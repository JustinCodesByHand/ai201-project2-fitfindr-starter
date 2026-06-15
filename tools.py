"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # Step 1: Load every listing from the JSON file into a Python list
    # load_listings() returns a list of dicts — each dict is one item for sale
    # Example: all_listings[0] is {"id": "lst_001", "title": "Vintage Levi's...", "price": 38.0, ...}
    all_listings = load_listings()

    # Step 2: Keep only listings whose price is at or below max_price
    # Skip this filter entirely if max_price is None (user didn't set a price limit)
    # listing["price"] is a float — compare it to max_price
    if max_price is not None:
        all_listings = [l for l in all_listings if l["price"] <= max_price]

    # Step 3: Keep only listings whose size contains the size the user asked for
    # Skip this filter entirely if size is None
    # listing["size"] is a string like "S/M" — use .lower() on both sides so "m" matches "S/M"
    if size is not None:
        all_listings = [l for l in all_listings if size.lower() in l["size"].lower()]

    # Step 4: Score each remaining listing by how many of the user's keywords appear in it
    # Split description into individual words: description.lower().split()
    # For each listing, count how many of those words appear in listing["title"].lower()
    #   or listing["description"].lower() or anywhere in listing["style_tags"]
    # Store each listing + its score together so you can sort later
    # Hint: build a list of tuples like [(score, listing), (score, listing), ...]
    keywords = description.lower().split()
    scored = []
    for listing in all_listings:
        searchable = (
            listing["title"].lower()
            + " " + listing["description"].lower()
            + " " + " ".join(listing["style_tags"]).lower()
        )
        score = sum(1 for kw in keywords if kw in searchable)
        scored.append((score, listing))

    # Step 5: Drop any listings with a score of 0 — they matched no keywords at all
    scored = [(score, listing) for score, listing in scored if score > 0]

    # Step 6: Sort by score, highest first
    # If you used tuples: sorted(..., reverse=True) then pull just the listing dict back out
    scored.sort(key=lambda x: x[0], reverse=True)

    # Step 7: Return the final list of listing dicts (not tuples — just the dicts)
    # If nothing survived the filters, this returns [] — that is correct, do not raise
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    # Step 1: Check whether wardrobe["items"] is empty
    # wardrobe["items"] is a list of dicts — each dict has keys: id, name, category, colors, style_tags, notes
    # Example: wardrobe["items"][0] is {"id": "w_001", "name": "Baggy straight-leg jeans", "category": "bottoms", ...}
    items = wardrobe["items"]

    if not items:
        # Step 2: Wardrobe is empty — ask LLM for general styling advice
        # Tell LLM about the new item and ask what kinds of pieces pair well with it
        prompt = (
            f"A user is considering buying this thrifted item:\n"
            f"Name: {new_item['title']}\n"
            f"Style: {', '.join(new_item['style_tags'])}\n"
            f"Colors: {', '.join(new_item['colors'])}\n"
            f"Category: {new_item['category']}\n\n"
            f"They have no wardrobe entered yet. Give them 1-2 general outfit ideas — "
            f"what kinds of pieces pair well with this item, what vibe it suits, "
            f"and how they might style it. Be specific about garment types and aesthetics."
        )
    else:
        # Step 3: Wardrobe has items — format them into a list for the prompt
        # Build a readable string of wardrobe pieces so the LLM can name specific ones
        # Each item in wardrobe["items"] has a "name" key — e.g. "Baggy straight-leg jeans, dark wash"
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']})" for item in items
        )
        prompt = (
            f"A user is considering buying this thrifted item:\n"
            f"Name: {new_item['title']}\n"
            f"Style: {', '.join(new_item['style_tags'])}\n"
            f"Colors: {', '.join(new_item['colors'])}\n"
            f"Category: {new_item['category']}\n\n"
            f"Their current wardrobe includes:\n{wardrobe_lines}\n\n"
            f"Suggest 1-2 complete outfit combinations using the new item paired with "
            f"specific pieces from their wardrobe. Name the exact wardrobe pieces you're pairing. "
            f"Be specific about the aesthetic and vibe of each outfit."
        )

    # Step 4: Call the LLM and return its response as a string
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Step 1: Guard against empty outfit string — return an error message string, do NOT raise
    # outfit.strip() removes whitespace — if nothing is left, the input is unusable
    if not outfit or not outfit.strip():
        return "Could not generate a fit card — outfit suggestion was empty."

    # Step 2: Build a prompt giving the LLM the item details + outfit, asking for a caption
    # new_item is a listing dict — access fields like new_item["title"], new_item["price"], new_item["platform"]
    # The caption must mention item name, price, and platform once each, sound casual, not like a product description
    prompt = (
        f"Write a 2-4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
        f"The thrifted item: {new_item['title']} — ${new_item['price']:.2f} on {new_item['platform']}\n"
        f"The full outfit: {outfit}\n\n"
        f"Rules:\n"
        f"- Sound like a real person posting an OOTD, not a product description\n"
        f"- Mention the item name, price, and platform naturally (once each)\n"
        f"- Capture the specific vibe of the outfit\n"
        f"- Keep it 2-4 sentences\n"
        f"- No hashtags"
    )

    # Step 3: Call the LLM with higher temperature so captions sound different each time
    # temperature=0.9 makes the output more creative and varied vs the default 0.7
    client = _get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return response.choices[0].message.content
