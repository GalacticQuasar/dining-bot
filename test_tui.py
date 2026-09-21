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
from datetime import date, timedelta

import tui


async def wait_loaded(app, timeout=30):
    deadline = asyncio.get_event_loop().time() + timeout
    while not app._loaded:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("menus did not load in time")
        await asyncio.sleep(0.1)


async def main():
    app = tui.DiningApp()
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
        assert "Chicken Alfredo Bowl" in bowl_content, "1bowl dinner should render"
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

    print("smoke test passed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)