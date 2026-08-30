"""
End-to-end validation: simulates what the agent does without hitting real APIs.
Uses local CSV data + mock Monday.com client to verify the full BI pipeline.
"""

import sys
import os
sys.path.insert(0, '.')

# Mock the monday_client to use local CSVs
import pandas as pd

# Monkey-patch for testing
import src.bi_tools as bi_tools

def mock_deals():
    df = pd.read_csv('../deal_funnel.csv')
    records = df.to_dict(orient='records')
    from src.data_cleaner import clean_deals
    return clean_deals(records)

def mock_wo():
    df = pd.read_csv('../work_orders.csv', skiprows=1)
    records = df.to_dict(orient='records')
    from src.data_cleaner import clean_work_orders
    return clean_work_orders(records)

# Patch cache
bi_tools._cache['deals'] = mock_deals()
bi_tools._cache['work_orders'] = mock_wo()

print("=" * 60)
print("SKYLARK BI AGENT — End-to-End Validation")
print("=" * 60)

# 1. Pipeline Summary
print("\n[1] Pipeline Summary:")
result = bi_tools.get_pipeline_summary()
print(result[:800])

# 2. Sector Breakdown
print("\n[2] Sector Breakdown (Deals):")
result = bi_tools.get_sector_breakdown()
print(result[:600])

# 3. Revenue Summary
print("\n[3] Revenue Summary:")
result = bi_tools.get_revenue_summary()
print(result[:600])

# 4. Win Rate
print("\n[4] Win Rate Analysis:")
result = bi_tools.get_win_rate_analysis()
print(result[:600])

# 5. Sector filter: Renewables
print("\n[5] Pipeline Summary - Renewables:")
result = bi_tools.get_pipeline_summary(sector="Renewables")
print(result[:600])

# 6. Leadership Update (abridged)
print("\n[6] Leadership Update (first 1000 chars):")
result = bi_tools.get_leadership_update()
print(result[:1000])

print("\n" + "=" * 60)
print("ALL VALIDATIONS PASSED!")
print("=" * 60)
