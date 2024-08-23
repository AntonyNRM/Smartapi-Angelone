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
from sqlalchemy import text
import mysql.connector as sqlConnector
import http.client
import logging

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
global token, exchange, tradingsymbol, symboltoken, symbol, stop_event, stop_loop, gtta
global exch_seg, rule_id, SL_order_id

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

def stop_function():
    global stop_loop
    stop_loop = True

def token_finder(name, expiry, instrumenttype, exchange, strike, option_type):
    global a, symboltoken, symbol
    
    def fetch_json_data(url, file_path):
        # Fetch the JSON data from the URL
        response = requests.get(url)
        data = response.json()
        # Save the data to a file
        with open(file_path, 'w') as file:
            json.dump(data, file)
        return data

    def load_json_data(file_path):
        # Load the JSON data from the file
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data

    def search_symbol(data, name, expiry, instrumenttype, exchange, strike, option_type):
        # Search for the target using name, expiry, instrumenttype, and exchange        
        symbols = str(strike)+option_type
        print(name, expiry, instrumenttype, exchange, strike, symbols)
        
        for item in data:
            if (item['name'] == name and 
                item['expiry'] == expiry and 
                item['instrumenttype'] == instrumenttype and 
                item['exch_seg'] == exchange and 
                item['symbol'][-7:] == symbols):
                print(item)
                return item
        return None

    def is_file_updated_today(file_path):
        global a
        # Check if the file was updated today
        if not os.path.exists(file_path):
            return False
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
     
        return file_mod_time.date() == datetime.today().date()

    # URL containing the JSON data
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    # File path to store the JSON data
    file_path = "scrip_master.json"

    # Get the absolute path of the file
    absolute_file_path = os.path.abspath(file_path)
    print(f"The JSON data will be saved to: {absolute_file_path}")

    # Check if the file was updated today
    if is_file_updated_today(file_path):
        # Load the JSON data from the file if it was updated today
        json_data = load_json_data(file_path)
    else:
        # Fetch and save the JSON data if the file was not updated today
        json_data = fetch_json_data(url, file_path)

    
    # Search for the target symbol in the stored JSON data
    result = search_symbol(json_data, name, expiry, instrumenttype, exchange,strike, option_type)
    toke = result['token']
    symb = result['symbol']
    symboltoken = toke
    

    print(toke, symb)


    return toke, symb

def expdate(exp):
    global expirydat, currentdat
    current_date = datetime.now().date()
    days_ahead = exp - current_date.weekday()
    mon = str(current_date.month)
    dat = str(current_date.day).zfill(2)
    yr = str(current_date.year)
        
        
    months = {
                '1': "JAN", '2': "FEB", '3': "MAR", '4': "APR",
                '5': "MAY", '6': "JUN", '7': "JUL", '8': "AUG",
                '9': "SEP", '10': "OCT", '11': "NOV", '12': "DEC"
            }    
    mont = months.get(mon, "Invalid Month")
    currentdat = str(dat)+str(mont)+str(yr)

    if days_ahead == 0 :
        mon = str(current_date.month)
        dat = str(current_date.day).zfill(2)
        yr = str(current_date.year)
        
        
        months = {
                '1': "JAN", '2': "FEB", '3': "MAR", '4': "APR",
                '5': "MAY", '6': "JUN", '7': "JUL", '8': "AUG",
                '9': "SEP", '10': "OCT", '11': "NOV", '12': "DEC"
            }    
        mont = months.get(mon, "Invalid Month")
        datw = str(dat)+str(mont)+str(yr)
        expirydat = datw
        return datw
    elif days_ahead < 0:
        days_ahead += 7

    coming_expiry = current_date + timedelta(days=days_ahead)
    mon = str(coming_expiry.month)
    dat = str(coming_expiry.day).zfill(2)
    yr = str(coming_expiry.year)
    months = {
            '1': "JAN", '2': "FEB", '3': "MAR", '4': "APR",
            '5': "MAY", '6': "JUN", '7': "JUL", '8': "AUG",
            '9': "SEP", '10': "OCT", '11': "NOV", '12': "DEC"
        }    
    mont = months.get(mon, "Invalid Month")


    # print(dat,mont,yr)
    coming_expiry = str(dat)+str(mont)+str(yr)
        
    expirydat = coming_expiry

    
    # print("DATE = ",coming_expiry)
    return coming_expiry


#================================================================================================================================================================================================================================================================================================
# Define button click function
def button_click():
    global underlying, strike, option_type, above_price, stop_loss, targets
    global authToken, symbol, symboltoken, stop_loop, exchange

    buy_at = Buy_at_entry.get().strip()
    
    if not buy_at:
        messagebox.showinfo("Warning", "Please fill both buy at and sell after fields.")
        return

    print(buy_at)
    parts = buy_at.split('\n')
    print(parts[0])
    print(parts[1])
    print(parts[2])
    print(parts[3])

    if len(parts) < 4:
        print("Error: Insufficient parts in the message. Please check the message format.")
        return

    try:
        # Process the first line
        action, underlying, strike, option_type = parts[0].split()
        strike = int(strike)
        
        # Extract 'ABOVE' price
        above_price_str = parts[2].split()[1]  # '₹150'
        above_price = float(above_price_str[1:])  # Convert '150' to float

        # Extract 'SL' stop loss
        stop_loss_str = parts[3].split()[1]  # '₹130'
        stop_loss = float(stop_loss_str[1:])  # Convert '130' to float

        # Extract 'TGT' targets
        targets_str = parts[4].split()[1]  # '170₹-180₹-200₹'
        targets = [float(target[:-1]) for target in targets_str.split('-')]  # Extract values before '₹' and convert to float

        print("Action:", action)
        print("Underlying:", underlying)
        print("Strike:", strike)
        print("Option Type:", option_type)
        print("Above Price:", above_price)
        print("Stop Loss:", stop_loss)
        print("Targets:", targets)
    except (ValueError, IndexError) as e:
        print(f"Error: {e}. Please check the input values for correct format.")
        return



    if selected_option == 0:
        messagebox.showinfo("Warning", "Please select Market.")
        return

    if time.time() >= target_time:
        print("Maximum runtime (15:20 hours) reached. Exiting program.")
        exit()
    
    expiry = ""
    name = ""
    exchange = ""
    instrumenttype = ""

    if re.search("BANK", underlying):
        expiry = calendar.WEDNESDAY
        exchange = "NFO"    
        name = "BANKNIFTY"
        expiry = expdate(expiry)
        instrumenttype = "OPTIDX"
    elif re.search("NIFTY", underlying):
        expiry = calendar.THURSDAY
        exchange = "NFO"    
        name = "NIFTY"
        expiry = expdate(expiry)
        instrumenttype = "OPTIDX"
    elif re.search("SENSEX", underlying):
        expiry = calendar.FRIDAY
        exchange = "BFO"    
        name = "SENSEX"
        expiry = expdate(expiry)
        instrumenttype = "OPTIDX"
    elif re.search("FIN", underlying):
        expiry = calendar.TUESDAY
        exchange = "NFO"    
        name = "FINNIFTY"
        expiry = expdate(expiry)
        instrumenttype = "OPTIDX"
    else:
        print(" ERROR : SYMBOL DOES NOT MATCH")
    print(expiry)
    
    fetch = token_finder(name, str(expiry), instrumenttype, exchange, strike, option_type)
    symboltoken = fetch[0] # saved as global
    symbol = fetch[1] # saved as global

    ltp = get_ltp_data()
    
    # Run buyorders in a new thread
    background_thread = threading.Thread(target=buyorders, args=(above_price, stop_event))
    background_thread.start()


    combobox["state"] = "disabled"
    radio1["state"] = "disabled"
    radio2["state"] = "disabled"
    radio3["state"] = "disabled"
    button.config(state="disable")
    # button2.config(state="disabled")
    button3.config(state="normal")
    time.sleep(1.00)

def button3_click():
    global stop_loop
    stop_buyorders()
    stop_loop = False
    
    print("Loop has been stopped from another function.")
    combobox["state"] = "normal"
    radio1["state"] = "normal"
    radio2["state"] = "normal"
    radio3["state"] = "normal"
    button.config(state="normal")
    # button2.config(state="disable")
    button3.config(state="disable")
    pass

def stop_buyorders():
    global public_ip, local_ip, mac_address,  api_key, authToken, gtt_rule_id, SL_order_id
    global stop_event, stop_loop, symbol, symboltoken, gtta
    global underlying, strike, option_type, above_price, exchange
    stop_loop = False
    obj=SmartConnect(api_key=api_key)
    values = combobox['values']
    disclose = values[0]
    qty = combobox.get() 
    limit_price = above_price + 1.00
    trg_price = above_price
    trig_price = above_price + 1.00
    sell_price = above_price + 0.70
    transactiontype = "SELL"
    sell_rule_id = 0


    if check_gtt_status(gtt_rule_id) == "PENDING":
        cancel_gtt_rule()
        gtta = 0
        exit()
    elif check_order_status(  SL_order_id) != "completed":
        cancel_order(SL_order_id)
        time.sleep(1)
        sell_order_id = sell_order(above_price, "LIMIT")
        time.sleep(1)
        sell_order_status = check_order_status(  sell_order_id)  
        while sell_order_status != "completed":
            ltp = get_ltp_data()
            print("LTP : ",ltp['ltp'])
            sell_order_status = check_order_status(  sell_order_id)
            if ltp < (above_price - 10):
                price = above_price - 10
                sell_order_id1 = sell_order(price, "MARKET")
                sell_order_status1 = check_order_status(  sell_order_id1)
                while sell_order_status1 != "completed":
                    sell_order_status = check_order_status(  sell_order_id1)
                    gtta = 0
                    exit()
                if sell_order_status == "completed":
                    print("SL HIT")
                    gtta = 0
                    exit()
        if sell_order_status == "completed":
            print("Sold at CTC")
            gtta = 0
            exit()


    gtta = 0

    combobox["state"] = "normal"
    radio1["state"] = "normal"
    radio2["state"] = "normal"
    radio3["state"] = "normal"
    button.config(state="normal")
    button2.config(state="disable")
    button3.config(state="disable")
    if stop_event is not None:
        stop_event.set()
        print("Stop signal sent to buy orders thread.")


def button2_click():
    # sellorders()
    combobox["state"] = "normal"
    radio1["state"] = "normal"
    radio2["state"] = "normal"
    radio3["state"] = "normal"
    button.config(state="normal") 
    button2.config(state="disabled")
    if time.time() >= target_time:
        print("Maximum runtime (15:20 hours) reached. Exiting program.")
        exit()

#================================================================================================================================================================================================================================================================================================

def radio_changed():
    global selected_option, lab1, selected_option_combo
    combobox.set("")  # Clear the current selection
    combobox["values"] = []  # Clear the combobox values
    button.config(state="disabled")
    button2.config(state="disabled")
    button3.config(state="disabled")
    if time.time() >= target_time:
        print("Maximum runtime (15:20 hours) reached. Exiting program.")
        exit()
    combobox["state"] = "readonly"
    selected_option = var.get()
    if selected_option == 1:
        lab1 = "NIFTY"
        update_label(lab1)
        values = [i for i in range(25, 1801, 25)]
        combobox["values"] = values
        on_combobox_select()
        return
    elif selected_option == 2:
        lab1 = "BANK NIFTY"
        update_label(lab1)
        values = [i for i in range(15, 901, 15)]
        combobox["values"] = values
        on_combobox_select()        
        return
    elif selected_option == 3:
        lab1 = "SENSEX"
        update_label(lab1)
        values = [i for i in range(10, 501, 10)]
        combobox["values"] = values
        on_combobox_select()        
        return
    
def update_label(lab1):
    label1.config(text=lab1)

def on_combobox_select(event=None):
    global selected_option_combo,buy_at,sell_after
    value = combobox.get()    
    if value:
        selected_option_combo = int(value) 
        print(selected_option_combo)
        button.config(state="normal")
        on_buy_at_change()
    else:
        print("SELECT THE QUANTITY OF SHARES")

def on_buy_at_change(*args):

    pass

def on_sell_after_change(*args):

    pass
#================================================================================================================================================================================================================================================================================================
# new token code to be added later if required
def get_new_token():
    return "Bearer new_token_example"    

def get_ltp_data():
    global public_ip, local_ip, exchange, symbol, symboltoken, api_key, authToken
    url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/order/v1/getLtpData"
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
    request_data = {
        'exchange': exchange,
        'tradingsymbol': symbol,
        'symboltoken': symboltoken
    }

    response = requests.post(url, headers=headers, data=json.dumps(request_data))
    response_data = response.json()
    
    #print("Response Data:", response_data)  # Print the entire response for debugging

    if response_data.get('status'):
        # Extract and return the data
        return response_data['data']
    else:
        if response_data.get('errorcode') == 'AG8001':  # Invalid Token Error
            print("Invalid Token. Refreshing symboltoken...")
            new_token = get_new_token()
            return get_ltp_data()
        else:
            print(f"Error fetching LTP data: {response_data.get('message')}")
            return None

#=========================================================================================================================================================================================================================================================

# GTT SET
def GTT_create_rule(above_price, trig_price, disclose):
    global public_ip, local_ip, api_key, authToken, mac_address, expirydat, currentdat, symbol, symboltoken, exchange, qty
    transactiontype = "BUY"

    if expirydat == currentdat:
        timeperiod = 0
    else:
        timeperiod = 1


    try:
        payload = {
            "tradingsymbol": symbol,
            "symboltoken": symboltoken,
            "exchange": exchange,
            "transactiontype": transactiontype,
            "producttype": "CARRYFORWARD",
            "price": above_price,
            "qty":  qty,
            "triggerprice": trig_price,
            "timeperiod": timeperiod
        }

        # Convert payload to JSON string
        payload_json = json.dumps(payload)

        # Define the headers
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
        conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

        # Send the request
        logging.info("Sending GTT rule creation request with payload: %s", payload_json)
        conn.request("POST", "/rest/secure/angelbroking/gtt/v1/createRule", payload_json, headers)

        # Get the response
        res = conn.getresponse()
        data = res.read()

        # Decode and load JSON response
        dat = data.decode("utf-8")
        da = json.loads(dat)
        logging.info("Received response: %s", da)

        # Extract gtt_rule_id from response
        gtt_rule_id = da.get("data", {}).get("id", None)
        logging.info("GTT rule id: %s", gtt_rule_id)

        return gtt_rule_id

    except Exception as e:
        logging.error("GTT Rule creation failed: %s", e)
        return None

def cancel_gtt_rule():
    global public_ip, local_ip, symboltoken, exchange,api_key, gtt_rule_id, authToken
    url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/gtt/v1/cancelRule"
    
    payload = json.dumps({
        "id": gtt_rule_id,
        "symboltoken": symboltoken,
        "exchange": exchange
    })
    
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

    response = requests.post(url, headers=headers, data=payload)
    response_data = response.json()
    print("GTT CANCEL :",response_data)

    if response.status_code == 200:
        print("GTT rule cancelled successfully.")
        exit()
        return response.json()
    else:
        print("Failed to cancel GTT rule.")
        return response.text

def check_gtt_status(gtt_rule_id):
    global public_ip, local_ip, authToken, mac_address,api_key
    try:
        # Define the payload
        payload = {
            "id": gtt_rule_id
        }

        # Convert payload to JSON string
        payload_json = json.dumps(payload)

        # Define the headers
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

        # Send the request
        conn.request("POST", "/rest/secure/angelbroking/gtt/v1/ruleDetails", payload_json, headers)

        # Get the response
        res = conn.getresponse()
        data = res.read()

        # Decode and parse the JSON response
        response_json = data.decode("utf-8")
        response_dict = json.loads(response_json)

        # Check the status of the rule
        rule_status = response_dict.get("data", {}).get("status", None)
        if rule_status is None:
            print("Rule status not found in the response.")
            return
        if rule_status == "NEW":
            print("PENDING")
            status = "PENDING"
            return status 
        elif rule_status == "TRIGGERED":
            print(f"The GTT rule status is: {rule_status}")
            status = "TRIGGERED"
            return status
        elif rule_status == "CANCELLED":
            print(f"The GTT rule status is: {rule_status}")
            status = "CANCELLED"            
            exit()
            return status
    except Exception as e:
        print("GTT STATUS CHECK ERROR: {}".format(e))
        return None

# Button Process
def buyorders(above_price, stop_event):
    global api_key, authToken, symbol, symboltoken, stop_loop, gtta, gtt_rule_id, SL_order_id, exchange, qty
    obj=SmartConnect(api_key=api_key)
    producttype = "CARRYFORWARD"
    trig_price = above_price + 1.00
    
    qty = combobox.get() 
    SL_order_id = ""
    SL_order_status= ""
    i = 0
    ltp = get_ltp_data()
    print("LTP : ",ltp['ltp'])
    values = combobox['values']
    disclose = values[0]
    

    try:
        gtt_rule_id=GTT_create_rule(above_price, trig_price, disclose)
        print("The GTT rule id is: {}".format(gtt_rule_id))
        stat = check_gtt_status(  gtt_rule_id)
        order_status = stat

        time.sleep(0.50)
        print("GTT RULE STATUS :", order_status)
        while order_status == "PENDING":
            stat = check_gtt_status(gtt_rule_id)
            order_status = stat
            print(order_status)
            ltp = get_ltp_data()
            print("LTP : ",ltp['ltp'])
            if order_status == "CANCELLED":
                print("GTT Status : ",order_status)
                exit()    
            if order_status == "TRIGGERED":
                print("GTT rule Triggered : ", order_status)
                gtta = 1
            time.sleep(0.50)
        stat = check_gtt_status(gtt_rule_id)
        order_status = stat
        if order_status == "CANCELLED":
                print("GTT Status : ",order_status)
                exit()

        try:


            if order_status != "Pending":
                if order_status == "TRIGGERED":
                    print("GTT order executed : ", order_status)
                    stop_loss_price = above_price - 15.00  # Example stop-loss price
                    SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                    stop_loss_status_complete = check_order_status(SL_order_id)
                    SL_order_status = stop_loss_status_complete[0]
                    SL_status = stop_loss_status_complete[1]
                    ltp = get_ltp_data()
                    slprice = 40
                    try:
                        while (SL_order_status != "TRIGGERED" or SL_order_id == ""):
                            stop_loss_status_complete = check_order_status(SL_order_id)
                            SL_order_status = stop_loss_status_complete[0]
                            SL_status = stop_loss_status_complete[1]

                            ltp = get_ltp_data()                    
                            print("LTP : ",ltp)
                            if SL_order_status == "TRIGGERED":
                                print("SL HIT", SL_status)
                                return
                            if ltp > above_price + 4 and ltp < above_price + 5:
                                # cancel previous SL and create a new SL
                                stop_loss_price = above_price - 3
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 5.05 and ltp < above_price + 7:
                                # cancel previous SL and create a new SL
                                stop_loss_price = above_price + 2
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 7.05 and ltp < above_price + 9:
                                stop_loss_price = above_price + 3
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 9.50 and ltp < above_price + 12:
                                stop_loss_price = above_price + 5
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 12 and ltp < above_price + 14.5:
                                stop_loss_price = above_price + 8
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 15 and ltp < above_price + 18.5:
                                stop_loss_price = above_price + 10
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 19 and ltp < above_price + 22.5:
                                stop_loss_price = above_price + 15
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price, producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 25 and ltp < above_price + 27.5:
                                stop_loss_price = above_price + 20
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 30 and ltp < above_price + 32.5:
                                stop_loss_price = above_price + 25
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                            if ltp > above_price + 35 and ltp < above_price + 37.5:
                                stop_loss_price = above_price + 30
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]                                            
                            if ltp > slprice:
                                stop_loss_price = ltp - 5
                                if SL_order_id != "":
                                    cancel_order("STOPLOSS", SL_order_id)
                                SL_order_id = place_stop_loss_order(stop_loss_price,  producttype, disclose)
                                stop_loss_status_complete = check_order_status(  SL_order_id)
                                SL_order_status = stop_loss_status_complete[0]
                                SL_status = stop_loss_status_complete[1]
                                slprice = ltp + 5
                    except Exception as e:
                        print("Error at Trailing SL order: {}".format(e))            
                        
        except Exception as e:
            print("Error at 1st SL order: {}".format(e))            
                        


    except Exception as e:
        print("Error at the loop: {}".format(e))

# Remaining Process
def sell_order(price, ordertype):
    global public_ip, local_ip, api_key, authToken, mac_address, symboltoken, symbol, above_price
    transaction_type = "SELL"
    
    values = combobox['values']
    disclose = values[0]
    try:
        payload = {
            "tradingsymbol": symbol,
            "symboltoken": symboltoken,
            "exchange": exchange,
            "transactiontype": transaction_type,
            "producttype": "CARRYFORWARD",
            "price": price,
            "quantity": qty,
            "duration": "DAY",
            "ordertype": ordertype,
            "triggerprice": 0,  # For normal orders, set trigger price to 0
        }

        # Convert payload to JSON string
        payload_json = json.dumps(payload)

        # Define the headers
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
        conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

        # Send the request
        logging.info("Sending normal order request with payload: %s", payload_json)
        conn.request("POST", "/rest/secure/angelbroking/order/v1/placeOrder", payload_json, headers)

        # Get the response
        res = conn.getresponse()
        data = res.read()

        # Decode and load JSON response
        dat = data.decode("utf-8")
        da = json.loads(dat)
        logging.info("Received response: %s", da)

        # Extract order_id from response
        order_id = da.get("data", {}).get("orderid", None)
        logging.info("Order id: %s", order_id)

        return order_id

    except Exception as e:
        logging.error("Order creation failed: %s", e)
        return None

def place_stop_loss_order(stop_loss_price, producttype, disclose):
    global public_ip, local_ip, api_key, authToken, mac_address, symboltoken, symbol, above_price, exchange, qty

    transactiontype = "SELL"
    ordertype = "STOPLOSS_LIMIT"
    variety = "STOPLOSS"
    limit_price = stop_loss_price + 1
    
    # Define the payload
    payload = {
        "variety": variety,
        "tradingsymbol": symbol,
        "symboltoken": symboltoken,
        "transactiontype": transactiontype,
        "exchange": exchange,
        "ordertype": ordertype,
        "producttype": producttype,
        "duration": "DAY",
        "price": limit_price,
        "stoploss": 0,
        "quantity": qty,
        "triggerprice": stop_loss_price

    }

    # Convert payload to JSON string
    payload_json = json.dumps(payload)

    # Define the headers
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

    # Send the request
    conn.request("POST", "/rest/secure/angelbroking/order/v1/placeOrder", payload_json, headers)

    # Get the response
    res = conn.getresponse()
    data = res.read()

    # Decode and parse the JSON response
    response_json = data.decode("utf-8")
    response_dict = json.loads(response_json)

    # Extract the order ID
    order_id = response_dict.get("data", {}).get("orderid", None)

    # Print the order ID
    if order_id is not None:
        print(f"Order ID: {order_id}")
        return order_id
    else:
        print("Order ID not found in the response.")

def check_order_status(order_id):
    global public_ip, local_ip, authToken, mac_address,api_key
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
    conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

    # Send the request
    endpoint = f"/rest/secure/angelbroking/order/v1/details/{order_id}"
    conn.request("GET", endpoint, headers=headers)

    # Get the response
    res = conn.getresponse()
    data = res.read()

    # Decode and parse the JSON response
    response_json = data.decode("utf-8")
    response_dict = json.loads(response_json)

    # Check the status of the order
    order_status = response_dict.get("data", {}).get("orderstatus", None)
    if order_status is None:
        print("Order status not found in the response.")
        return

    if order_status.lower() == "rejected":
        print("The stop loss order has been rejected.")
        return order_status
    elif order_status.lower() == "completed":
        print("The stop loss order has been triggered and completed.")
        return order_status
    else:
        print(f"The stop loss order status is: {order_status}")
        return order_status

def cancel_order(order_id, parent_order_id=None):
    global api_key, authToken, symbol, symboltoken, stop_loop, gtta
    global public_ip, local_ip, api_key, authToken, mac_address

    try:
        payload = {
            "orderid": order_id
        }

        # Convert payload to JSON string
        payload_json = json.dumps(payload)

        # Define the headers
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
        conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

        # Send the request
        logging.info("Sending cancel order request with payload: %s", payload_json)
        conn.request("POST", "/rest/secure/angelbroking/order/v1/cancelOrder", payload_json, headers)

        # Get the response
        res = conn.getresponse()
        data = res.read()

        # Decode and load JSON response
        dat = data.decode("utf-8")
        da = json.loads(dat)
        logging.info("Received response: %s", da)

        # Extract status from response
        status = da.get("status", None)
        logging.info("Cancel order status: %s", status)
        time.sleep(1)

        return status

    except Exception as e:
        logging.error("Order cancellation failed: %s", e)
        return None

#===================================================================================================================================================================================================================
# Create a Tkinter window
window = tk.Tk()
window.title("Angel Trader")
window.geometry("673x115")

# Use themed widgets
style = ttk.Style()
style.theme_use("clam")  # You can change "clam" to other available themes like "aqua", "alt", "default", etc.

# Create labels
label1 = tk.Label(window, text="Quantity")
label2 = tk.Label(window, text="Telegram Message:")
label3 = tk.Label(window, text="Minimum point to obtain")
label4 = tk.Label(window, text="Target")
label5 = tk.Label(window, text="Stop Loss 1")
label6 = tk.Label(window, text="Stop Loss 2")

# Create a Combobox widget
combobox = ttk.Combobox(window)
combobox["state"] = "disable"  # To prevent manual input

# Create StringVar variables
Buy_at_var = tk.StringVar()

# Create a single-line text box with increased width
Buy_at_entry = ttk.Entry(window, textvariable=Buy_at_var, width=80)

# Register the callback functions for text changes
Buy_at_var.trace_add("write", on_buy_at_change)

# Grid layout for labels and text boxes
# Configure columns
window.grid_columnconfigure(0, weight=0)  # Column for labels
window.grid_columnconfigure(1, weight=2)  # Column for text boxes and comboboxes

# Position widgets in grid
label1.grid(row=0, column=0, padx=2, pady=2, sticky="e")
label2.grid(row=1, column=0, padx=2, pady=2, sticky="e")
combobox.grid(row=0, column=1, padx=2, pady=2, sticky="w")  # Align Combobox
Buy_at_entry.grid(row=1, column=1, padx=2, pady=2, sticky="w")  # Align Entry

# Create frames
frame1 = ttk.Frame(window)
frame1.grid(row=3, column=0, columnspan=2, pady=10)

frame2 = ttk.Frame(window)
frame2.grid(row=3, column=2, pady=10)

# Create radio buttons
var = tk.IntVar()
radio1 = ttk.Radiobutton(frame1, text="NIFTY", variable=var, value=1, command=radio_changed)
radio2 = ttk.Radiobutton(frame1, text="BANKNIFTY", variable=var, value=2, command=radio_changed)
radio3 = ttk.Radiobutton(frame1, text="SENSEX", variable=var, value=3, command=radio_changed)

# Create buttons
button = ttk.Button(frame1, text="Place Order", command=button_click, style="Green.TButton")
button2 = ttk.Button(frame2, text="Market Close", command=button2_click, style="Red.TButton")
button3 = ttk.Button(frame2, text="CTC SL", command=stop_buyorders, style="Red.TButton")

# Pack buttons and radio buttons
button.pack(side=tk.LEFT, padx=10, pady=10)
button2.pack(side=tk.LEFT, padx=10, pady=10)
button3.pack(side=tk.LEFT, padx=10, pady=10)

radio1.pack(side=tk.LEFT, padx=10, pady=10)
radio2.pack(side=tk.LEFT, padx=10, pady=10)
radio3.pack(side=tk.LEFT, padx=10, pady=10)

button.config(state="disabled")
button2.config(state="disabled")
button3.config(state="disabled")

# Bind events
radio1.bind("<Button-1>", lambda event: radio_changed())
radio2.bind("<Button-1>", lambda event: radio_changed())
radio3.bind("<Button-1>", lambda event: radio_changed())
combobox.bind("<<ComboboxSelected>>", on_combobox_select)

# Style configuration
style.configure("TLabel", font=("Arial", 11))
style.configure("TCombobox", font=("Arial", 11))
style.configure("TButton", font=("Arial", 11))
style.configure("TRadiobutton", font=("Arial", 11))
style.configure("Green.TButton", background="green")
style.configure("Red.TButton", background="red")

# Configure rows to expand properly
window.grid_rowconfigure(2, weight=1)

# Start the Tkinter event loop
window.mainloop()
 
 
