"""Load the CSV tables created by etl.py into PostgreSQL.

Running this script again replaces the rows in our five staging tables.
"""
#IMPORT LIBRARIES
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Boolean, Date, Integer, Numeric, create_engine, inspect, text
from sqlalchemy.engine import URL


# These are the five files produced by our cleaning and aggregation script.
table_names = [
    "household_daily",
    "household_weekly",
    "household_monthly",
    "spending_monthly",
    "financial_monthly",
]
#List the five CSV files that will be loaded into PostgreSQL. These files are created by the etl.py script.
#use for loop to load all five files (data)
schema_name = "diary_data"
# Columns that uniquely identify each row in our summary tables
#compound primary keys for the five tables. Each table has a different set of columns that uniquely identify each row.
primary_keys = {
    "household_daily": ["hh_ids", "transaction_date"],
    "household_weekly": ["hh_ids", "week_start"],
    "household_monthly": ["hh_ids", "month_start"],
    "spending_monthly": [
        "hh_ids", "month_start", "category", "payment_group"
    ],
    "financial_monthly": [
        "hh_ids", "month_start", "financial_activity"
    ]
}

def load_tables():
    #Find the project folder
    project = Path(__file__).resolve().parent.parent
    data_folder = project / "data" / "processed" #find the processed data folder
    # Read the database settings from the terminal environment.
    # Connecting to postgresql

    # Since I am pushing to git--Keeping passwords out of the Python file is safer for GitHub.

    db_url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD") or None,
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "kenya_cashflow"),
    )
    engine = create_engine(db_url) #creates SQLALCHEMy engine

    # Run all five loads in one transaction. If a load fails, PostgreSQL
    # rolls back the changes rather than leaving half the tables updated.
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        # Reading each CSV file and loading it into PostgreSQL

        for name in table_names: 
            file_path = data_folder / f"{name}.csv"
            if not file_path.is_file():
                raise FileNotFoundError(f"Missing processed file: {file_path}")

            df = pd.read_csv(file_path, dtype={"hh_ids": "string"}) #household IDs are identifiers, not numbers, so read them as strings

            # CSV dates start as text. Convert them before inserting into SQL....csv doesnt preserve actual db data types
            date_columns = ["transaction_date", "week_start", "month_start"]
            for column in date_columns:
                if column in df.columns:
                    df[column] = pd.to_datetime(df[column], errors="raise").dt.date # report error if date cnnot be converted
            # Check that the columns chosen as keys are valid
            keys = primary_keys[name] # Gets key column for each table from the primary_keys dictionary

            if df[keys].isna().any().any(): # check for missing values in the primary key columns(rule no 1--should be not null)
                raise ValueError(f"Missing values in primary key: {name}")

            if df.duplicated(subset=keys).any(): # check for duplicate rows based on the primary key columns (rule no 2--should be unique)
                raise ValueError(f"Duplicate primary key found in {name}")

            # creating a dictionary of db column types to ensure that the data is loaded into the correct types in PostgreSQL
            # Explicit SQL types for financial amounts, dates and indicators.
            # PostgreSQL NUMERIC avoids storing KES amounts as approximate floats.
            sql_types = {}
            for column in df.columns:
                if column in date_columns:
                    sql_types[column] = Date()
                elif column.endswith("_kes"):
                    sql_types[column] = Numeric(18, 2)
                elif column in ["has_core_activity", "negative_month"]:
                    sql_types[column] = Boolean()
                elif column == "negative_day_share":
                    sql_types[column] = Numeric(12, 8)
                elif column in [
                    "eligible_transactions", "recorded_days", "active_days",
                    "negative_days", "transactions", "missing_amounts",
                ]:
                    sql_types[column] = Integer()

            # Preventing duplicate loads
            # Clear old rows if this table exists. This makes reruns safe:
            # reloading won't keep adding duplicate household-months.
            # remove all rows from the table if it already exists in the database
            if inspect(connection).has_table(name, schema=schema_name):
                connection.execute(text(f'TRUNCATE TABLE {schema_name}."{name}"')) #Allows rerunns withouuts accumulating duplicates

            # pandas creates the SQL table the first time; later runs append
            # fresh rows after the TRUNCATE above.
            df.to_sql(
                name,
                con=connection,
                schema=schema_name,
                if_exists="append", 
                index=False, #dont insert pandas row index as a column in the database
                dtype=sql_types, # dictionary of column names and their corresponding SQLAlchemy types
                chunksize=1000, # banches of 1000 rows at a time to avoid memory issues
                method="multi", # combine multiple rows into a single INSERT statement for efficiency
            )

            # Verify that the row count in the database matches the CSV file.
            # data quality checjk 
            db_count = connection.execute(
                text(f'SELECT COUNT(*) FROM {schema_name}."{name}"')
            ).scalar_one()
            if db_count != len(df):
                raise ValueError(f"Row count does not match for {name}")

            
            # Add the primary key if the table does not have one already
            existing_key = inspect(connection).get_pk_constraint(
                name, schema=schema_name
            )

            if not existing_key["constrained_columns"]:
                key_columns = ", ".join(f'"{column}"' for column in keys)

                connection.execute(text(
                    f'ALTER TABLE {schema_name}."{name}" '
                    f'ADD CONSTRAINT "{name}_pk" PRIMARY KEY ({key_columns})'
                ))
            

            print(f"Loaded {name}: {db_count:,} rows")
            

    engine.dispose() # Close the database connection
    print("All five tables are ready in PostgreSQL (schema: diary_data).")

#Only execute load_tables() automatically when this file is run directly. 
if __name__ == "__main__":
    load_tables()
