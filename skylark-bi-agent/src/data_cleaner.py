"""
data_cleaner.py
Normalizes and cleans raw Monday.com data from both boards.
Handles: inconsistent dates, missing values, naming variations, messy numbers.
"""

import re
import pandas as pd
from datetime import datetime
from typing import Optional


# ─── Date Normalization ──────────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d %b %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
]


def parse_date(raw: str) -> Optional[str]:
    """Try multiple date formats; return ISO string or None."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or raw.lower() in ("n/a", "na", "-", "tbd", "nil"):
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None  # unparseable


# ─── Number Normalization ────────────────────────────────────────────────────

def parse_number(raw) -> Optional[float]:
    """Strip currency symbols, commas, spaces; return float or None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("n/a", "na", "-", "", "#value!"):
        return None
    s = re.sub(r"[₹$,\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


# ─── Status / Stage Normalization ────────────────────────────────────────────

DEAL_STATUS_MAP = {
    "open": "Open",
    "won": "Won",
    "dead": "Dead",
    "on hold": "On Hold",
    "on-hold": "On Hold",
}

SECTOR_ALIASES = {
    "renewables": "Renewables",
    "renewable": "Renewables",
    "solar": "Renewables",
    "wind": "Renewables",
    "mining": "Mining",
    "mine": "Mining",
    "powerline": "Powerline",
    "power line": "Powerline",
    "power-line": "Powerline",
    "railways": "Railways",
    "railway": "Railways",
    "rail": "Railways",
    "construction": "Construction",
    "dsp": "DSP",
    "tender": "Tender",
    "others": "Others",
    "other": "Others",
    "aviation": "Aviation",
    "manufacturing": "Manufacturing",
    "security and surveillance": "Security & Surveillance",
    "security & surveillance": "Security & Surveillance",
}

WO_STATUS_MAP = {
    "completed": "Completed",
    "ongoing": "Ongoing",
    "not started": "Not Started",
    "pause / struck": "Paused/Stuck",
    "paused/stuck": "Paused/Stuck",
    "partial completed": "Partially Completed",
    "partially completed": "Partially Completed",
    "executed until current month": "Ongoing",
}


def normalize_sector(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unknown"
    raw = str(raw).strip()
    if not raw or raw.lower() in ("nan", "none", ""):
        return "Unknown"
    key = raw.lower()
    return SECTOR_ALIASES.get(key, raw.title())


def normalize_deal_status(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unknown"
    raw = str(raw).strip()
    if not raw or raw.lower() in ("nan", "none", ""):
        return "Unknown"
    return DEAL_STATUS_MAP.get(raw.lower(), raw)


def normalize_wo_status(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unknown"
    raw = str(raw).strip()
    if not raw or raw.lower() in ("nan", "none", ""):
        return "Unknown"
    return WO_STATUS_MAP.get(raw.lower(), raw)


# ─── Deals Board Cleaner ─────────────────────────────────────────────────────

DEALS_COLUMN_MAP = {
    "Deal Name": "deal_name",
    "Name": "deal_name",
    "Owner code": "owner_code",
    "Client Code": "client_code",
    "Deal Status": "deal_status",
    "Close Date (A)": "close_date_actual",
    "Closure Probability": "closure_probability",
    "Masked Deal value": "deal_value",
    "Tentative Close Date": "tentative_close_date",
    "Deal Stage": "deal_stage",
    "Product deal": "product",
    "Sector/service": "sector",
    "Created Date": "created_date",
}


def clean_deals(records: list[dict]) -> pd.DataFrame:
    """
    Clean raw deal records from Monday.com.
    Returns a DataFrame with normalized columns.
    """
    rows = []
    issues = []

    for i, rec in enumerate(records):
        row = {}

        # Map column names
        for src_key, dest_key in DEALS_COLUMN_MAP.items():
            row[dest_key] = rec.get(src_key, rec.get("name", ""))

        # If deal_name is still empty, use item name
        if not row.get("deal_name"):
            row["deal_name"] = rec.get("name", f"Deal_{i}")

        # Skip header rows that leaked in (Monday import artifact)
        if row.get("deal_status") in ("Deal Status", "Owner code", "deal_status"):
            continue

        # Normalize fields
        row["deal_status"] = normalize_deal_status(row.get("deal_status", ""))
        row["sector"] = normalize_sector(row.get("sector", ""))
        row["deal_value"] = parse_number(row.get("deal_value"))
        row["close_date_actual"] = parse_date(row.get("close_date_actual"))
        row["tentative_close_date"] = parse_date(row.get("tentative_close_date"))
        row["created_date"] = parse_date(row.get("created_date"))

        # Closure probability: normalize to string label
        prob = str(row.get("closure_probability", "")).strip().lower()
        if prob in ("high", "medium", "low"):
            row["closure_probability"] = prob.title()
        else:
            row["closure_probability"] = None

        # Flag data quality issues
        if not row.get("deal_value"):
            issues.append(f"Row {i}: '{row['deal_name']}' missing deal value")
        if not row.get("sector") or row["sector"] == "Unknown":
            issues.append(f"Row {i}: '{row['deal_name']}' missing sector")

        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df[~df["deal_name"].isin(["Deal Status", ""])]
        # Deduplicate complete duplicates
        df = df.drop_duplicates()

    return df, issues


# ─── Work Orders Board Cleaner ────────────────────────────────────────────────

WO_COLUMN_MAP = {
    "Deal name masked": "deal_name",
    "Name": "deal_name",
    "Customer Name Code": "customer_code",
    "Serial #": "serial_no",
    "Nature of Work": "nature_of_work",
    "Execution Status": "execution_status",
    "Data Delivery Date": "data_delivery_date",
    "Date of PO/LOI": "po_date",
    "Document Type": "document_type",
    "Probable Start Date": "start_date",
    "Probable End Date": "end_date",
    "BD/KAM Personnel code": "owner_code",
    "Sector": "sector",
    "Type of Work": "type_of_work",
    "Is any Skylark software platform part of the client deliverables in this deal?": "skylark_platform",
    "Last invoice date": "last_invoice_date",
    "latest invoice no.": "invoice_no",
    "Amount in Rupees (Excl of GST) (Masked)": "amount_excl_gst",
    "Amount in Rupees (Incl of GST) (Masked)": "amount_incl_gst",
    "Billed Value in Rupees (Excl of GST.) (Masked)": "billed_excl_gst",
    "Billed Value in Rupees (Incl. of GST.) (Masked)": "billed_incl_gst",
    "Collected Amount in Rupees (Incl of GST.) (Masked)": "collected_amount",
    "Amount to be billed in Rs. (Exl. of GST) (Masked)": "unbilled_excl_gst",
    "Amount Receivable (Masked)": "amount_receivable",
    "WO Status (billed)": "wo_status",
    "Billing Status": "billing_status",
    "Expected Billing Month": "expected_billing_month",
    "Actual Billing Month": "actual_billing_month",
}


def clean_work_orders(records: list[dict]) -> pd.DataFrame:
    """
    Clean raw work order records from Monday.com.
    Returns a DataFrame with normalized columns.
    """
    rows = []
    issues = []

    for i, rec in enumerate(records):
        row = {}

        for src_key, dest_key in WO_COLUMN_MAP.items():
            val = rec.get(src_key, "")
            row[dest_key] = val if val else ""

        # Item name fallback
        if not row.get("deal_name"):
            row["deal_name"] = rec.get("name", f"WO_{i}")

        # Skip empty / blank rows
        if not row.get("deal_name") and not row.get("serial_no"):
            continue

        # Normalize
        row["sector"] = normalize_sector(row.get("sector", ""))
        row["execution_status"] = normalize_wo_status(row.get("execution_status", ""))

        # Numeric fields
        for num_col in ["amount_excl_gst", "amount_incl_gst", "billed_excl_gst",
                         "billed_incl_gst", "collected_amount", "unbilled_excl_gst",
                         "amount_receivable"]:
            row[num_col] = parse_number(row.get(num_col))

        # Date fields
        for date_col in ["po_date", "start_date", "end_date",
                          "last_invoice_date", "data_delivery_date"]:
            row[date_col] = parse_date(row.get(date_col))

        # Quality flags
        if row.get("amount_excl_gst") is None:
            issues.append(f"Row {i}: '{row['deal_name']}' has no contract amount")

        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.drop_duplicates(subset=["serial_no"], keep="first") if "serial_no" in df.columns else df

    return df, issues


# ─── Summary Helpers ─────────────────────────────────────────────────────────

def summarize_data_quality(deals_issues: list, wo_issues: list) -> str:
    total = len(deals_issues) + len(wo_issues)
    if total == 0:
        return "✅ No data quality issues detected."
    lines = [f"⚠️ **{total} data quality notes:**"]
    for issue in deals_issues[:5]:
        lines.append(f"  - [Deals] {issue}")
    for issue in wo_issues[:5]:
        lines.append(f"  - [Work Orders] {issue}")
    if total > 10:
        lines.append(f"  _...and {total - 10} more issues (not shown)_")
    return "\n".join(lines)
