use algo;

CREATE TABLE IF NOT EXISTS instruments_token (
            token VARCHAR(50),
            symbol VARCHAR(50),
            name VARCHAR(50),
            expiry VARCHAR(50),
            strike FLOAT,
            lotsize INT,
            instrumenttype VARCHAR(50),
            exch_seg VARCHAR(50),
            tick_size FLOAT,
            PRIMARY KEY (token)
);
        
CREATE TABLE login_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    smartApi VARCHAR(1024),
    authToken VARCHAR(1024),
    refreshToken VARCHAR(1024),
    feedToken VARCHAR(1024),
    UNIQUE (id)
);




