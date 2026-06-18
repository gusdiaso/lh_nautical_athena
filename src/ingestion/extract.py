df = (
    spark.read
    .format("jdbc")
    .option("url", JDBC_URL)
    .option("dbtable", "INFORMATION_SCHEMA.TABLES")
    .option("user", SOURCE_CONFIG["user"])
    .option("password", SOURCE_CONFIG["password"])
    .option("driver", SOURCE_CONFIG["driver"])
    .load()
)

display(df)