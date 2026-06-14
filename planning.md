# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (`data/listings.json`, loaded via `load_listings()`) for items that match the user's keywords, and optionally a size and a price ceiling. Returns the matching listings ranked best-match first.

**Input parameters:**
- `description` (str): keywords describing what the user wants, e.g. `"vintage graphic tee"`. Required.
- `size` (str | None): a size to filter by, e.g. `"M"`. Matched case-insensitively as a substring against each listing's `size` field (so `"M"` matches `"S/M"`). `None` skips size filtering.
- `max_price` (float | None): inclusive price ceiling, e.g. `30.0`. `None` skips price filtering.

**What it returns:**
A `list[dict]` — a Python list where **each element is one listing dictionary**. Sorted so the highest-scoring match is at index `0`. Each listing dict has exactly these keys:

| key | type | example | how to access |
|-----|------|---------|---------------|
| `id` | str | `"lst_002"` | `listing["id"]` |
| `title` | str | `"Y2K Baby Tee — Butterfly Print"` | `listing["title"]` |
| `description` | str | `"Super cute early 2000s baby tee..."` | `listing["description"]` |
| `category` | str | `"tops"` | `listing["category"]` |
| `style_tags` | list[str] | `["y2k", "vintage", "graphic tee"]` | `listing["style_tags"]` — a list; loop it or `listing["style_tags"][0]` |
| `size` | str | `"S/M"` | `listing["size"]` |
| `condition` | str | `"excellent"` | `listing["condition"]` |
| `price` | float | `18.0` | `listing["price"]` |
| `colors` | list[str] | `["white", "pink", "purple"]` | `listing["colors"]` — a list |
| `brand` | str \| None | `"Levi's"` or `None` | `listing["brand"]` (may be `None`) |
| `platform` | str | `"depop"` | `listing["platform"]` |

So the top result's title is: `results[0]["title"]`. Its first style tag is: `results[0]["style_tags"][0]`.

**What happens if it fails or returns nothing:**
Returns an empty list `[]` — it never raises an exception. The agent sees `[]`, tells the user nothing matched, and asks them to loosen a filter (raise `max_price`, drop the size, or use broader keywords). The agent does **not** proceed to `suggest_outfit` with no item.

---

### Tool 2: suggest_outfit

**What it does:**
Given one thrifted item and the user's wardrobe, asks the LLM to suggest 1–2 complete outfits, naming real pieces from the wardrobe where possible.

**Input parameters:**
- `new_item` (dict): one listing dict — the item the user is considering. Same shape as a `search_listings` result above. Access fields like `new_item["title"]`, `new_item["colors"]`.
- `wardrobe` (dict): the user's closet. **It is a dict with one key, `"items"`, whose value is a list of wardrobe-item dicts.** Access the list with `wardrobe["items"]`. Each wardrobe item has these keys:

| key | type | example | how to access |
|-----|------|---------|---------------|
| `id` | str | `"w_001"` | `item["id"]` |
| `name` | str | `"Baggy straight-leg jeans, dark wash"` | `item["name"]` |
| `category` | str | `"bottoms"` | `item["category"]` |
| `colors` | list[str] | `["dark blue", "indigo"]` | `item["colors"]` |
| `style_tags` | list[str] | `["denim", "streetwear", "baggy"]` | `item["style_tags"]` |
| `notes` | str \| None | `"High-waisted"` or `None` | `item["notes"]` (may be `None`) |

So the first wardrobe piece's name is `wardrobe["items"][0]["name"]`. The number of pieces is `len(wardrobe["items"])`.

**What it returns:**
A non-empty `str` containing the outfit suggestions (free text the agent shows the user).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty (`len(wardrobe["items"]) == 0`), do not error. Instead ask the LLM for *general* styling advice for `new_item` (what kinds of pieces pair with it, what vibe it suits) and return that string. Never return `""`.

---

### Tool 3: create_fit_card

**What it does:**
Turns an outfit suggestion into a short, shareable caption — the kind of thing posted under an OOTD photo.

**Input parameters:**
- `outfit` (str): the outfit text returned by `suggest_outfit`.
- `new_item` (dict): the same listing dict as Tool 2. Used to name the item, its price, and platform. Access `new_item["title"]`, `new_item["price"]`, `new_item["platform"]`.

**What it returns:**
A `str` — 2–4 sentences usable as an Instagram/TikTok caption. Mentions the item title, price, and platform once each. Uses a higher LLM temperature so different inputs yield different captions.

**What happens if it fails or returns nothing:**
If `outfit` is empty or only whitespace (`outfit.strip() == ""`), return a plain descriptive error **string** (not an exception), e.g. `"Can't write a fit card — no outfit was provided."` The agent surfaces that to the user.

---

### Additional Tools (if any)

None. Three read-only tools only — this project does not write to disk.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is **LLM-driven and context-aware** — not a fixed sequence. `run_agent(query, wardrobe)` works like the prior project's loop:

1. Build a `messages` list: system prompt (which embeds the user's wardrobe) + the user query.
2. Call the LLM with `messages` and `TOOL_DEFINITIONS` (JSON schemas describing the 3 tools).
3. If the LLM response contains `tool_calls`: append the assistant message, run each tool via `dispatch_tool()`, append each result as a `role="tool"` message, then call the LLM again.
4. Repeat until the LLM returns a final text answer (no more tool calls) or `MAX_TOOL_ROUNDS` is hit.

**The agent's behavior changes based on what was returned** — that is the whole point:
- If `search_listings` returns `[]`, the LLM sees the empty result and stops to ask the user to loosen filters. It does **not** call `suggest_outfit`.
- If a real item was found, the LLM moves on to `suggest_outfit`, then `create_fit_card`.

It knows it's done when the LLM responds with text and no tool calls.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict is the source of truth for one interaction (created by `_new_session(query, wardrobe)`). It holds:

```python
{
    "query": query,              # original user query (str)
    "search_results": [],        # list[dict] from search_listings
    "selected_item": None,       # dict — the top listing, index 0 of search_results
    "wardrobe": wardrobe,        # dict with "items" list
    "outfit_suggestion": None,   # str from suggest_outfit
    "fit_card": None,            # str from create_fit_card
    "error": None,               # str if the run ended early, else None
}
```

The found item flows into `suggest_outfit` **without the user re-entering it**: when `search_listings` runs, `dispatch_tool` stores `results[0]` into `session["selected_item"]`. When the LLM next calls `suggest_outfit`, `dispatch_tool` pulls the **real, complete dict** from `session["selected_item"]` and passes it in — so no fields are lost or paraphrased. Likewise `create_fit_card` reads `session["outfit_suggestion"]` and `session["selected_item"]`.

So the LLM decides *which* tool and *when*; Python's `session` dict carries the actual data losslessly between calls.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`) | Tell the user nothing matched; ask them to loosen one filter (raise max_price, drop size, broaden keywords). Do not call suggest_outfit. |
| suggest_outfit | Wardrobe is empty (`len(wardrobe["items"]) == 0`) | Return general styling advice for the item instead of pairing with named pieces. Never return an empty string. |
| create_fit_card | Outfit input is missing or incomplete (empty/whitespace `outfit`) | Return a descriptive error string ("no outfit was provided"); the agent shows it and offers to retry. Never raise. |

---

## Architecture

```
                 ┌─────────────────────────────────────────────┐
 User query  ──▶ │            run_agent(query, wardrobe)         │
                 │                                               │
                 │   ┌───────────────┐     reads/writes          │
                 │   │ Planning loop │◀───────────┐              │
                 │   │ (LLM picks    │            │              │
                 │   │  next tool)   │       ┌────▼─────┐        │
                 │   └──────┬────────┘       │ session  │        │
                 │          │ dispatch_tool  │  dict    │        │
                 │          ▼                │ (state)  │        │
                 │   ┌──────────────┐        └────▲─────┘        │
                 │   │search_listings├─store top hit─┘            │
                 │   └──────┬───────┘                            │
                 │   results==[] ──▶ set session["error"], ask user (STOP)
                 │          │ item found                          │
                 │          ▼                                     │
                 │   ┌──────────────┐  reads selected_item        │
                 │   │suggest_outfit │  (+ wardrobe)               │
                 │   └──────┬───────┘  empty wardrobe ▶ general advice
                 │          ▼                                     │
                 │   ┌──────────────┐  reads outfit + item        │
                 │   │create_fit_card│  blank outfit ▶ error string│
                 │   └──────┬───────┘                            │
                 └──────────┼───────────────────────────────────┘
                            ▼
                   Final answer to user (listing + outfit + fit card)
```

The LLM chooses each tool; the `session` dict (right side) carries real objects between tools; error paths branch off each tool (empty search stops the run; empty wardrobe and blank outfit degrade gracefully).

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
I'll use **Claude (Claude Code)**. For each tool I'll hand it that tool's section above (the input table, the return-shape table, and the failure-mode row) plus `utils/data_loader.py`. I expect it to produce one function at a time in `tools.py`:
- `search_listings` using `load_listings()` — filter by `max_price` and `size`, score by keyword overlap with `description`, drop zero-score, sort descending.
- `suggest_outfit` and `create_fit_card` using the Groq client.
I'll verify each before trusting it: run `search_listings("vintage graphic tee", max_price=30)` and confirm it returns a list of dicts with the expected keys and that `results[0]["title"]` looks right; run `search_listings("designer ballgown", max_price=5)` and confirm it returns `[]`; call `suggest_outfit` once with the example wardrobe and once with the empty wardrobe.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the **Planning Loop**, **State Management**, and **Architecture** sections plus the prior project's `agent.py` as the pattern. I expect `TOOL_DEFINITIONS` (3 JSON schemas), `dispatch_tool` (routes calls and reads/writes `session`, storing `results[0]` in `selected_item`), and the `run_agent` loop. I'll verify with the two end-to-end runs below: the happy path must produce a non-empty `fit_card`, and the no-results path must set `session["error"]` and never call `suggest_outfit`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
`run_agent` builds `messages` (system prompt with the wardrobe embedded + the query) and calls the LLM. The LLM decides to call `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`.

**Step 2:**
`search_listings` returns a non-empty `list[dict]`. `dispatch_tool` stores the top hit in `session["selected_item"]` (e.g. `lst_002`, "Y2K Baby Tee — Butterfly Print", $18, depop) and returns the results to the LLM as a `role="tool"` message. The LLM sees a real match, so it next calls `suggest_outfit`.

**Step 3:**
`dispatch_tool` feeds the real `session["selected_item"]` dict and the wardrobe into `suggest_outfit`. The wardrobe is non-empty, so it returns a string pairing the tee with named pieces (baggy straight-leg jeans `w_001`, chunky white sneakers `w_007`). Stored in `session["outfit_suggestion"]`.

**Step 4:**
The LLM calls `create_fit_card`. `dispatch_tool` passes `session["outfit_suggestion"]` and `session["selected_item"]`. It returns a 2–4 sentence caption mentioning the tee, $18, and depop. Stored in `session["fit_card"]`. The LLM then returns a final text answer (no more tool calls) and the loop ends.

**Final output to user:**
The found listing (title, price, platform), the outfit idea using their own jeans and sneakers, and a shareable fit-card caption — all from one query, with the item flowing search → suggest → card without the user re-entering it.
