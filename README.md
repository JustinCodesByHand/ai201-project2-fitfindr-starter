# FitFindr

An AI-powered thrift-shopping assistant. Give it a natural language query — item type, size, price ceiling — and it finds a matching secondhand listing, suggests outfit combinations using your wardrobe, and writes a shareable OOTD caption.

Built with Python, Groq (llama-3.3-70b-versatile), and Gradio.

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

```bash
python app.py    # opens http://localhost:7860
```

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # The three tools
├── agent.py                   # Planning loop + session state
├── app.py                     # Gradio UI
├── tests/
│   └── test_tools.py          # 12 pytest tests
└── planning.md                # Design spec (written before implementation)
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Keyword-score the mock listings dataset against the user's description, with optional hard filters on size and price. Returns the best matches first so the agent can pick the top result without user input.

**Inputs:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `description` | `str` | Yes | Keywords, e.g. `"vintage graphic tee"` |
| `size` | `str \| None` | No | Size filter, e.g. `"M"`. Case-insensitive substring match against listing `size` field (`"M"` matches `"S/M"`). `None` skips size filtering. |
| `max_price` | `float \| None` | No | Inclusive price ceiling in dollars. `None` skips price filtering. |

**Output:** `list[dict]` — each dict is one listing, sorted best-match first. Fields:

| Key | Type | Example |
|---|---|---|
| `id` | `str` | `"lst_002"` |
| `title` | `str` | `"Y2K Baby Tee — Butterfly Print"` |
| `description` | `str` | `"Super cute early 2000s baby tee..."` |
| `category` | `str` | `"tops"` |
| `style_tags` | `list[str]` | `["y2k", "vintage", "graphic tee"]` |
| `size` | `str` | `"S/M"` |
| `condition` | `str` | `"excellent"` |
| `price` | `float` | `18.0` |
| `colors` | `list[str]` | `["white", "pink", "purple"]` |
| `brand` | `str \| None` | `"Levi's"` or `None` |
| `platform` | `str` | `"depop"` |

Returns `[]` (never raises) if nothing matches.

---

### Tool 2: `suggest_outfit`

**Purpose:** Given the thrifted item and the user's wardrobe, ask the LLM to build 1–2 complete outfits. If the wardrobe is populated, the LLM names specific owned pieces. If the wardrobe is empty, it returns general styling advice instead.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `new_item` | `dict` | A listing dict from `search_listings` — same shape as the table above |
| `wardrobe` | `dict` | `{"items": [...]}` where each item has keys `id`, `name`, `category`, `colors`, `style_tags`, `notes`. Access the list with `wardrobe["items"]`. |

**Output:** `str` — non-empty outfit suggestion text. Never returns `""`.

---

### Tool 3: `create_fit_card`

**Purpose:** Turn the outfit suggestion into a 2–4 sentence Instagram/TikTok caption. Mentions the item name, price, and platform once each. Uses temperature 0.9 so each caption sounds different.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `outfit` | `str` | The text returned by `suggest_outfit` |
| `new_item` | `dict` | The same listing dict — provides `title`, `price`, `platform` |

**Output:** `str` — 2–4 sentence caption, or a descriptive error string if `outfit` is empty or whitespace.

---

## Planning Loop

`run_agent(query, wardrobe)` uses an **LLM-driven tool-calling loop** — the model decides which tool to call next at each step based on what has happened so far, rather than executing a fixed sequence.

**How it works:**

1. A fresh `session` dict is created to hold all state for this interaction.
2. A `messages` list is initialized with a system prompt (explaining the 3-tool workflow) and the user's query.
3. The LLM is called with `messages` and `TOOL_DEFINITIONS` (JSON schemas for all 3 tools). `tool_choice="auto"` lets it decide whether to call a tool or stop.
4. If the response contains `tool_calls`: each call is routed through `dispatch_tool()`, which runs the real Python function and writes results into `session`. The tool result is appended to `messages` as a `role="tool"` message.
5. The LLM is called again with the updated `messages`. It now sees what the previous tool returned and decides what to do next.
6. The loop exits when: the LLM returns a text response with no tool calls, `session["error"]` is set (no-results early exit), `session["fit_card"]` is populated (all three tools complete), or `MAX_ITERATIONS` (6) is reached.

**Why the behavior is context-driven:** The LLM sees the actual tool output in `messages`. If `search_listings` returns zero results, the tool message says so and the system prompt instructs the LLM to stop — it does not call `suggest_outfit`. If results are found, the LLM proceeds to `suggest_outfit`, then `create_fit_card`. The decision at each step is made by the model, not by a hardcoded `if/else`.

---

## State Management

A single `session` dict is created at the start of each `run_agent` call and acts as the single source of truth across all three tool calls:

```python
{
    "query": query,              # str — original user query
    "parsed": {},                # dict — reserved
    "search_results": [],        # list[dict] — all matching listings
    "selected_item": None,       # dict — top listing; flows into suggest_outfit + create_fit_card
    "wardrobe": wardrobe,        # dict — user's wardrobe with "items" list
    "outfit_suggestion": None,   # str — returned by suggest_outfit
    "fit_card": None,            # str — returned by create_fit_card
    "error": None,               # str — set if the run ended early, None on success
}
```

**How state passes between tools:** When `search_listings` runs, `dispatch_tool` stores `results[0]` (the full listing dict) into `session["selected_item"]`. When the LLM next calls `suggest_outfit`, `dispatch_tool` reads `session["selected_item"]` and `session["wardrobe"]` and passes them directly to the Python function — no data is re-entered or re-fetched. Likewise, `create_fit_card` reads `session["outfit_suggestion"]` and `session["selected_item"]`. The LLM decides *which* tool to call and *when*; Python's `session` dict carries the actual objects losslessly between calls.

---

## Error Handling

### `search_listings` — no results

`search_listings` never raises. If no listings survive the filters, it returns `[]`. `dispatch_tool` detects the empty list, sets `session["error"]` to a message naming the failed query and suggesting the user try broader terms, and returns an error string to the LLM. The system prompt instructs the LLM to stop immediately — it does not call `suggest_outfit`.

**Tested example:**
```
query: "designer ballgown size XXS under $5"
session["error"]: "No listings found for 'designer ballgown' with the given
                   size/price filters. Try broader search terms."
session["outfit_suggestion"]: None
session["fit_card"]: None
```

### `suggest_outfit` — empty wardrobe

`suggest_outfit` has two code paths based on `len(wardrobe["items"])`. If the wardrobe is empty, it builds a different prompt asking for general styling advice (what types of pieces pair with the item, what aesthetic it suits) rather than pairing with named wardrobe pieces. The function never returns `""` and never raises.

**Tested example:**
```python
suggest_outfit(results[0], get_empty_wardrobe())
# Returns: "The Y2K Baby Tee — Butterfly Print is a cute and playful piece.
#  Here are a couple of outfit ideas to get you started: 1. Cottagecore Dream:
#  Pair the tee with some high-waisted mom jeans..."
# (general advice — no specific wardrobe pieces named)
```

### `create_fit_card` — empty outfit string

`create_fit_card` guards at entry: `if not outfit or not outfit.strip()` it returns a descriptive error string and skips the LLM call entirely.

**Tested example:**
```python
create_fit_card("", results[0])
# Returns: "Could not generate a fit card — outfit suggestion was empty."
```

### API errors — Groq malformed tool-call JSON and rate limits

Groq's model occasionally generates malformed tool-call syntax (e.g. `<function=search_listings({"description": "boots"})` using `(` instead of a space). Rather than failing the run, `_recover_from_groq_tool_error()` extracts the `failed_generation` string from the error body, parses the intended tool name and JSON args with a regex, and calls `dispatch_tool` directly so the loop continues.

If the error is a rate limit (HTTP 429), `session["error"]` is set to `"API rate limit reached. Please wait a minute and try again."`.

---

## Spec Reflection

**One way the spec helped:** The explicit data-shape tables in `planning.md` — listing every key, type, and example value for the `search_listings` return dict and the `wardrobe` dict — eliminated a whole class of bugs before implementation started. When wiring `suggest_outfit`, the exact key name (`wardrobe["items"]`, not `wardrobe["wardrobe_items"]`) was already documented, so there was no guessing. The tables also confirmed that `selected_item` flowing from `search_listings` → `suggest_outfit` → `create_fit_card` carried all the fields each tool needed.

**One way implementation diverged from the spec:** The spec's `TOOL_DEFINITIONS` for `suggest_outfit` and `create_fit_card` originally included boolean placeholder parameters (`use_selected_item: bool`, `use_outfit_suggestion: bool`) to give the LLM something to pass. In practice, Groq generated malformed JSON for these dummy parameters far more reliably than for `search_listings`'s real string parameters — because the model tried to produce a value for a parameter with no semantic meaning. The fix was to declare those two tools with no parameters (`"properties": {}, "required": []`), since their inputs come from session state, not the LLM. The spec implied all tool calls should carry arguments; the real system needed the LLM to call two of them with empty argument objects.

---

## AI Usage

### Instance 1: Generating `tools.py` from the spec tables

**What I gave the AI:** The full `planning.md` Tool 1–3 sections — input parameter tables, return-shape tables with key names and types, failure-mode rows — plus `utils/data_loader.py` and a request to write scaffold comments on every other line with blank lines for me to fill in.

**What it produced:** A complete `tools.py` with all three functions implemented and every-other-line scaffold comments explaining each step. For example, above `all_listings = load_listings()` it wrote: `"Step 1: Load every listing from the JSON file into a Python list — load_listings() returns a list of dicts, each dict is one item for sale. Example: all_listings[0] is {'id': 'lst_001', ...}"`.

**What I changed:** I read the scaffold comments first to understand the flow before reading the generated code. I then verified the keyword-scoring logic manually by running `search_listings("vintage graphic tee", max_price=30)` and checking that the top result was a tee, and `search_listings("designer ballgown", max_price=5)` returned `[]`. I kept the comments as documentation since they explain the *why* of each step.

### Instance 2: Debugging Groq tool-call generation failures

**What I gave the AI:** The exact error body from Groq — `{'failed_generation': '<function=search_listings({"description": "black combat boots", "size": "8"})</function>'}` showing the `(` malformation — plus a second failure using `=` as the separator, and the constraint that the fix must keep the loop LLM-driven (rubric requirement: agent behavior must be context-driven, not fixed-sequential).

**What it produced:** `_recover_from_groq_tool_error()` — a function that extracts `failed_generation` from the error body and uses a regex to parse the tool name and JSON args from the malformed string, then calls `dispatch_tool` directly so the loop continues.

**What I changed:** The initial regex `[=({\s]+` consumed the opening `{` along with the separator character, so `raw_args` was missing its leading brace and `json.loads` failed with "Extra data." I debugged it by writing a small test script that ran the regex against all three known malformation patterns, found the issue, and changed the pattern to `[=(]?\s*(\{.*?)` — stopping before `{` rather than including it in the separator class.

---

## Running Tests

```bash
pytest tests/
```

12 tests covering all three tools: happy paths, empty-results path, empty-wardrobe path, empty-outfit/whitespace-outfit paths, price filter, size filter, and relevance ordering.
