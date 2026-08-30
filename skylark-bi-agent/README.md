# Skylark Drones — Business Intelligence Agent

A conversational AI agent that answers founder-level business intelligence queries by integrating with Monday.com boards containing **Work Orders** and **Deal Funnel** data.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   User (Browser)                     │
└─────────────────────┬───────────────────────────────┘
                      │ Chat (Chainlit UI)
┌─────────────────────▼───────────────────────────────┐
│               Chainlit App  (app.py)                 │
│          Session management, welcome flow            │
└─────────────────────┬───────────────────────────────┘
                      │ async run_agent()
┌─────────────────────▼───────────────────────────────┐
│          AI Agent  (src/agent.py)                    │
│   OpenAI GPT-4o with 11 function-calling tools       │
└──────┬──────────────────────────────────────────────┘
       │ Tool dispatch
┌──────▼──────────────────────────────────────────────┐
│         BI Tools  (src/bi_tools.py)                  │
│  Pipeline, Revenue, Win Rate, Ops, AR, Leadership    │
└──────┬──────────────────────────────────────────────┘
       │ Fetch & clean
┌──────▼────────────────┐   ┌────────────────────────┐
│  Monday Client        │   │  Data Cleaner           │
│  (src/monday_client)  │   │  (src/data_cleaner.py)  │
│  GraphQL + pagination │   │  Date/number/sector     │
└──────┬────────────────┘   │  normalization          │
       │                    └────────────────────────┘
┌──────▼──────────────────────────────────────────────┐
│              Monday.com API (GraphQL)                │
│          Deals Board   |   Work Orders Board         │
└─────────────────────────────────────────────────────┘
```

---

## 📁 File Structure

```
skylark-bi-agent/
├── app.py                  # Chainlit chat UI entry point
├── import_to_monday.py     # One-time CSV → Monday.com import script
├── requirements.txt
├── Dockerfile
├── .env.example            # Environment variable template
├── .chainlit/
│   └── config.toml
└── src/
    ├── __init__.py
    ├── monday_client.py    # Monday.com GraphQL API client (pagination)
    ├── data_cleaner.py     # Data normalization (dates, numbers, sectors)
    ├── bi_tools.py         # 10 BI analysis functions
    └── agent.py            # OpenAI function-calling agent
```

---

## ⚙️ Setup Instructions

### Prerequisites
- Python 3.11+
- A [Monday.com](https://monday.com) account with API access
- An OpenAI API key

---

### Step 1 — Clone & Install

```bash
cd skylark-bi-agent
pip install -r requirements.txt
```

---

### Step 2 — Monday.com Configuration

#### 2a. Get Your API Token
1. Log into Monday.com
2. Click your **avatar** → **Administration** → **API**
3. Copy your **Personal API Token (v2)**

#### 2b. Import the CSV Data
Copy your CSV files into the project root, then run:

```bash
# Set your token first
set MONDAY_API_TOKEN=your_token_here   # Windows
export MONDAY_API_TOKEN=your_token_here  # Mac/Linux

# Import both boards
python import_to_monday.py --deals ../deal_funnel.csv --workorders ../work_orders.csv
```

The script will print the **Board IDs** upon completion — save these.

#### 2c. Manual Import (Alternative)
1. Go to Monday.com → **+ Add Board** → Import from CSV
2. Upload `deal_funnel.csv` → name it **"Deal Funnel — Skylark"**
3. Upload `work_orders.csv` → name it **"Work Orders — Skylark"**
4. Set column types appropriately (see below)
5. Note the board IDs from the URL: `monday.com/boards/XXXXXXXXX`

**Recommended column types for Deals board:**
| Column | Type |
|--------|------|
| Deal Status | Status |
| Closure Probability | Dropdown |
| Masked Deal Value | Numbers |
| Tentative Close Date | Date |
| Deal Stage | Status |
| Sector/service | Dropdown |

**Recommended column types for Work Orders board:**
| Column | Type |
|--------|------|
| Execution Status | Status |
| Sector | Dropdown |
| Amount in Rupees (Excl GST) | Numbers |
| Date of PO/LOI | Date |
| Billing Status | Status |

---

### Step 3 — Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
OPENAI_API_KEY=sk-...
MONDAY_API_TOKEN=your_monday_token
MONDAY_DEALS_BOARD_ID=1234567890
MONDAY_WORK_ORDERS_BOARD_ID=9876543210
```

---

### Step 4 — Run Locally

```bash
chainlit run app.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 🚀 Deployment (Railway)

1. Push to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Set environment variables in Railway dashboard (same as `.env`)
4. Railway auto-detects the Dockerfile and deploys
5. You get a public URL like `https://skylark-bi-agent.railway.app`

### Alternative: Render
1. Go to [render.com](https://render.com) → **New Web Service** → connect GitHub
2. Build command: `pip install -r requirements.txt`
3. Start command: `chainlit run app.py --host 0.0.0.0 --port $PORT`
4. Add environment variables in the Render dashboard

---

## 💬 Example Queries

| Query | What it does |
|-------|-------------|
| "How's our pipeline looking for energy sector?" | Filters deals by Renewables sector |
| "Show me the leadership update" | Generates full board-ready report |
| "What's our win rate in Mining?" | Win/loss analysis for Mining |
| "Which accounts receivable are priority?" | Flags high AR accounts |
| "How much have we collected vs contracted?" | Revenue collections summary |
| "Who has the strongest pipeline?" | Owner/BD performance breakdown |
| "Which work orders are stuck?" | Paused/stuck project list |
| "Show me a cross-board deal to WO summary" | Links sales → operations data |

---

## 🛡️ Data Handling Notes

- **No CSV hardcoding** — all data fetched live from Monday.com GraphQL API
- **Graceful degradation** — missing values, nulls, and API errors are handled transparently
- **Data quality transparency** — agent reports data gaps alongside insights
- **In-memory caching** — data cached per session for speed; `invalidate_cache` clears it
- **Pagination** — handles boards with 500+ items via cursor-based pagination

---

## 🔑 Environment Variables Reference

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o) |
| `MONDAY_API_TOKEN` | Monday.com Personal API Token |
| `MONDAY_DEALS_BOARD_ID` | Board ID of the Deal Funnel board |
| `MONDAY_WORK_ORDERS_BOARD_ID` | Board ID of the Work Orders board |
