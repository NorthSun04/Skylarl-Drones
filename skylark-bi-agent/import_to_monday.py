"""
import_to_monday.py
------------------
Script to import Deal Funnel and Work Orders CSVs into Monday.com.
Run this ONCE after setting up your Monday.com boards.

Usage:
    python import_to_monday.py --deals deal_funnel.csv --workorders work_orders.csv

Requirements:
    pip install requests pandas python-dotenv
"""

import os
import sys
import json
import time
import argparse
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.monday.com/v2"
TOKEN = os.environ.get("MONDAY_API_TOKEN", "")

HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json",
    "API-Version": "2024-01",
}


def gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def create_board(name: str, board_kind: str = "public") -> str:
    """Create a board and return its ID."""
    query = """
    mutation($name: String!, $kind: BoardKind!) {
        create_board(board_name: $name, board_kind: $kind) { id }
    }
    """
    result = gql(query, {"name": name, "kind": board_kind})
    board_id = result["data"]["create_board"]["id"]
    print(f"✅ Created board: '{name}' (ID: {board_id})")
    return board_id


def add_column(board_id: str, title: str, col_type: str) -> str:
    """Add a column to a board, return column ID."""
    query = """
    mutation($board_id: ID!, $title: String!, $type: ColumnType!) {
        create_column(board_id: $board_id, title: $title, column_type: $type) { id }
    }
    """
    result = gql(query, {"board_id": board_id, "title": title, "type": col_type})
    return result["data"]["create_column"]["id"]


def create_item(board_id: str, item_name: str, column_values: dict) -> str:
    """Create an item on the board."""
    col_vals_str = json.dumps(json.dumps(column_values))
    query = f"""
    mutation {{
        create_item(
            board_id: {board_id},
            item_name: {json.dumps(item_name)},
            column_values: {col_vals_str}
        ) {{ id }}
    }}
    """
    result = gql(query)
    if "errors" in result:
        return None
    return result.get("data", {}).get("create_item", {}).get("id")


# ─── Deals Import ─────────────────────────────────────────────────────────────

DEALS_COLUMNS = [
    ("Owner Code", "text"),
    ("Client Code", "text"),
    ("Deal Status", "status"),
    ("Close Date (Actual)", "date"),
    ("Closure Probability", "dropdown"),
    ("Deal Value (Masked)", "numbers"),
    ("Tentative Close Date", "date"),
    ("Deal Stage", "status"),
    ("Product", "text"),
    ("Sector", "dropdown"),
    ("Created Date", "date"),
]


def import_deals(csv_path: str) -> str:
    df = pd.read_csv(csv_path, skiprows=0)
    df = df.dropna(how="all")

    # Remove rows that are actually header repetitions
    df = df[df["Deal Name"] != "Deal Status"]
    df = df[df["Deal Name"].notna()]

    board_id = create_board("Deal Funnel — Skylark")

    # Create columns
    col_ids = {}
    for col_name, col_type in DEALS_COLUMNS:
        try:
            col_id = add_column(board_id, col_name, col_type)
            col_ids[col_name] = col_id
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Could not create column '{col_name}': {e}")

    print(f"\nImporting {len(df)} deal records...")

    success = 0
    for _, row in df.iterrows():
        item_name = str(row.get("Deal Name", "Unnamed Deal"))
        if not item_name or item_name == "nan":
            item_name = "Unnamed Deal"

        col_values = {}

        # Text / date / number mappings
        def safe(val):
            return str(val).strip() if pd.notna(val) and str(val) != "nan" else ""

        if col_ids.get("Owner Code"):
            col_values[col_ids["Owner Code"]] = safe(row.get("Owner code", ""))
        if col_ids.get("Client Code"):
            col_values[col_ids["Client Code"]] = safe(row.get("Client Code", ""))
        if col_ids.get("Deal Status"):
            col_values[col_ids["Deal Status"]] = {"label": safe(row.get("Deal Status", "Open"))}
        if col_ids.get("Deal Value (Masked)"):
            try:
                v = float(str(row.get("Masked Deal value", "")).replace(",", ""))
                col_values[col_ids["Deal Value (Masked)"]] = v
            except (ValueError, TypeError):
                pass
        if col_ids.get("Tentative Close Date"):
            d = safe(row.get("Tentative Close Date", ""))
            if d:
                col_values[col_ids["Tentative Close Date"]] = {"date": d}
        if col_ids.get("Deal Stage"):
            col_values[col_ids["Deal Stage"]] = {"label": safe(row.get("Deal Stage", ""))}
        if col_ids.get("Product"):
            col_values[col_ids["Product"]] = safe(row.get("Product deal", ""))
        if col_ids.get("Sector"):
            col_values[col_ids["Sector"]] = {"label": safe(row.get("Sector/service", ""))}
        if col_ids.get("Closure Probability"):
            col_values[col_ids["Closure Probability"]] = {"label": safe(row.get("Closure Probability", ""))}

        item_id = create_item(board_id, item_name, col_values)
        if item_id:
            success += 1
        time.sleep(0.25)  # Rate limiting

    print(f"✅ Deals import complete: {success}/{len(df)} items created.")
    print(f"📋 Deals Board ID: {board_id}")
    return board_id


# ─── Work Orders Import ───────────────────────────────────────────────────────

WO_COLUMNS = [
    ("Customer Code", "text"),
    ("Serial No", "text"),
    ("Nature of Work", "text"),
    ("Execution Status", "status"),
    ("Date of PO/LOI", "date"),
    ("Start Date", "date"),
    ("End Date", "date"),
    ("Owner Code", "text"),
    ("Sector", "dropdown"),
    ("Type of Work", "text"),
    ("Contract Amount (Excl GST)", "numbers"),
    ("Billed Amount (Excl GST)", "numbers"),
    ("Collected Amount", "numbers"),
    ("Amount Receivable", "numbers"),
    ("Billing Status", "status"),
    ("WO Status", "status"),
]


def import_work_orders(csv_path: str) -> str:
    # Skip first blank row
    df = pd.read_csv(csv_path, skiprows=1)
    df = df.dropna(how="all")
    df = df[df.iloc[:, 0].notna()]

    board_id = create_board("Work Orders — Skylark")

    col_ids = {}
    for col_name, col_type in WO_COLUMNS:
        try:
            col_id = add_column(board_id, col_name, col_type)
            col_ids[col_name] = col_id
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Could not create column '{col_name}': {e}")

    print(f"\nImporting {len(df)} work order records...")
    success = 0

    for _, row in df.iterrows():
        item_name = str(row.get("Deal name masked", row.iloc[0])).strip()
        if not item_name or item_name == "nan":
            item_name = "Unnamed WO"

        def safe(val):
            return str(val).strip() if pd.notna(val) and str(val) != "nan" else ""

        def safe_num(val):
            try:
                return float(str(val).replace(",", "").replace("₹", "").strip())
            except (ValueError, TypeError):
                return None

        col_values = {}

        if col_ids.get("Customer Code"):
            col_values[col_ids["Customer Code"]] = safe(row.get("Customer Name Code", ""))
        if col_ids.get("Serial No"):
            col_values[col_ids["Serial No"]] = safe(row.get("Serial #", ""))
        if col_ids.get("Nature of Work"):
            col_values[col_ids["Nature of Work"]] = safe(row.get("Nature of Work", ""))
        if col_ids.get("Execution Status"):
            col_values[col_ids["Execution Status"]] = {"label": safe(row.get("Execution Status", ""))}
        if col_ids.get("Sector"):
            col_values[col_ids["Sector"]] = {"label": safe(row.get("Sector", ""))}
        if col_ids.get("Type of Work"):
            col_values[col_ids["Type of Work"]] = safe(row.get("Type of Work", ""))
        if col_ids.get("Owner Code"):
            col_values[col_ids["Owner Code"]] = safe(row.get("BD/KAM Personnel code", ""))

        for num_col, src_col in [
            ("Contract Amount (Excl GST)", "Amount in Rupees (Excl of GST) (Masked)"),
            ("Billed Amount (Excl GST)", "Billed Value in Rupees (Excl of GST.) (Masked)"),
            ("Collected Amount", "Collected Amount in Rupees (Incl of GST.) (Masked)"),
            ("Amount Receivable", "Amount Receivable (Masked)"),
        ]:
            if col_ids.get(num_col):
                v = safe_num(row.get(src_col, ""))
                if v is not None:
                    col_values[col_ids[num_col]] = v

        if col_ids.get("Billing Status"):
            col_values[col_ids["Billing Status"]] = {"label": safe(row.get("Billing Status", ""))}
        if col_ids.get("WO Status"):
            col_values[col_ids["WO Status"]] = {"label": safe(row.get("WO Status (billed)", ""))}

        item_id = create_item(board_id, item_name, col_values)
        if item_id:
            success += 1
        time.sleep(0.25)

    print(f"✅ Work Orders import complete: {success}/{len(df)} items created.")
    print(f"📋 Work Orders Board ID: {board_id}")
    return board_id


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import CSVs into Monday.com")
    parser.add_argument("--deals", default="../deal_funnel.csv", help="Path to deal funnel CSV")
    parser.add_argument("--workorders", default="../work_orders.csv", help="Path to work orders CSV")
    parser.add_argument("--only", choices=["deals", "workorders"], help="Import only one board")
    args = parser.parse_args()

    if not TOKEN:
        print("❌ MONDAY_API_TOKEN not set. Please set it in .env")
        sys.exit(1)

    deals_board_id = None
    wo_board_id = None

    if args.only != "workorders":
        print("\n📊 Importing Deals...")
        deals_board_id = import_deals(args.deals)

    if args.only != "deals":
        print("\n🔧 Importing Work Orders...")
        wo_board_id = import_work_orders(args.workorders)

    print("\n" + "=" * 60)
    print("✅ Import complete! Add these to your .env file:")
    if deals_board_id:
        print(f"MONDAY_DEALS_BOARD_ID={deals_board_id}")
    if wo_board_id:
        print(f"MONDAY_WORK_ORDERS_BOARD_ID={wo_board_id}")
    print("=" * 60)
