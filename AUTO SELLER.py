import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from SmartApi import SmartConnect
import re
import threading
import pyotp
import requests
import json
import os
import time
import calendar
from datetime import date, datetime, timedelta
from logzero import logger
from sqlalchemy import text, create_engine
import mysql.connector as sqlConnector
import http.client
import logging
import urllib.request
import pandas as pd


# Setup logging
logging.basicConfig(level=logging.INFO)


current_time = time.localtime()
target_time = time.mktime((current_time.tm_year, current_time.tm_mon, current_time.tm_mday, 23, 44, 59, current_time.tm_wday, current_time.tm_yday, current_time.tm_isdst))

if time.time() >= target_time:
    print("Maximum runtime (15:20 hours) reached. Exiting program.")
    exit()

# Global Variables
global smartApi, authToken, refreshToken, feedToken, api_key
global con, a, expirydat, currentdat
global underlying, strike, option_type, above_price, stop_loss, targets
global token, symbol, stop_event, stop_loop, gtta
global exch_seg, rule_id, SL_order_id, mac_address
global tradingsymbol, symboltoken, buyavgprice, exchange , producttype, quantity

authToken = ""
smartApi = ""
refreshToken = ""
feedToken = ""
a = 0
stop_event = None
stop_loop = False
stop_event = threading.Event()
gtta = 0
rule_id = 0

# Database Connections
con = sqlConnector.connect(host="127.0.0.1", user="root", passwd="", database="", port="3306", auth_plugin='mysql_native_password')

Toke = ""
api_key = ''

mac_address = ''
public_ip = ''
local_ip = ''


def login():
    global smartApi, authToken, refreshToken, feedToken, api_key
    username = ''
    pwd = ''
    login_token = ""
    totp = pyotp.TOTP(login_token).now()
    
    smartApi = SmartConnect(api_key=api_key)
    data = smartApi.generateSession(username, pwd, totp)

    if not data['status']:
        logger.error("Login failed: %s", data)
        return None
    
    #print(data)

    authToken = data['data']['jwtToken']
    refreshToken = data['data']['refreshToken']
    feedToken = smartApi.getfeedToken()

    #print(smartApi, authToken, refreshToken, feedToken)
    #print("Length of authToken:", len(authToken))
    
    SaveAccessToken(smartApi, authToken, refreshToken, feedToken)
    
    return smartApi, authToken, refreshToken, feedToken

def SaveAccessToken(smartApi, authToken, refreshToken, feedToken):
    print("Access Token Saved")
    query = """
        INSERT INTO algo.login_details (smartApi, authToken, refreshToken, feedToken) 
        VALUES (%s, %s, %s, %s) 
        ON DUPLICATE KEY UPDATE 
        smartApi = %s, authToken = %s, refreshToken = %s, feedToken = %s, timestamp = CURRENT_TIMESTAMP();
    """
    values = (str(smartApi), authToken, refreshToken, feedToken, str(smartApi), authToken, refreshToken, feedToken)
    
    cur = con.cursor()
    cur.execute(query, values)
    con.commit()

def GetAccessToken():
    global smartApi, authToken, refreshToken, feedToken, api_key
    cursor = con.cursor()
    query = "SELECT SQL_NO_CACHE smartApi, authToken, refreshToken, feedToken FROM login_details WHERE Date(timestamp) = '{}';".format(date.today())
    cursor.execute(query)
    row = cursor.fetchone()
    if row:
        smartApi, authToken, refreshToken, feedToken = row
        #print("Access Token Obtained",authToken)
        return row
    else:
        return None

def truncate_table(engine, table_name):
    with engine.connect() as connection:
        truncate_statement = text(f"TRUNCATE TABLE {table_name}")
        connection.execute(truncate_statement)



accesstoken = GetAccessToken()


if accesstoken is None:
    login()

if accesstoken is not None:
    
    smartApi = accesstoken[0]
    authToken = accesstoken[1]
    refreshToken = accesstoken[2]
    feedToken = accesstoken[3]





tradingsymbol = ""
buyavgprice = 0.00
symboltoken =  0
quantity = 0
producttype = ""
exchange = ""

def get_open_positions():
    global public_ip, local_ip, exchange, symbol, symboltoken, api_key, authToken

    
    # Establish connection to the API
    conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

    # Set up the request headers
    headers = {
        'Content-type': 'application/json',
        'X-ClientLocalIP': local_ip,
        'X-ClientPublicIP': public_ip,
        'X-MACAddress': mac_address,
        'Accept': 'application/json',
        'X-PrivateKey': api_key,
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'Authorization': authToken
    }

    # Send GET request to the API
    conn.request("GET", "/rest/secure/angelbroking/order/v1/getPosition", '', headers)

    # Get the response from the API
    res = conn.getresponse()
    data = res.read().decode("utf-8")
    # print(data)

    # Check if the response data is empty
    if not data:
        print("Error: Empty response received from the server.")
        return None
    
    try:
        # Parse the JSON response
        response = json.loads(data) 
    
        # Check if the request was successful
        if response.get("status") == True:
            return response.get("data", [])
        else:
            print(f"API Error: {response.get('message', 'Unknown error')}")
            return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None


def check_order_status(order_id):
    global public_ip, local_ip, authToken, mac_address,api_key
    # Set up the request headers
    headers = {
        'Content-type': 'application/json',
        'X-ClientLocalIP': local_ip,
        'X-ClientPublicIP': public_ip,
        'X-MACAddress': mac_address,
        'Accept': 'application/json',
        'X-PrivateKey': api_key,
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'Authorization': authToken
    }

    # Create the connection
    conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

    # Send the request to get the order details using the uniqueorderid
    endpoint = f"/rest/secure/angelbroking/order/v1/details/{order_id}"
    conn.request("GET", endpoint, headers=headers)

    # Get the response
    res = conn.getresponse()
    data = res.read()

    # Decode and parse the JSON response
    response_json = data.decode("utf-8")
    response_dict = json.loads(response_json)

    if response_dict.get("status") and response_dict.get("data"):
        # Extract order status and filled shares
        order_status = response_dict["data"].get("orderstatus")
        filled_shares = response_dict["data"].get("filledshares", 0)
        
        print(f"Order Status: {order_status}")
        print(f"Filled Shares: {filled_shares}")

        if order_status.lower() == "complete" or int(filled_shares) > 0:
            print("Sell order has been executed.")
            return True
        elif order_status.lower() == "cancelled":
            print(f"Order Status: {order_status}")
            return order_status
        elif order_status.lower() == "rejected":
            print(f"Order Status: {order_status}")
            return order_status
        else:
            print(f"Sell order is not executed yet. Current status: {order_status}")
            return False
    else:
        print(f"Order not found or error: {response_dict.get('message', 'Unknown error')}")
        return None



# open_positions = [{'symboltoken': '434330', 'symbolname': 'CRUDEOIL', 'instrumenttype': 'OPTFUT', 'priceden': '1.00', 'pricenum': '1.00', 'genden': '1.00', 'gennum': '1.00', 'precision': '2', 'multiplier': '-1', 'boardlotsize': '1', 'exchange': 'MCX', 'producttype': 'INTRADAY', 'tradingsymbol': 'CRUDEOIL24AUG6650CE', 'symbolgroup': '', 'strikeprice': '6650.0', 'optiontype': 'CE', 'expirydate': '14AUG2024', 'lotsize': '100', 'cfbuyqty': '0', 'cfsellqty': '0', 'cfbuyamount': '0.00', 'cfsellamount': '0.00', 'buyavgprice': '87.45', 'sellavgprice': '90.82', 'avgnetprice': '43.60', 'netvalue': '-4360.00', 'netqty': '100', 'totalbuyvalue': '122430.00', 'totalsellvalue': '118070.00', 'cfbuyavgprice': '0.00', 'cfsellavgprice': '0.00', 'totalbuyavgprice': '87.45', 'totalsellavgprice': '90.82', 'netprice': '43.60', 'buyqty': '1400', 'sellqty': '1300', 'buyamount': '122430.00', 'sellamount': '118070.00', 'pnl': '1016.00', 'realised': '4381.00', 'unrealised': '-3365.00', 'ltp': '53.8', 'close': '88.9'}]

def get_order_book():
    payload = ''
    global public_ip, local_ip, authToken, mac_address,api_key
    conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")
    headers = {
        'Authorization': authToken,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'X-ClientLocalIP': local_ip,
        'X-ClientPublicIP': public_ip,
        'X-MACAddress': mac_address,
        'X-PrivateKey': api_key
    }

    # Create the connection
    

    try:
        conn.request("GET", "/rest/secure/angelbroking/order/v1/getOrderBook", payload, headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        response = json.loads(data)


        if response.get("status") == True:
            return response.get("data", [])
        else:
            print(f"API Error: {response.get('message', 'Unknown error')}")
            return None

    except Exception as e:
        print(f"Request failed: {e}")
        return None

def get_most_recent_order():
    global tradingsymbol
    order_book = get_order_book()
    if order_book is not None:
        # Filter orders by the trading symbol
        filtered_orders = [order for order in order_book if order['tradingsymbol'] == tradingsymbol]
        
        if not filtered_orders:
            print(f"No orders found for trading symbol: {tradingsymbol}")
            return None
        
        # Sort orders by a timestamp or order ID (assuming 'updatetime' is present)
        sorted_orders = sorted(filtered_orders, key=lambda x: x.get('updatetime', ''), reverse=True)

        # Get the most recent order
        most_recent_order = sorted_orders[0]
        print(f"Most Recent Order: {most_recent_order}")
        return most_recent_order

    return None


def get_order_details(open_positions):
    global tradingsymbol, symboltoken, buyavgprice, exchange , producttype, quantity
    for position in open_positions:
        tradingsymbol = position['tradingsymbol']
        symboltoken = position['symboltoken']
        buyavgprice = float(position['netprice'])
        exchange = position['exchange']
        producttype = position['producttype']
        quantity = int(position['netqty'])
        print(tradingsymbol, symboltoken, buyavgprice, exchange , producttype, quantity)
        # return tradingsymbol, symboltoken, buyavgprice, exchange , producttype, quantity
    most_recent_order = get_most_recent_order()
    if most_recent_order:
        buyavgprice = float(most_recent_order['averageprice'])
        quantity = int(most_recent_order['quantity'])
        print(f"  {buyavgprice}, Quantity: {quantity}")
    else:
        print("Failed to retrieve the most recent order.")
    return None, None, None, None, None, None


while True:
    positions =""
    
    positions = get_open_positions()
    # print(positions)

    if positions:
        open_positions = [position for position in positions if position['netqty'] != '0']
        print(open_positions)
        if open_positions:
            print(open_positions)
            ord = get_order_details(open_positions)
            if ord is not None:
                place_sell_order()
            else:
                print("waiting for order")
        else:
            print("No Order as of now")



    def place_sell_order():
        global tradingsymbol, symboltoken, buyavgprice, exchange , producttype, quantity
        global public_ip, local_ip, exchange, symbol, symboltoken, api_key, authToken

        
        # Establish connection to the API
        conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

        # Set up the request headers
        headers = {
            'Content-type': 'application/json',
            'X-ClientLocalIP': local_ip,
            'X-ClientPublicIP': public_ip,
            'X-MACAddress': mac_address,
            'Accept': 'application/json',
            'X-PrivateKey': api_key,
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'Authorization': authToken
        }            


        if buyavgprice is not None:
            # Set sell price 1 point higher than ordered price
            sell_price = buyavgprice + 2.50
            print(sell_price)
            # Construct the sell order
            sell_order = {
                "variety": "NORMAL",
                "tradingsymbol": tradingsymbol,
                "symboltoken": symboltoken,  # Replace with actual token if needed
                "transactiontype": "SELL",
                "exchange": exchange,
                "ordertype": "LIMIT",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": str(sell_price),
                "quantity": quantity
            }            
        
            # Place the sell order
            conn.request("POST", "/rest/secure/angelbroking/order/v1/placeOrder", json.dumps(sell_order), headers)
            res = conn.getresponse()
            data = res.read()
            if data.decode("utf-8") == "":
                print("Waiting for orders")
            else:
                print("Sell Order Response:", data.decode("utf-8"))
            dat = data.decode("utf-8")
            da = json.loads(dat)
            order_id = da.get("data", {}).get("uniqueorderid", None)
            print(order_id)

            status = check_order_status(order_id)
            while status != True:
                status = check_order_status(order_id)
                if status == "cancelled" or status == "rejected":
                    print("Exit with unwanted status : ", status)
                    break

            return sell_order, data.decode("utf-8")
        else:
            print("No order placed so far")
            return None

    time.sleep(0.60)