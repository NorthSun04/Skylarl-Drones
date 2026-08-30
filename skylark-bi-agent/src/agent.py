"""
agent.py
The core AI agent using OpenAI function-calling to route founder questions
to the right BI tool. Falls back gracefully on API errors.
"""

import os
import json
from openai import OpenAI
from src import bi_tools

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

SYSTEM_PROMPT = """You are Skylark BI Agent — an expert business intelligence assistant for Skylark Drones.
You help founders and executives get quick, accurate answers about their business from Monday.com data.

Your data sources:
1. **Deals Board** — Sales pipeline: deal stages, values, sectors, owners, win/loss status
2. **Work Orders Board** — Operations: active projects, billing, collections, AR

Behavior guidelines:
- Always call the appropriate tool to fetch LIVE data from Monday.com — never guess numbers
- When the user's question is ambiguous, ask ONE clarifying question before calling tools
- Proactively highlight data quality issues (missing values, etc.) when they affect your answer
- Format all monetary values in INR (Cr or L as appropriate)
- Provide business context and insights, not just raw numbers
- If a sector/filter isn't found, suggest alternatives
- For leadership updates, use get_leadership_update() directly

Available sectors: Mining, Renewables, Railways, Powerline, Construction, DSP, Tender, Others, Aviation, Manufacturing
Available deal statuses: Open, Won, Dead, On Hold
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_summary",
            "description": "Get a high-level summary of the deals pipeline. Optionally filter by sector and/or deal status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector to filter by, e.g. 'Renewables', 'Mining'"},
                    "status": {"type": "string", "description": "Deal status filter: Open, Won, Dead, On Hold"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_breakdown",
            "description": "Show deal count and value broken down by industry sector. Use board='work_orders' for operational sector data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "board": {"type": "string", "description": "'deals' (default) or 'work_orders'"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_summary",
            "description": "Revenue and collections analysis from Work Orders. Shows contract value, billed, collected, AR, and unbilled amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_win_rate_analysis",
            "description": "Analyse win rates, loss rates, and conversion metrics from the deals board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_operational_metrics",
            "description": "Work order operational health: execution status distribution, work type breakdown, billing status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ar_priority",
            "description": "List high-priority accounts receivable (AR) — overdue or flagged collections.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_owner_performance",
            "description": "BD / Sales owner-wise pipeline value and won deals breakdown.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deal_to_wo_summary",
            "description": "Cross-board analysis: how won deals translate to work orders and execution revenue.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_leadership_update",
            "description": "Generate a comprehensive leadership update report covering pipeline, revenue, operations, and risks.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_preview",
            "description": "Show a sample of raw cleaned data from either board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "board": {"type": "string", "description": "'deals' or 'work_orders'"},
                    "n": {"type": "integer", "description": "Number of rows to preview (default 5)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invalidate_cache",
            "description": "Force a fresh data fetch from Monday.com (clears in-memory cache).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

TOOL_DISPATCH = {
    "get_pipeline_summary": bi_tools.get_pipeline_summary,
    "get_sector_breakdown": bi_tools.get_sector_breakdown,
    "get_revenue_summary": bi_tools.get_revenue_summary,
    "get_win_rate_analysis": bi_tools.get_win_rate_analysis,
    "get_operational_metrics": bi_tools.get_operational_metrics,
    "get_ar_priority": bi_tools.get_ar_priority,
    "get_owner_performance": bi_tools.get_owner_performance,
    "get_deal_to_wo_summary": bi_tools.get_deal_to_wo_summary,
    "get_leadership_update": bi_tools.get_leadership_update,
    "get_data_preview": bi_tools.get_data_preview,
    "invalidate_cache": bi_tools.invalidate_cache,
}


def call_tool(name: str, args: dict):
    """Dispatch a tool call and return its string result."""
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        result = fn(**args)
        return result if result is not None else "Done."
    except Exception as e:
        return f"⚠️ Error running {name}: {e}"


async def run_agent(user_message: str, history: list[dict]) -> str:
    """
    Run one turn of the agent given a user message and conversation history.
    Returns the assistant's final text response.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    max_iterations = 5
    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as e:
            return f"❌ OpenAI API error: {e}\n\nPlease check your API key."

        message = response.choices[0].message

        # No tool calls → final answer
        if not message.tool_calls:
            return message.content or "I couldn't generate a response. Please try rephrasing."

        # Append assistant message with tool calls
        messages.append(message)

        # Execute all tool calls
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            result = call_tool(fn_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

    return "I reached the maximum number of reasoning steps. Please try a simpler question."
