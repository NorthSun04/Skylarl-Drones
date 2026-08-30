"""
app.py  —  Skylark Drones BI Agent
Chainlit chat interface connecting the AI agent to founders.
"""

import os
import chainlit as cl
from dotenv import load_dotenv
from src.agent import run_agent
from src.monday_client import test_connection

load_dotenv()

# ─── Startup Message ──────────────────────────────────────────────────────────

WELCOME_MSG = """# 🚁 Skylark Drones — Business Intelligence Agent

Hello! I'm your AI-powered BI assistant, connected live to your **Monday.com** boards.

**I can answer questions like:**
- *"How's our pipeline looking for the energy sector this quarter?"*
- *"What's our win rate in Mining vs Railways?"*
- *"Show me our accounts receivable priority list"*
- *"Which BD owner has the strongest pipeline?"*
- *"Generate a leadership update for this week"*
- *"What work orders are stuck or paused?"*
- *"How much revenue have we collected vs contracted?"*

**Data sources:** Deals Board + Work Orders Board (live from Monday.com)

---
What would you like to know?
"""


@cl.on_chat_start
async def start():
    """Initialize session and check Monday.com connection."""
    # Check env vars
    missing = []
    for var in ["OPENAI_API_KEY", "MONDAY_API_TOKEN", "MONDAY_DEALS_BOARD_ID", "MONDAY_WORK_ORDERS_BOARD_ID"]:
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        await cl.Message(
            content=(
                f"⚠️ **Configuration incomplete.** Missing environment variables:\n"
                + "\n".join(f"  - `{v}`" for v in missing)
                + "\n\nPlease set these in your `.env` file and restart."
            )
        ).send()
        return

    # Test Monday.com connection
    connected = test_connection()
    status = "✅ Connected to Monday.com" if connected else "⚠️ Monday.com connection check failed — data may be unavailable"

    # Store conversation history in session
    cl.user_session.set("history", [])
    cl.user_session.set("monday_connected", connected)

    await cl.Message(content=WELCOME_MSG + f"\n_{status}_").send()


@cl.on_message
async def handle_message(message: cl.Message):
    """Handle each user message through the agent."""
    history = cl.user_session.get("history", [])

    # Show typing indicator
    async with cl.Step(name="Thinking...", type="run", show_input=False) as step:
        step.input = message.content

        try:
            response = await run_agent(message.content, history)
        except Exception as e:
            response = (
                f"❌ An error occurred: `{e}`\n\n"
                "Please check your API keys and Monday.com board IDs, then try again."
            )

        step.output = "Done"

    # Update conversation history (keep last 20 turns to avoid token overflow)
    history.append({"role": "user", "content": message.content})
    history.append({"role": "assistant", "content": response})
    history = history[-20:]
    cl.user_session.set("history", history)

    await cl.Message(content=response).send()


@cl.action_callback("refresh_data")
async def on_refresh(action: cl.Action):
    """Refresh Monday.com data cache."""
    from src.bi_tools import invalidate_cache
    invalidate_cache()
    await cl.Message(content="🔄 Data cache cleared — next query will fetch fresh data from Monday.com.").send()
