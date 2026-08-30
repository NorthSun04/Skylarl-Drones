# Decision Log — Skylark Drones BI Agent

**Author:** Skylark Assignment Submission  
**Date:** August 2026  
**Time Budget:** 6 hours

---

## 1. Key Assumptions

**Data & Domain**
- Deal names are anonymized (fictional characters) — treated as-is; real names would be in production
- "Energy sector" in founder questions maps to "Renewables" in the data (most common interpretation in drone industry context)
- Masked monetary values are in Indian Rupees (INR); formatted as Cr/L for readability
- Duplicate rows in the deals CSV (same deal, different dates) are intentional — they represent separate deal entries, not errors
- The header rows that appear mid-CSV (rows 52, 181) are artifacts of the export tool; filtered out in the data cleaner
- `#VALUE!` errors in the work orders sheet are Excel formula errors — treated as null

**Business Logic**
- "Pipeline" = Open deals only (not Won or Dead)
- "Revenue" = Work Orders board (contracted and collected amounts)
- Win rate calculated as Won / (Won + Dead) — excluding still-open deals from denominator
- "Leadership update" = a board-ready report covering pipeline, revenue, operations, and risks

---

## 2. Tech Stack Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **LLM** | OpenAI GPT-4o | Best function-calling reliability; understands ambiguous business queries |
| **UI Framework** | Chainlit | Purpose-built for LLM chat apps; minimal boilerplate; streams responses |
| **Monday.com Integration** | REST/GraphQL API | Simpler to set up than MCP for a self-contained submission; full control over queries |
| **Data Processing** | pandas | Standard for tabular data; handles the messy CSVs well |
| **Hosting** | Railway / Render | One-click Docker deploy; free tier available; gives public URL immediately |
| **Architecture** | Function-calling agent | More reliable than prompt-only for structured data queries; forces tool use |

**Why API over MCP?**  
MCP requires a running sidecar server and more complex orchestration. For a self-contained demo with a 6-hour deadline, the GraphQL API is simpler, equally powerful, and easier to deploy. MCP would be the right choice for a production multi-tool environment.

**Why GPT-4o over Gemini?**  
GPT-4o has more mature, reliable function-calling behavior for structured data routing. Gemini is excellent for generation but has more variability in tool dispatch for complex multi-step queries.

---

## 3. Trade-offs

**Speed vs. Freshness**  
Data is cached in-memory per session to avoid hammering the Monday.com API on every message. The trade-off is that live changes in Monday.com aren't reflected until the user refreshes or session restarts. A Redis TTL cache (e.g., 5 minutes) would be the production solution.

**Breadth vs. Depth**  
Built 10 BI tools covering most founder questions rather than going very deep on one area. In production, each tool would have richer drill-down capability (e.g., individual deal timelines, custom date ranges, forecast modeling).

**Data Cleaning vs. Passthrough**  
Chose aggressive normalization (dates, sectors, statuses) over passing raw data to the LLM. This ensures consistent calculations but might lose edge-case nuances. All normalization logic is transparent and logged.

**Pagination**  
Implemented full cursor-based pagination for boards with 500+ items. This is slower on first load but ensures no data is missed for large boards.

---

## 4. What I'd Do Differently With More Time

1. **Streaming responses** — Stream LLM output token-by-token for a faster perceived experience
2. **Chart generation** — Use matplotlib/plotly to render pipeline funnel charts, sector pie charts inline in chat
3. **Date-range filtering** — Let users say "this quarter" or "FY25-26" and map to date ranges automatically
4. **Persistent memory** — Store conversation context in a database so founders can resume sessions
5. **Monday.com webhooks** — Real-time cache invalidation when board data changes
6. **User authentication** — Role-based access (founder sees everything; BD sees only their deals)
7. **Forecasting** — Use closure probability × deal value to project quarterly revenue expectations
8. **Automated alerts** — Cron job to send weekly leadership updates to Slack/email

---

## 5. Interpretation of "Leadership Updates"

**My interpretation:** A leadership update is a *structured, self-contained report* that a founder or VP can read in 2 minutes before a board meeting or weekly review. It should:

- Summarize the current state without requiring the reader to ask follow-up questions
- Highlight what's working (top-performing sectors, won deals)
- Flag what needs attention (stuck projects, high AR, low-probability stalled deals)
- Provide actionable numbers (not just "pipeline is healthy" — actual ₹ values)

**Implementation:** The `get_leadership_update()` tool auto-generates this report combining both boards. It covers: pipeline health, high-probability deals, revenue collections, AR outstanding, stuck projects, and data quality notes.

**Extension ideas:** In a richer implementation, this could be triggered on a schedule (every Monday morning), formatted as a PDF, and sent to a Slack channel or email — making it a "push" update rather than a query response.

---

## 6. Handling Data Quality

The data had several real-world issues handled gracefully:

| Issue | Handling |
|-------|----------|
| Repeated header rows mid-CSV | Filtered out by checking if value equals column name |
| Missing deal values | Counted; reported to user; excluded from sums |
| `#VALUE!` Excel errors | Treated as null |
| Inconsistent date formats | Tried 10 format patterns; returned null if none matched |
| Sector naming variants | Normalized via alias map (e.g., "energy" → "Renewables") |
| Mixed number formats (commas, ₹ symbol) | Stripped via regex before parsing |
| Blank owner codes | Left as empty string; shown as "Unassigned" in reports |

The agent always communicates data quality caveats alongside its answers — e.g., "Note: 23 deals have missing deal values and are excluded from the total."
