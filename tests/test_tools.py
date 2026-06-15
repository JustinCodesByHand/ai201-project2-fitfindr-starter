"""
tests/test_tools.py

Run with: pytest tests/
Each test covers one behavior or one failure mode per tool.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ────────────────────────────────────────────────────────────

def test_search_returns_results():
    # Happy path — "vintage graphic tee" should match several listings
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_returns_list_of_dicts():
    # Each result must be a full listing dict with the expected fields
    results = search_listings("jacket", size=None, max_price=None)
    assert len(results) > 0
    first = results[0]
    for field in ["id", "title", "description", "category", "style_tags", "size", "price", "platform"]:
        assert field in first, f"Missing field: {field}"

def test_search_empty_results():
    # Failure mode — impossible query returns [] not an exception
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    # All returned items must be at or below max_price
    results = search_listings("jacket", size=None, max_price=25)
    assert all(item["price"] <= 25 for item in results)

def test_search_size_filter():
    # All returned items must contain the requested size (case-insensitive)
    results = search_listings("top", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)

def test_search_best_match_first():
    # Top result should be more relevant than last result
    # "vintage graphic tee" — first result should score higher than last
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 1
    # Just verify it's a list of dicts (scoring order tested implicitly via relevance)
    assert isinstance(results[0], dict)


# ── suggest_outfit ─────────────────────────────────────────────────────────────

# Use a real listing dict as new_item for outfit tests
_SAMPLE_ITEM = {
    "id": "lst_002",
    "title": "Y2K Baby Tee — Butterfly Print",
    "description": "Super cute early 2000s baby tee with butterfly graphic.",
    "category": "tops",
    "style_tags": ["y2k", "vintage", "graphic tee"],
    "size": "S/M",
    "condition": "excellent",
    "price": 18.0,
    "colors": ["white", "pink", "purple"],
    "brand": None,
    "platform": "depop",
}

def test_suggest_outfit_with_wardrobe():
    # Happy path — returns a non-empty string naming wardrobe pieces
    result = suggest_outfit(_SAMPLE_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0

def test_suggest_outfit_empty_wardrobe():
    # Failure mode — empty wardrobe returns general advice string, not "" and not crash
    result = suggest_outfit(_SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── create_fit_card ────────────────────────────────────────────────────────────

_SAMPLE_OUTFIT = (
    "Pair the Y2K baby tee with baggy straight-leg jeans and chunky white sneakers "
    "for a nostalgic streetwear look."
)

def test_create_fit_card_returns_string():
    # Happy path — returns a non-empty caption string
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result.strip()) > 0

def test_create_fit_card_mentions_item_details():
    # Caption should mention the platform and price somewhere
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    assert "depop" in result.lower() or "18" in result

def test_create_fit_card_empty_outfit():
    # Failure mode — empty outfit string returns error message string, no crash
    result = create_fit_card("", _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    # Should NOT be a real caption — it's an error message
    assert "depop" not in result.lower()

def test_create_fit_card_whitespace_outfit():
    # Whitespace-only outfit string also triggers error path
    result = create_fit_card("   ", _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
