"""
bi_tools.py
Business Intelligence tools called by the LLM agent.
Each function queries Monday.com, cleans data, and returns structured insights.
"""

import os
import pandas as pd
from src.monday_client import get_board_as_records
from src.data_cleaner import (
    clean_deals, clean_work_orders, summarize_data_quality
)

# Board IDs are loaded from env vars (set after Monday.com import)
DEALS_BOARD_ID = os.environ.get("MONDAY_DEALS_BOARD_ID", "")
WORK_ORDERS_BOARD_ID = os.environ.get("MONDAY_WORK_ORDERS_BOARD_ID", "")


# ─── Data Loaders (cached per session) ───────────────────────────────────────

_cache: dict = {}


def _load_deals() -> tuple[pd.DataFrame, list]:
    if "deals" not in _cache:
        records = get_board_as_records(DEALS_BOARD_ID)
        df, issues = clean_deals(records)
        _cache["deals"] = (df, issues)
    return _cache["deals"]


def _load_work_orders() -> tuple[pd.DataFrame, list]:
    if "work_orders" not in _cache:
        records = get_board_as_records(WORK_ORDERS_BOARD_ID)
        df, issues = clean_work_orders(records)
        _cache["work_orders"] = (df, issues)
    return _cache["work_orders"]


def invalidate_cache():
    """Force fresh fetch on next call."""
    _cache.clear()


def fmt_inr(val) -> str:
    """Format a number as Indian Rupees (Cr)."""
    if val is None or pd.isna(val):
        return "N/A"
    cr = val / 1_00_00_000
    if cr >= 1:
        return f"₹{cr:,.2f} Cr"
    lakh = val / 1_00_000
    return f"₹{lakh:,.2f} L"


# ─── 1. Pipeline Summary ──────────────────────────────────────────────────────

def get_pipeline_summary(sector: str = None, status: str = None) -> str:
    """
    High-level pipeline overview.
    Optional filters: sector, status (Open/Won/Dead/On Hold).
    """
    df, issues = _load_deals()
    if df.empty:
        return "❌ Could not load deals data from Monday.com."

    original_count = len(df)
    if sector:
        df = df[df["sector"].str.lower() == sector.lower()]
    if status:
        df = df[df["deal_status"].str.lower() == status.lower()]

    if df.empty:
        filters = f"sector='{sector}'" if sector else ""
        filters += f" status='{status}'" if status else ""
        return f"No deals found matching filters: {filters.strip()}."

    total_deals = len(df)
    total_value = df["deal_value"].sum(skipna=True)
    open_deals = df[df["deal_status"] == "Open"]
    won_deals = df[df["deal_status"] == "Won"]
    dead_deals = df[df["deal_status"] == "Dead"]

    open_value = open_deals["deal_value"].sum(skipna=True)
    won_value = won_deals["deal_value"].sum(skipna=True)

    by_stage = (
        df[df["deal_status"] == "Open"]
        .groupby("deal_stage")["deal_value"]
        .agg(count="count", value="sum")
        .sort_values("value", ascending=False)
        .head(6)
    )

    lines = [
        f"## 📊 Pipeline Summary{f' — {sector}' if sector else ''}",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Deals | {total_deals:,} |",
        f"| Open Deals | {len(open_deals):,} |",
        f"| Won Deals | {len(won_deals):,} |",
        f"| Dead Deals | {len(dead_deals):,} |",
        f"| Open Pipeline Value | {fmt_inr(open_value)} |",
        f"| Won Revenue | {fmt_inr(won_value)} |",
        f"| Total Portfolio Value | {fmt_inr(total_value)} |",
    ]

    if not by_stage.empty:
        lines += ["", "**Top Open Deal Stages:**"]
        for stage, row_ in by_stage.iterrows():
            lines.append(f"  - {stage}: {int(row_['count'])} deals — {fmt_inr(row_['value'])}")

    dq = summarize_data_quality(issues, [])
    if "⚠️" in dq:
        lines += ["", dq]

    return "\n".join(lines)


# ─── 2. Sector Breakdown ──────────────────────────────────────────────────────

def get_sector_breakdown(board: str = "deals") -> str:
    """
    Break down pipeline/revenue by sector.
    board: 'deals' or 'work_orders'
    """
    if board == "work_orders":
        df, issues = _load_work_orders()
        if df.empty:
            return "❌ Could not load work orders data."
        grouped = (
            df.groupby("sector")
            .agg(
                count=("deal_name", "count"),
                total_value=("amount_excl_gst", "sum"),
                collected=("collected_amount", "sum"),
            )
            .sort_values("total_value", ascending=False)
        )
        title = "Work Orders"
    else:
        df, issues = _load_deals()
        if df.empty:
            return "❌ Could not load deals data."
        grouped = (
            df[df["deal_status"] == "Open"]
            .groupby("sector")
            .agg(count=("deal_name", "count"), total_value=("deal_value", "sum"))
            .sort_values("total_value", ascending=False)
        )
        title = "Open Deals"

    lines = [f"## 🗂️ Sector Breakdown — {title}", ""]
    if grouped.empty:
        return f"No data found."

    lines.append("| Sector | Count | Value |")
    lines.append("|--------|-------|-------|")
    for sector, row_ in grouped.iterrows():
        val = fmt_inr(row_.get("total_value", 0))
        lines.append(f"| {sector} | {int(row_['count'])} | {val} |")

    return "\n".join(lines)


# ─── 3. Revenue & Collections ────────────────────────────────────────────────

def get_revenue_summary(sector: str = None) -> str:
    """
    Revenue analysis from Work Orders board.
    Shows: total contract value, billed, collected, outstanding AR.
    """
    df, issues = _load_work_orders()
    if df.empty:
        return "❌ Could not load work orders data."

    if sector:
        df = df[df["sector"].str.lower() == sector.lower()]
        if df.empty:
            return f"No work orders found for sector: '{sector}'."

    total_contract = df["amount_excl_gst"].sum(skipna=True)
    total_billed = df["billed_excl_gst"].sum(skipna=True)
    total_collected = df["collected_amount"].sum(skipna=True)
    total_ar = df["amount_receivable"].sum(skipna=True)
    total_unbilled = df["unbilled_excl_gst"].sum(skipna=True)

    by_status = (
        df.groupby("execution_status")
        .agg(
            count=("deal_name", "count"),
            value=("amount_excl_gst", "sum"),
        )
        .sort_values("count", ascending=False)
    )

    lines = [
        f"## 💰 Revenue Summary{f' — {sector}' if sector else ''}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Contract Value (Excl. GST) | {fmt_inr(total_contract)} |",
        f"| Billed So Far | {fmt_inr(total_billed)} |",
        f"| Collected | {fmt_inr(total_collected)} |",
        f"| Accounts Receivable (AR) | {fmt_inr(total_ar)} |",
        f"| Unbilled Amount | {fmt_inr(total_unbilled)} |",
    ]

    if not by_status.empty:
        lines += ["", "**Work Orders by Execution Status:**"]
        for status, row_ in by_status.iterrows():
            lines.append(f"  - {status}: {int(row_['count'])} orders — {fmt_inr(row_['value'])}")

    dq = summarize_data_quality([], issues)
    if "⚠️" in dq:
        lines += ["", dq]

    return "\n".join(lines)


# ─── 4. Win Rate Analysis ────────────────────────────────────────────────────

def get_win_rate_analysis(sector: str = None) -> str:
    """
    Analyse win/loss/open rates from the deals pipeline.
    """
    df, issues = _load_deals()
    if df.empty:
        return "❌ Could not load deals data."

    if sector:
        df = df[df["sector"].str.lower() == sector.lower()]
        if df.empty:
            return f"No deals found for sector: '{sector}'."

    total = len(df)
    won = len(df[df["deal_status"] == "Won"])
    dead = len(df[df["deal_status"] == "Dead"])
    open_ = len(df[df["deal_status"] == "Open"])

    win_rate = (won / (won + dead) * 100) if (won + dead) > 0 else 0
    conversion = (won / total * 100) if total > 0 else 0

    # Sector-wise win rates
    sector_wr = (
        df.groupby("sector")["deal_status"]
        .value_counts()
        .unstack(fill_value=0)
        .assign(
            win_rate=lambda x: (
                x.get("Won", 0) / (x.get("Won", 0) + x.get("Dead", 0)).replace(0, 1) * 100
            ).round(1)
        )
        .sort_values("win_rate", ascending=False)
    )

    lines = [
        f"## 🏆 Win Rate Analysis{f' — {sector}' if sector else ''}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Deals | {total:,} |",
        f"| Won | {won:,} |",
        f"| Dead/Lost | {dead:,} |",
        f"| Open | {open_:,} |",
        f"| Win Rate (vs. closed) | {win_rate:.1f}% |",
        f"| Overall Conversion | {conversion:.1f}% |",
    ]

    if "win_rate" in sector_wr.columns and not sector_wr.empty:
        lines += ["", "**Win Rate by Sector:**"]
        lines.append("| Sector | Won | Lost | Win Rate |")
        lines.append("|--------|-----|------|----------|")
        for sec, row_ in sector_wr.iterrows():
            w = int(row_.get("Won", 0))
            d = int(row_.get("Dead", 0))
            wr = row_.get("win_rate", 0)
            lines.append(f"| {sec} | {w} | {d} | {wr:.1f}% |")

    return "\n".join(lines)


# ─── 5. Operational Metrics ───────────────────────────────────────────────────

def get_operational_metrics(sector: str = None) -> str:
    """
    Work order operational health: status distribution, stuck/paused projects.
    """
    df, issues = _load_work_orders()
    if df.empty:
        return "❌ Could not load work orders data."

    if sector:
        df = df[df["sector"].str.lower() == sector.lower()]
        if df.empty:
            return f"No work orders found for sector: '{sector}'."

    total = len(df)
    completed = len(df[df["execution_status"] == "Completed"])
    ongoing = len(df[df["execution_status"] == "Ongoing"])
    stuck = len(df[df["execution_status"] == "Paused/Stuck"])
    not_started = len(df[df["execution_status"] == "Not Started"])

    # Nature of work breakdown
    work_type_counts = (
        df.groupby("type_of_work")
        .agg(count=("deal_name", "count"), value=("amount_excl_gst", "sum"))
        .sort_values("count", ascending=False)
        .head(8)
    )

    # Billing status
    if "billing_status" in df.columns:
        billing_dist = df["billing_status"].value_counts().head(5)
    else:
        billing_dist = pd.Series(dtype=int)

    lines = [
        f"## ⚙️ Operational Metrics{f' — {sector}' if sector else ''}",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| Total Work Orders | {total:,} |",
        f"| Completed | {completed:,} |",
        f"| Ongoing | {ongoing:,} |",
        f"| Paused / Stuck | {stuck:,} |",
        f"| Not Started | {not_started:,} |",
    ]

    if not work_type_counts.empty:
        lines += ["", "**Work Type Distribution:**"]
        for wtype, row_ in work_type_counts.iterrows():
            lines.append(f"  - {wtype}: {int(row_['count'])} orders ({fmt_inr(row_['value'])})")

    if not billing_dist.empty:
        lines += ["", "**Billing Status:**"]
        for bstatus, cnt in billing_dist.items():
            lines.append(f"  - {bstatus}: {cnt}")

    return "\n".join(lines)


# ─── 6. Accounts Receivable Priority ─────────────────────────────────────────

def get_ar_priority() -> str:
    """
    List high-priority accounts receivable from Work Orders.
    """
    df, issues = _load_work_orders()
    if df.empty:
        return "❌ Could not load work orders data."

    # Filter AR Priority accounts
    if "AR Priority account" in df.columns:
        priority_df = df[df["AR Priority account"].str.lower() == "priority"]
    else:
        priority_df = df[df["amount_receivable"] > 0].nlargest(10, "amount_receivable")

    if priority_df.empty:
        return "No AR priority accounts flagged."

    lines = ["## 🚨 AR Priority Accounts", ""]
    lines.append("| Deal | Sector | Receivable |")
    lines.append("|------|--------|------------|")
    for _, row_ in priority_df.head(15).iterrows():
        name = row_.get("deal_name", "N/A")
        sec = row_.get("sector", "N/A")
        ar = fmt_inr(row_.get("amount_receivable"))
        lines.append(f"| {name} | {sec} | {ar} |")

    total_ar = priority_df["amount_receivable"].sum(skipna=True)
    lines += ["", f"**Total Priority AR: {fmt_inr(total_ar)}**"]
    return "\n".join(lines)


# ─── 7. Owner / BD Performance ────────────────────────────────────────────────

def get_owner_performance() -> str:
    """
    BD/owner-wise pipeline and revenue breakdown.
    """
    df, issues = _load_deals()
    if df.empty:
        return "❌ Could not load deals data."

    grouped = (
        df[df["deal_status"] == "Open"]
        .groupby("owner_code")
        .agg(
            deals=("deal_name", "count"),
            pipeline_value=("deal_value", "sum"),
        )
        .sort_values("pipeline_value", ascending=False)
    )

    lines = ["## 👤 BD / Owner Performance (Open Pipeline)", ""]
    lines.append("| Owner | Deals | Pipeline Value |")
    lines.append("|-------|-------|----------------|")
    for owner, row_ in grouped.iterrows():
        lines.append(f"| {owner} | {int(row_['deals'])} | {fmt_inr(row_['pipeline_value'])} |")

    won_grouped = (
        df[df["deal_status"] == "Won"]
        .groupby("owner_code")
        .agg(won_deals=("deal_name", "count"), won_value=("deal_value", "sum"))
        .sort_values("won_value", ascending=False)
    )

    if not won_grouped.empty:
        lines += ["", "**Won Deals by Owner:**"]
        lines.append("| Owner | Won Deals | Won Value |")
        lines.append("|-------|-----------|-----------|")
        for owner, row_ in won_grouped.head(8).iterrows():
            lines.append(f"| {owner} | {int(row_['won_deals'])} | {fmt_inr(row_['won_value'])} |")

    return "\n".join(lines)


# ─── 8. Cross-Board: Deal → WO Match ─────────────────────────────────────────

def get_deal_to_wo_summary() -> str:
    """
    Cross-board analysis: match Won deals to Work Orders to show execution progress.
    """
    deals_df, _ = _load_deals()
    wo_df, _ = _load_work_orders()

    if deals_df.empty or wo_df.empty:
        return "❌ Could not load data from one or both boards."

    won_deals = deals_df[deals_df["deal_status"] == "Won"]
    total_won = len(won_deals)
    total_wo = len(wo_df)
    active_wo = len(wo_df[wo_df["execution_status"] == "Ongoing"])
    completed_wo = len(wo_df[wo_df["execution_status"] == "Completed"])

    # Revenue bridge
    won_value = won_deals["deal_value"].sum(skipna=True)
    wo_contract_value = wo_df["amount_excl_gst"].sum(skipna=True)
    wo_collected = wo_df["collected_amount"].sum(skipna=True)

    lines = [
        "## 🔗 Deal → Work Order Pipeline",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Won Deals | {total_won:,} |",
        f"| Total Work Orders | {total_wo:,} |",
        f"| Active (Ongoing) WOs | {active_wo:,} |",
        f"| Completed WOs | {completed_wo:,} |",
        f"| Won Deal Value | {fmt_inr(won_value)} |",
        f"| WO Contract Value | {fmt_inr(wo_contract_value)} |",
        f"| Revenue Collected | {fmt_inr(wo_collected)} |",
    ]
    return "\n".join(lines)


# ─── 9. Leadership Update Report ─────────────────────────────────────────────

def get_leadership_update() -> str:
    """
    Auto-generate a leadership update covering pipeline health, revenue,
    top sectors, and key risks. Intended for weekly/monthly reviews.
    """
    deals_df, d_issues = _load_deals()
    wo_df, w_issues = _load_work_orders()

    lines = ["# 📋 Skylark Drones — Leadership Update", ""]

    # Pipeline Health
    if not deals_df.empty:
        open_df = deals_df[deals_df["deal_status"] == "Open"]
        won_df = deals_df[deals_df["deal_status"] == "Won"]
        open_val = open_df["deal_value"].sum(skipna=True)
        won_val = won_df["deal_value"].sum(skipna=True)
        top_sector = (
            open_df.groupby("sector")["deal_value"].sum().idxmax()
            if not open_df.empty else "N/A"
        )

        lines += [
            "## 🔵 Pipeline Health",
            f"- **Open Pipeline:** {fmt_inr(open_val)} across {len(open_df):,} deals",
            f"- **Won Revenue:** {fmt_inr(won_val)} across {len(won_df):,} deals",
            f"- **Top Sector by Open Value:** {top_sector}",
            "",
        ]

        # High-probability open deals
        high_prob = open_df[open_df["closure_probability"] == "High"]
        high_val = high_prob["deal_value"].sum(skipna=True)
        lines += [
            f"- **High-Probability Deals:** {len(high_prob):,} deals worth {fmt_inr(high_val)}",
            "",
        ]

    # Operational
    if not wo_df.empty:
        total_contract = wo_df["amount_excl_gst"].sum(skipna=True)
        total_collected = wo_df["collected_amount"].sum(skipna=True)
        total_ar = wo_df["amount_receivable"].sum(skipna=True)
        stuck_count = len(wo_df[wo_df["execution_status"] == "Paused/Stuck"])

        collection_pct = (
            total_collected / total_contract * 100
        ) if total_contract else 0

        lines += [
            "## 🟢 Operational & Revenue",
            f"- **Total Contract Value (WOs):** {fmt_inr(total_contract)}",
            f"- **Revenue Collected:** {fmt_inr(total_collected)} ({collection_pct:.1f}% of contracted)",
            f"- **Accounts Receivable:** {fmt_inr(total_ar)}",
            f"- **Stuck/Paused Projects:** {stuck_count} (need attention)",
            "",
        ]

    # Risks
    lines += ["## 🔴 Key Risks & Actions Required"]
    if not wo_df.empty:
        stuck_df = wo_df[wo_df["execution_status"] == "Paused/Stuck"]
        if not stuck_df.empty:
            lines.append("**Stuck Projects:**")
            for _, row_ in stuck_df.head(5).iterrows():
                lines.append(f"  - {row_.get('deal_name', 'N/A')} ({row_.get('sector', 'N/A')})")

    # Data Quality
    total_issues = len(d_issues) + len(w_issues)
    if total_issues > 0:
        lines += [
            "",
            f"⚠️ **Data Quality:** {total_issues} records have missing/incomplete data "
            f"(dates, values, or sectors). Recommend data cleanup before next board review.",
        ]

    lines += [
        "",
        "---",
        "_Report auto-generated by Skylark BI Agent from Monday.com live data._",
    ]

    return "\n".join(lines)


# ─── 10. Raw Data Preview ─────────────────────────────────────────────────────

def get_data_preview(board: str = "deals", n: int = 5) -> str:
    """Return a markdown table preview of raw cleaned data."""
    if board == "work_orders":
        df, _ = _load_work_orders()
        cols = ["deal_name", "sector", "execution_status", "amount_excl_gst", "po_date"]
    else:
        df, _ = _load_deals()
        cols = ["deal_name", "deal_status", "sector", "deal_stage", "deal_value", "tentative_close_date"]

    if df.empty:
        return f"No data available for board: {board}"

    avail_cols = [c for c in cols if c in df.columns]
    sample = df[avail_cols].head(n)

    lines = [f"## 📄 Sample Data — {board.replace('_', ' ').title()}", ""]
    lines.append("| " + " | ".join(avail_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(avail_cols)) + " |")
    for _, row_ in sample.iterrows():
        vals = []
        for c in avail_cols:
            v = row_.get(c, "")
            if isinstance(v, float) and not pd.isna(v):
                v = fmt_inr(v) if "amount" in c or "value" in c else f"{v:,.2f}"
            vals.append(str(v) if v is not None else "—")
        lines.append("| " + " | ".join(vals) + " |")

    return "\n".join(lines)
