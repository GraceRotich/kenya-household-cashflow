"""Clean the Kenya Financial Diaries data and build tables for our dashboard.

Run from the project folder:
    python src/etl.py

Or give the input file explicitly:
    python src/etl.py --input data/raw/diaries_transactions_all.zip

The original notebook explains how we arrived at these rules.
"""

import argparse
import json
from pathlib import Path

import pandas as pd


# These payment methods are treated as monetary transactions in our MVP.
# Credit and in-kind transactions are kept separately.
monetary_modes = [
    "Cash",
    "Mobile money transfer (M-PESA, Airtel Money, Orange Money, Yu Cash, Tangaza, etc)",
    "Transfer into bank, SACCO, or MFI account",
    "Cheque or money order",
    "Debit card",
    "Standing order",
    "Wire over Western Union, Money Gram",
]

financial_purposes = {
    "Deposit on financial asset": "asset_deposit",
    "Withdrawal on financial asset": "asset_withdrawal",
    "New borrowing on financial liability": "new_borrowing",
    "Repayment on financial liability": "liability_repayment",
}


def clean_transactions(raw):
    """Keep valid source rows and label the different kinds of activity."""

    # Keep the source column names before adding any new ones.
    # A transaction ID can repeat, so we also need our own row ID.
    original_columns = raw.columns.tolist()
    df = raw.copy()
    df["source_row_id"] = range(1, len(df) + 1)

    # Exclude identical copies of a source row, but keep the first occurrence.
    # This is the same duplicate rule used in our notebook.
    df["is_exact_duplicate"] = df.duplicated(subset=original_columns)
    duplicate_count = int(df["is_exact_duplicate"].sum())
    df = df.loc[~df["is_exact_duplicate"]].copy()

    # Convert dates and amounts to the types we need for calculations.
    df["transaction_date"] = pd.to_datetime(
        df["trx_date"], format="%d%b%Y", errors="coerce"
    )
    amount = pd.to_numeric(df["trx_value_kes"], errors="coerce")

    # Stop rather than quietly lose dates or turn invalid text into missing amounts.
    if df["transaction_date"].isna().any() or df["hh_ids"].isna().any():
        raise ValueError("Missing household IDs or invalid transaction dates")
    if (df["trx_value_kes"].notna() & amount.isna()).any():
        raise ValueError("Some transaction amounts are not numeric")

    df["trx_value_kes"] = amount
    df["amount_is_missing"] = amount.isna()
    df["amount_is_zero"] = amount.eq(0)
    df["amount_is_negative"] = amount.lt(0)

    # Starting and closing balances are observations of an account balance.
    # We don't want to mistake them for new money received or spent.
    account_balance = df["account_startclose_balance"].isin(["Start", "Close"])
    mode_balance = df["trx_mode_desc"].isin(["STARTING BALANCE", "CLOSING BALANCE"])
    df["is_balance_record"] = account_balance | mode_balance
    df["balance_label_conflict"] = account_balance != mode_balance
    df["balance_needs_review"] = df["is_balance_record"] & (
        df["trx_class_code"] != "findev"
    )

    # Classify transactions using the categories in the source data.
    cls = df["trx_class_code"]
    family = df["trx_family_desc"]
    direction = df["trx_direction"]
    not_balance = ~df["is_balance_record"]

    df["activity_group"] = "needs_review"
    df.loc[not_balance & (cls == "opex"), "activity_group"] = "household_expenditure"
    df.loc[not_balance & (cls == "income") & (direction == "Inflow"), "activity_group"] = "income_inflow"
    df.loc[not_balance & (cls == "income") & (direction == "Outflow"), "activity_group"] = "income_outflow"
    df.loc[not_balance & (family == "Resources Received") & (direction == "Inflow"), "activity_group"] = "transfer_received"
    df.loc[not_balance & (family == "Resources Given") & (direction == "Outflow"), "activity_group"] = "transfer_given"
    df.loc[not_balance & (family == "Passthrough Income"), "activity_group"] = "passthrough"
    df.loc[not_balance & (cls == "findev"), "activity_group"] = "financial_device"
    df.loc[not_balance & (cls == "assets"), "activity_group"] = "asset_activity"
    df.loc[not_balance & (cls == "cash"), "activity_group"] = "cash_record"
    df.loc[~not_balance, "activity_group"] = "balance_record"

    if (df["activity_group"] == "needs_review").any():
        raise ValueError("Some transactions did not get an activity category")

    # Separate income receipts from the costs of running a business or farm.
    income_in = df["activity_group"] == "income_inflow"
    income_out = df["activity_group"] == "income_outflow"
    df["income_component"] = pd.NA
    df.loc[income_in, "income_component"] = "income_source_receipt"
    df.loc[income_in & (family == "Non-employment"), "income_component"] = "nonemployment_support"
    df.loc[income_out, "income_component"] = "other_income_outflow"
    df.loc[
        income_out & family.isin(["Self-employment", "Agriculture"]),
        "income_component",
    ] = "business_agriculture_cost"

    # Name the savings, borrowing and repayment operations.
    is_financial = df["activity_group"] == "financial_device"
    df["financial_activity"] = pd.NA
    df.loc[is_financial, "financial_activity"] = (
        df.loc[is_financial, "trx_prx_purpose_fd"]
        .map(financial_purposes)
        .fillna("purpose_not_recorded")
    )

    # Work out which recorded activities may involve an actual money payment.
    selected = (
        df["activity_group"].isin(
            ["household_expenditure", "transfer_received", "transfer_given"]
        )
        | df["income_component"].isin(
            ["income_source_receipt", "business_agriculture_cost"]
        )
    )
    mode = df["trx_mode_desc"]
    df["payment_group"] = pd.NA
    df.loc[selected, "payment_group"] = "other_or_unknown"
    df.loc[selected & mode.isin(monetary_modes), "payment_group"] = "monetary"
    df.loc[selected & (mode == "Purchase on credit/arrears"), "payment_group"] = "credit"
    df.loc[
        selected & (mode == "In-kind (trade, good, service--NOT MONEY)"),
        "payment_group",
    ] = "in_kind"

    # Our core monetary margin uses income, business costs, household spending
    # and transfers. It does NOT include borrowing or savings withdrawals.
    money = df["payment_group"].eq("monetary").fillna(False)
    money_in = (
        df["income_component"].eq("income_source_receipt").fillna(False)
        | (df["activity_group"] == "transfer_received")
    )
    money_out = (
        df["income_component"].eq("business_agriculture_cost").fillna(False)
        | df["activity_group"].isin(["household_expenditure", "transfer_given"])
    )

    if (money_in & money_out).any():
        raise ValueError("An activity was classified as both incoming and outgoing")

    df["core_in_kes"] = amount.where(money & money_in, 0)
    df["core_out_kes"] = amount.where(money & money_out, 0)
    df["core_net_kes"] = df["core_in_kes"] - df["core_out_kes"]
    df["core_eligible"] = money & (money_in | money_out)
    df["core_flow_missing"] = df["core_eligible"] & amount.isna()

    return df, duplicate_count


def make_summaries(df):
    """Make five tables that will be loaded into PostgreSQL."""

    # First make one row per household and recorded transaction date.
    daily = df.groupby(["hh_ids", "transaction_date"], as_index=False).agg(
        inflows_kes=("core_in_kes", "sum"),
        outflows_kes=("core_out_kes", "sum"),
        margin_kes=("core_net_kes", "sum"),
        eligible_transactions=("core_eligible", "sum"),
        missing_amounts=("core_flow_missing", "sum"),
    )
    daily["has_core_activity"] = daily["eligible_transactions"] > 0
    daily["negative_day"] = daily["has_core_activity"] & (daily["margin_kes"] < 0)
    daily["week_start"] = daily["transaction_date"].dt.to_period("W-SUN").dt.start_time
    daily["month_start"] = daily["transaction_date"].dt.to_period("M").dt.to_timestamp()

    # Add the daily amounts into weeks (Monday to Sunday) and calendar months.
    totals = {
        "inflows_kes": ("inflows_kes", "sum"),
        "outflows_kes": ("outflows_kes", "sum"),
        "margin_kes": ("margin_kes", "sum"),
        "recorded_days": ("transaction_date", "count"),
        "active_days": ("has_core_activity", "sum"),
        "negative_days": ("negative_day", "sum"),
        "transactions": ("eligible_transactions", "sum"),
        "missing_amounts": ("missing_amounts", "sum"),
    }
    weekly = daily.groupby(["hh_ids", "week_start"], as_index=False).agg(**totals)
    monthly = daily.groupby(["hh_ids", "month_start"], as_index=False).agg(**totals)

    monthly["negative_month"] = (
        (monthly["transactions"] > 0) & (monthly["margin_kes"] < 0)
    )
    monthly["negative_day_share"] = (
        monthly["negative_days"] / monthly["active_days"].replace(0, float("nan"))
    )

    # Keep spending categories separate from the cash-flow proxy.
    # trx_type_desc is more detailed than trx_family_desc (e.g. groceries).
    spending = df[df["activity_group"] == "household_expenditure"].copy()
    spending["month_start"] = spending["transaction_date"].dt.to_period("M").dt.to_timestamp()
    spending["category"] = spending["trx_type_desc"].fillna("Unspecified")
    spending_monthly = spending.groupby(
        ["hh_ids", "month_start", "category", "payment_group"],
        as_index=False, dropna=False,
    ).agg(
        transactions=("source_row_id", "count"),
        amount_kes=("trx_value_kes", lambda x: x.sum(min_count=1)),
        missing_amounts=("trx_value_kes", lambda x: x.isna().sum()),
    )

    # Track deposits, withdrawals, new loans and repayments separately.
    # An account deposit isn't automatically counted as household expenditure.
    financial = df[df["activity_group"] == "financial_device"].copy()
    financial["month_start"] = financial["transaction_date"].dt.to_period("M").dt.to_timestamp()
    financial_monthly = financial.groupby(
        ["hh_ids", "month_start", "financial_activity"],
        as_index=False, dropna=False,
    ).agg(
        transactions=("source_row_id", "count"),
        amount_kes=("trx_value_kes", lambda x: x.sum(min_count=1)),
        missing_amounts=("trx_value_kes", lambda x: x.isna().sum()),
    )

    tables = {
        "household_daily": daily.drop(columns=["week_start", "month_start"]),
        "household_weekly": weekly,
        "household_monthly": monthly,
        "spending_monthly": spending_monthly,
        "financial_monthly": financial_monthly,
    }

    # A simple reconciliation: grouping rows shouldn't change total amounts.
    for table in [daily, weekly, monthly]:
        for total_col, source_col in [
            ("inflows_kes", "core_in_kes"),
            ("outflows_kes", "core_out_kes"),
            ("margin_kes", "core_net_kes"),
        ]:
            assert abs(table[total_col].sum() - df[source_col].sum()) < 0.01

    assert not daily.duplicated(["hh_ids", "transaction_date"]).any()
    assert not weekly.duplicated(["hh_ids", "week_start"]).any()
    assert not monthly.duplicated(["hh_ids", "month_start"]).any()
    assert weekly["recorded_days"].sum() == len(daily)
    assert monthly["recorded_days"].sum() == len(daily)
    assert spending_monthly["transactions"].sum() == len(spending)
    assert financial_monthly["transactions"].sum() == len(financial)

    return tables


def main():
    # Allow the script to work from VS Code, the terminal or Airflow later.
    project = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=project / "data/raw/diaries_transactions_all.csv")
    parser.add_argument("--output", type=Path, default=project / "data/processed")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"File not found: {args.input}")

    args.output.mkdir(parents=True, exist_ok=True)
    print("Reading the source data...")
    raw = pd.read_csv(
        args.input, low_memory=False, dtype={"hh_ids": "string", "trx_id": "string"}
    )

    print("Cleaning and classifying transactions...")
    df, duplicate_count = clean_transactions(raw)
    del raw

    print("Building the household summaries...")
    tables = make_summaries(df)

    for name, table in tables.items():
        table.to_csv(args.output / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"Saved {name}: {len(table):,} rows")

    # Save a short report so we can quote checked figures in the presentation.
    report = {
        "transactions_after_deduplication": len(df),
        "candidate_duplicates_excluded": duplicate_count,
        "households": int(df["hh_ids"].nunique()),
        "household_months": len(tables["household_monthly"]),
        "negative_margin_months": int(tables["household_monthly"]["negative_month"].sum()),
        "core_inflows_kes": float(df["core_in_kes"].sum()),
        "core_outflows_kes": float(df["core_out_kes"].sum()),
        "core_margin_kes": float(df["core_net_kes"].sum()),
        "missing_core_amounts": int(df["core_flow_missing"].sum()),
        "balance_label_conflicts": int(df["balance_label_conflict"].sum()),
        "balance_records_needing_review": int(df["balance_needs_review"].sum()),
    }
    (args.output / "validation_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("All summary checks passed.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
