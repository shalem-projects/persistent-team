"""Tests for project_search.py — run with: python -B -m pytest test_project_search.py -v"""

from project_search import search


def test_exact_id_food():
    r = search("food")
    assert r["match"] == "food"


def test_exact_id_today():
    r = search("today")
    assert r["match"] == "today"


def test_alias_rectangle_game():
    r = search("the rectangle game")
    assert r["match"] == "rectangles-game"


def test_alias_food_thing():
    r = search("the food thing")
    assert r["match"] == "food"


def test_alias_city_ranking():
    r = search("city ranking")
    assert r["match"] == "דירוג_ערים"


def test_hebrew_uvacharta():
    r = search("ובחרת")
    assert r["match"] == "uvacharta_bachayim"


def test_hebrew_plonter():
    r = search("פלונטר")
    assert r["match"] == "plonter"


def test_arabic_syntax():
    r = search("arabic syntax")
    assert r["match"] == "plonter"


def test_sel_research():
    r = search("sel research")
    assert r["match"] == "israel_science_academy"


def test_ambiguous_game_no_auto():
    r = search("game")
    assert r["match"] is None
    assert len(r["candidates"]) > 1


def test_ambiguous_game_has_multiple():
    r = search("game")
    pids = [c["project_id"] for c in r["candidates"]]
    assert "tax_collector" in pids
    assert "rectangles-game" in pids
    assert "number-game" in pids


def test_tax_game_top_result():
    r = search("math game with tax")
    assert r["candidates"][0]["project_id"] == "tax_collector"


def test_no_match():
    r = search("xyzzy nonsense gibberish")
    assert r["match"] is None
    assert len(r["candidates"]) == 0


def test_control_panel():
    r = search("control panel")
    assert r["match"] == "control-panel"


def test_telegram_bot():
    r = search("telegram bot")
    assert r["candidates"][0]["project_id"] == "lili"
