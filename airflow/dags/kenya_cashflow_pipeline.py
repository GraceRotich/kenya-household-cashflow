
from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

# Project location
PROJECT = "/home/grace/projects/kenya-household-cashflow"

# Use the project's Python and dbt installations
PYTHON = f"{PROJECT}/.venv/bin/python"
DBT = f"{PROJECT}/.venv/bin/dbt"

# Protected local PostgreSQL credentials
PG_ENV = "/home/grace/airflow/pg.env"

# Define the pipeline
with DAG(
    dag_id="kenya_cashflow_pipeline",
    description="Kenya Financial Diaries ETL and analytics pipeline",
    start_date=datetime(2026, 11, 15),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["kenya", "data-engineering"],
) as dag:

    # Task 1: Clean and aggregate the raw transactions
    clean_data = BashOperator(
        task_id="clean_and_aggregate",
        bash_command=f"{PYTHON} src/etl.py",
        cwd=PROJECT,
    )

    # Task 2: Load processed data into PostgreSQL
    load_data = BashOperator(
        task_id="load_postgresql",
        bash_command=f"source {PG_ENV} && {PYTHON} src/load.py",
        cwd=PROJECT,
    )

    # Task 3: Build dbt views and run data tests
    build_dbt = BashOperator(
        task_id="build_dbt_models",
        bash_command=f"source {PG_ENV} && {DBT} build",
        cwd=f"{PROJECT}/kenya_cashflow_dbt",
    )

    # Run the tasks in this order
    clean_data >> load_data >> build_dbt
