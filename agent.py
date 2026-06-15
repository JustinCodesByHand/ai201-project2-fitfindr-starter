"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to a .env file in the project root.")
    return Groq(api_key=api_key)


# ── tool definitions ──────────────────────────────────────────────────────────
# TOOL_DEFINITIONS is a list of dicts — each dict describes one tool to the LLM.
# The LLM reads these descriptions to decide which tool to call next.
# Shape: [{"type": "function", "function": {"name": str, "description": str, "parameters": {...}}}]

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": (
                "Search secondhand listings for items matching a description. "
                "Call this FIRST to find a matching item. "
                "Returns a list of listing dicts sorted by relevance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Keywords describing what the user wants, e.g. 'vintage graphic tee'",
                    },
                    "size": {
                        "type": "string",
                        "description": "Size filter, e.g. 'M' or 'S/M'. Omit if not specified.",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price in dollars. Omit if not specified.",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_outfit",
            "description": (
                "Suggest 1-2 outfit combinations using the found item and the user's wardrobe. "
                "Call this AFTER search_listings returns results. "
                "Takes no arguments — uses the top search result already stored in session."
            ),
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
            "name": "create_fit_card",
            "description": (
                "Generate a short Instagram/TikTok caption for the outfit. "
                "Call this AFTER suggest_outfit returns a suggestion. "
                "Takes no arguments — uses the outfit suggestion already stored in session."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ── tool dispatcher ───────────────────────────────────────────────────────────
# dispatch_tool routes the LLM's tool call to the real Python function.
# tool_name: str — which tool the LLM chose (matches TOOL_DEFINITIONS names)
# tool_args: dict — arguments the LLM extracted from the user's query
# session: dict — the shared session dict; dispatcher reads and writes it
# Returns: a string result to send back to the LLM as a tool response

def _log(session: dict, msg: str) -> None:
    session["log"].append(msg)


def dispatch_tool(tool_name: str, tool_args: dict, session: dict) -> str:
    # Route "search_listings" → call search_listings(), store results in session
    if tool_name == "search_listings":
        desc = tool_args["description"]
        size = tool_args.get("size")
        price = tool_args.get("max_price")
        filters = []
        if size:
            filters.append(f"size={size}")
        if price is not None:
            filters.append(f"max_price=${price}")
        filter_str = f" [{', '.join(filters)}]" if filters else ""
        _log(session, f"[TOOL 1] search_listings(\"{desc}\"{filter_str})")
        _log(session, f"  Scoring listings by keyword match against title, description, style tags...")

        results = search_listings(
            description=desc,
            size=size,
            max_price=price,
        )
        session["search_results"] = results

        if not results:
            session["error"] = (
                f"No listings found for '{desc}' "
                f"with the given size/price filters. Try broader search terms."
            )
            _log(session, f"  Result: 0 matches — stopping early. No outfit suggestion will run.")
            return f"search_listings returned 0 results. {session['error']}"

        session["selected_item"] = results[0]
        item = results[0]
        _log(session, f"  Result: {len(results)} match(es). Top hit: \"{item['title']}\" — ${item['price']:.2f} on {item['platform']}")
        _log(session, f"  session[\"selected_item\"] = listing dict for \"{item['title']}\" (id={item['id']})")
        _log(session, f"  This dict flows directly into suggest_outfit — no re-entry needed.")
        return (
            f"Found {len(results)} listings. Top result: "
            f"{item['title']} — ${item['price']:.2f} on {item['platform']}. "
            f"id={item['id']}"
        )

    # Route "suggest_outfit" → call suggest_outfit(), store result in session
    elif tool_name == "suggest_outfit":
        if session["selected_item"] is None:
            return "Error: must call search_listings first to select an item."

        item = session["selected_item"]
        wardrobe_count = len(session["wardrobe"]["items"])
        _log(session, f"[TOOL 2] suggest_outfit(new_item=session[\"selected_item\"], wardrobe)")
        _log(session, f"  State passed from Tool 1: item is \"{item['title']}\" (${item['price']:.2f})")
        if wardrobe_count == 0:
            _log(session, f"  Wardrobe is empty — taking general styling advice path (no named pieces)")
        else:
            _log(session, f"  Wardrobe has {wardrobe_count} items — LLM will name specific pieces to pair")
        _log(session, f"  Calling LLM for outfit suggestion...")

        suggestion = suggest_outfit(item, session["wardrobe"])
        session["outfit_suggestion"] = suggestion
        _log(session, f"  Result: outfit suggestion stored in session[\"outfit_suggestion\"] ({len(suggestion)} chars)")
        return f"Outfit suggestion generated: {suggestion[:200]}..."

    # Route "create_fit_card" → call create_fit_card(), store result in session
    elif tool_name == "create_fit_card":
        if not session["outfit_suggestion"]:
            return "Error: must call suggest_outfit first to get an outfit suggestion."

        item = session["selected_item"]
        _log(session, f"[TOOL 3] create_fit_card(outfit=session[\"outfit_suggestion\"], new_item=session[\"selected_item\"])")
        _log(session, f"  State passed from Tools 1+2: item \"{item['title']}\", outfit text ({len(session['outfit_suggestion'])} chars)")
        _log(session, f"  Calling LLM for OOTD caption (temperature=0.9)...")

        fit_card = create_fit_card(session["outfit_suggestion"], item)
        session["fit_card"] = fit_card
        _log(session, f"  Result: fit card stored in session[\"fit_card\"] ({len(fit_card)} chars)")
        return f"Fit card created: {fit_card[:200]}..."

    else:
        return f"Error: unknown tool '{tool_name}'."


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "log": [],                   # list of narration strings, one per step
    }


# ── Groq tool-call repair ─────────────────────────────────────────────────────

def _recover_from_groq_tool_error(exc: Exception, session: dict) -> bool:
    """
    Groq occasionally generates malformed tool-call JSON (uses ( or = as separator
    instead of a space). The model still picked the right tool and args — recover by
    extracting them from the failed_generation field in the error body.

    Returns True if recovery succeeded and the tool was executed, False otherwise.
    """
    # Pull the failed_generation string out of the error body
    # exc.body is a dict for groq.BadRequestError; fall back to str(exc) for others
    body = getattr(exc, "body", None) or {}
    failed = ""
    if isinstance(body, dict):
        failed = body.get("error", {}).get("failed_generation", "")
    if not failed:
        failed = str(exc)

    # failed_generation looks like one of:
    #   <function=search_listings({"description": "boots", "size": "8"})</function>
    #   <function=search_listings {"description": "boots"}</function>
    #   <function=suggest_outfit={"use_selected_item":true}</function>
    # Extract tool name and the JSON blob (if any)
    match = re.search(r"<function=(\w+)[=(]?\s*(\{.*?)(?:</function>|$)", failed, re.DOTALL)
    if not match:
        return False

    tool_name = match.group(1)
    raw_args = match.group(2).strip().rstrip(")")

    # Parse args — empty string or no-arg tools get an empty dict
    try:
        tool_args = json.loads(raw_args) if raw_args and raw_args != "{}" else {}
    except json.JSONDecodeError:
        # Try wrapping in braces in case it's missing the closing }
        try:
            tool_args = json.loads(raw_args + "}")
        except json.JSONDecodeError:
            return False

    # Execute the tool the LLM intended to call
    dispatch_tool(tool_name, tool_args, session)
    return True


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session — single source of truth for this interaction
    session = _new_session(query, wardrobe)
    wardrobe_count = len(wardrobe["items"])
    _log(session, f"[AGENT] run_agent started")
    _log(session, f"  Query: \"{query}\"")
    _log(session, f"  Wardrobe: {wardrobe_count} item(s) loaded")
    _log(session, f"  Sending query to LLM with 3 tool definitions (search_listings, suggest_outfit, create_fit_card)...")

    # Step 2: Build the initial messages list the LLM will see
    # System prompt tells the LLM its role and the 3-tool sequence to follow
    # User message is the raw query — the LLM decides which tool to call first
    messages = [
        {
            "role": "system",
            "content": (
                "You are FitFindr, a thrift-shopping assistant. "
                "Help the user find a secondhand item and build an outfit around it. "
                "Use tools in this order based on what has been done so far:\n"
                "1. Call search_listings to find a matching item.\n"
                "2. Call suggest_outfit to build outfit ideas around the top result.\n"
                "3. Call create_fit_card to write a shareable caption.\n"
                "Stop after create_fit_card completes. "
                "If search_listings returns 0 results, stop immediately — do not call suggest_outfit."
            ),
        },
        {
            "role": "user",
            "content": query,
        },
    ]

    # Step 3: Planning loop — keep asking the LLM which tool to call next
    # LLM responds with either a tool_call or a plain text stop message
    # Max 6 iterations to prevent infinite loops (3 tools × 2 gives headroom)
    client = _get_groq_client()
    MAX_ITERATIONS = 6

    for _ in range(MAX_ITERATIONS):
        # Ask the LLM what to do next — pass the full messages history + tool defs
        # Groq can return 400 if it generates malformed tool-call JSON; treat as no-results
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",  # LLM decides whether to call a tool or stop
            )
        except Exception as exc:
            # Groq sometimes generates malformed tool-call JSON (e.g. using ( or = instead
            # of a space before the args object). The LLM still chose the right tool and
            # args — recover by extracting them from the failed_generation string.
            # Rate limit is a distinct error — give the user an actionable message
            if getattr(exc, "status_code", None) == 429:
                session["error"] = "API rate limit reached. Please wait a minute and try again."
                break
            recovered = _recover_from_groq_tool_error(exc, session)
            if recovered:
                # Successfully executed the intended tool call via repair — continue loop
                if session["error"]:
                    break
                continue
            session["error"] = "Sorry, could not understand your request. Try rephrasing it."
            break

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if message.tool_calls:
            names = [tc.function.name for tc in message.tool_calls]
            _log(session, f"[LLM] Decided to call: {', '.join(names)}")
        else:
            _log(session, f"[LLM] No more tool calls — loop complete")

        # Append the LLM's response to messages so it stays in context next turn
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (message.tool_calls or [])
            ] or None,
        })

        # If LLM stopped (no more tool calls), exit the loop
        if finish_reason == "stop" or not message.tool_calls:
            break

        # Execute each tool call the LLM requested
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            # tool_call.function.arguments is a JSON string — parse it to a dict
            tool_args = json.loads(tool_call.function.arguments)

            # Run the real tool function via dispatch and capture its string result
            tool_result = dispatch_tool(tool_name, tool_args, session)

            # Append the tool result to messages so the LLM sees what happened
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

            # If the search returned nothing, stop the loop early
            if session["error"]:
                break

        # Also break outer loop if error was set inside the tool call loop
        if session["error"]:
            break

        # If all three outputs are filled, we're done — no need to keep looping
        if session["fit_card"] is not None:
            break

    # Step 4: Return the completed session dict
    # Caller checks session["error"] first — if set, outfit_suggestion and fit_card are None
    if session["error"]:
        _log(session, f"[AGENT] Finished with error: {session['error']}")
    else:
        _log(session, f"[AGENT] Done. All 3 tools completed successfully.")
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
