SOURCE_CONFIG = {
    "host": "18.209.218.63",
    "port": 4563,
    "database": "lh_nautical",
    "schema": "dbo",
    "user": "student",
    "password": "<YOUR_PASSWORD>",
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
}

TARGET_CONFIG = {
    "dev_catalog": "dev_lh_nautical",
    "prod_catalog": "prod_lh_nautical",
    "raw_schema": "raw",
    "bronze_schema": "bronze",
    "silver_schema": "silver",
    "gold_schema": "gold",
}