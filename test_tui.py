#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["textual>=1.0", "httpx"]
# ///
"""Headless smoke test for tui.py. No pytest needed: uv run test_tui.py

Runs the Textual app with a pilot (no TTY required), waits for the live API
menus to load, and asserts the panes render, then exercises date navigation.
"""

import asyncio
import sys
from datetime import date, datetime, timedelta, timezone

import tui


async def wait_loaded(app, timeout=30):
    deadline = asyncio.get_event_loop().time() + timeout
    while not app._loaded:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("menus did not load in time")
        await asyncio.sleep(0.1)


def test_current_meal():
    def at(hour):
        return datetime(2026, 10, 16, hour, tzinfo=timezone.utc)

    def meal(name, start, end):
        return {"name": name, "start": at(start), "end": at(end), "items": []}

    entries = [
        {"meals": [meal("Breakfast", 7, 10), meal("Lunch", 11, 14), meal("Dinner", 17, 21)]},
        # Closed meals have no hours and are never picked.
        {"meals": [{"name": "Brunch", "start": None, "end": None, "items": []}]},
    ]
    assert tui.current_meal(entries, at(8)) == "Breakfast"
    assert tui.current_meal(entries, at(12)) == "Lunch"
    assert tui.current_meal(entries, at(15)) == "Dinner", "between meals: next one"
    assert tui.current_meal(entries, at(6)) == "Breakfast", "before opening: first meal"
    assert tui.current_meal(entries, at(22)) is None, "after close: all meals"
    assert tui.current_meal([], at(12)) is None
    print("current_meal ok")


async def main():
    test_current_meal()

    # The checks below assume the default all-meals view.
    app = tui.DiningApp(auto_meal=False)
    async with app.run_test(size=(200, 50)) as pilot:
        # Locations fetch -> panes mount -> menus load.
        await wait_loaded(app)

        panes = list(app.query(tui.LocationPane))
        assert app.courts, "no locations resolved"
        assert len(panes) == len(app.courts), "pane count mismatch"
        print(f"panes: {len(panes)} ({', '.join(app.courts)})")
        assert len(panes) == 6, f"expected 6 panes (5 courts + 1bowl), got {len(panes)}"
        assert app.courts[-1].lower().startswith("1bowl"), "1bowl should be pinned last"

        # Every pane should have swapped its LoadingIndicator for real content.
        for pane in panes:
            children = list(pane.children)
            assert children, f"pane {pane.court_name!r} has no content"
            assert not any(
                isinstance(c, tui.LoadingIndicator) for c in children
            ), f"pane {pane.court_name!r} still loading"
            content = children[0].content
            assert "Error:" not in content, f"pane {pane.court_name!r} errored: {content}"
            print(f"  {pane.court_name}: {len(content)} chars of menu")

        # At least one pane should have actual menu items (bullets), not just
        # the closed notice.
        with_menu = sum(
            1
            for p in panes
            if "\N{bullet}" in p.children[0].content
        )
        assert with_menu >= 1, "no pane rendered an actual menu"
        print(f"panes with menus: {with_menu}/6")

        # Date navigation: n -> tomorrow.
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        await pilot.press("n")
        await wait_loaded(app)
        assert app._loaded_date == tomorrow, f"expected {tomorrow}, got {app._loaded_date}"
        print(f"next day ok: {app._loaded_date}")

        # t -> back to today.
        await pilot.press("t")
        await wait_loaded(app)
        assert app._loaded_date == date.today().isoformat()
        print(f"today ok: {app._loaded_date}")

        # v toggles diet labels: hidden by default, shown after one press.
        any_traits = any(
            len(it["traits"]) > 0
            for p in panes
            if p.entry
            for meal in p.entry["meals"]
            for it in meal["items"]
        )
        assert any_traits, "API returned no traits at all; toggle test would be vacuous"
        before = panes[0].children[0].content
        assert app.show_traits is False
        assert "[vegan]" not in before and "[vegetarian]" not in before, (
            "traits should be hidden by default"
        )
        await pilot.press("v")
        await pilot.pause()
        assert app.show_traits is True
        after = panes[0].children[0].content
        assert any(tag in after for tag in ("[vegan]", "[vegetarian]", "[dim][")), (
            "traits should be visible after toggle"
        )
        print(f"toggle on ok: {len(before)} -> {len(after)} chars in pane 0")
        assert len(after) > len(before), "showing traits should add characters"

        # v again hides them.
        await pilot.press("v")
        await pilot.pause()
        assert app.show_traits is False
        assert panes[0].children[0].content == before, "toggle off should restore content"
        print("toggle off ok")

        # Meal filtering: b/l/d narrow panes to one meal, a restores.
        def pane_content(pane):
            return pane.children[0].content

        all_content = pane_content(panes[0])
        assert "Breakfast" in all_content or "Lunch" in all_content, (
            "expected multiple meals in default view"
        )
        await pilot.press("l")
        await pilot.pause()
        assert app.meal_filter == "Lunch"
        lunch_content = pane_content(panes[0])
        assert "Breakfast" not in lunch_content, "lunch filter should drop Breakfast"
        assert "Dinner" not in lunch_content, "lunch filter should drop Dinner"
        assert "no Lunch served here" not in lunch_content, (
            "Earhart should serve Lunch today"
        )
        print(f"lunch filter ok: {len(all_content)} -> {len(lunch_content)} chars")

        # Dinner filter: 1bowl serves dinner, so no 'no dinner' notice expected
        # there; panes show only Dinner sections.
        await pilot.press("d")
        await pilot.pause()
        assert app.meal_filter == "Dinner"
        dinner_content = pane_content(panes[0])
        assert "Breakfast" not in dinner_content and "Lunch" not in dinner_content
        bowl_content = pane_content(panes[-1])
        bowl_dinner = tui.filter_meals(panes[-1].entry["meals"], "Dinner")
        assert bowl_dinner and bowl_dinner[0]["items"], "1bowl should serve dinner today"
        first_item = bowl_dinner[0]["items"][0]["item"]
        assert first_item in bowl_content, f"1bowl dinner should render {first_item!r}"
        print("dinner filter ok")

        # Breakfast on 1bowl (it serves Lunch/Dinner only) shows the notice.
        await pilot.press("b")
        await pilot.pause()
        assert app.meal_filter == "Breakfast"
        bowl_breakfast = pane_content(panes[-1])
        assert "no Breakfast served here" in bowl_breakfast, (
            "1bowl pane should show the no-breakfast notice"
        )
        print("breakfast notice on 1bowl ok")

        # a restores the full menu exactly.
        await pilot.press("a")
        await pilot.pause()
        assert app.meal_filter is None
        assert pane_content(panes[0]) == all_content, (
            "all-meals view should match the original render"
        )
        print("all meals restored ok")

        # Pressing the same filter again is a no-op (guard clause).
        await pilot.press("l")
        await pilot.pause()
        content_l = pane_content(panes[0])
        await pilot.press("l")
        await pilot.pause()
        assert pane_content(panes[0]) == content_l, "repeat filter press should be a no-op"
        print("repeat filter no-op ok")

        # Left/right move focus between panes, clamped at both ends.
        panes[0].focus()
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is panes[1], "right should focus the next pane"
        await pilot.press("left", "left")
        await pilot.pause()
        assert app.focused is panes[0], "left should stop at the first pane"
        for _ in panes:
            await pilot.press("right")
        await pilot.pause()
        assert app.focused is panes[-1], "right should stop at the last pane"
        print("pane navigation ok")

    # At 80 columns most panes are off-screen; moving to the last one must
    # scroll it into view.
    app = tui.DiningApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await wait_loaded(app)
        panes = list(app.query(tui.LocationPane))
        container = app.query_one("#panes")
        assert container.scroll_x == 0

        # Default app starts filtered to the current (or next) meal.
        expected = tui.current_meal(
            [p.entry for p in panes if p.entry], datetime.now().astimezone()
        )
        assert app.meal_filter == expected, f"expected {expected!r}, got {app.meal_filter!r}"
        print(f"auto meal ok: {app.meal_filter or 'all meals'}")
        for _ in panes:
            await pilot.press("right")
        await pilot.pause(0.5)
        assert app.focused is panes[-1]
        assert container.scroll_x > 0, "focusing an off-screen pane should scroll to it"
        assert panes[-1].region.right <= container.region.right, "last pane should be fully visible"
        print(f"scroll into view ok: scroll_x={container.scroll_x}")

    print("smoke test passed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)