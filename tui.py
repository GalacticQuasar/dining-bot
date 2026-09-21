#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["textual>=1.0", "httpx"]
# ///
"""Purdue dining TUI: every dining court plus 1bowl, side by side.

Run:
    uv run tui.py
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx
from rich.markup import escape
from textual.app import App, ComposeResult
from textual.containers import HorizontalScroll, VerticalScroll
from textual.widgets import Footer, Header, LoadingIndicator, Static

DINING_API_URL = "https://api.hfs.purdue.edu/menus/v3/GraphQL"

LOCATIONS_QUERY = """
query getStartLocations {
  diningCourtCategories {
    name
    diningCourts {
      name
      formalName
    }
  }
}
"""

MENU_QUERY = """
query getLocationMenu($name: String!, $date: Date!) {
  diningCourtByName(name: $name) {
    formalName
    dailyMenu(date: $date) {
      meals {
        name
        status
        stations {
          name
          items {
            item {
              name
              traits {
                name
              }
            }
          }
        }
      }
    }
  }
}
"""


async def graphql(client, operation_name, query, variables):
    payload = {"operationName": operation_name, "query": query, "variables": variables}
    response = await client.post(DINING_API_URL, json=payload)
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(f"API returned non-JSON (HTTP {response.status_code})") from exc
    if body.get("errors") and not body.get("data"):
        messages = "; ".join(str(e.get("message", "?")) for e in body["errors"])
        raise RuntimeError(messages or f"API error (HTTP {response.status_code})")
    return body


async def pick_locations(client):
    """Dining courts in API order, with 1bowl pinned last. Data-driven:
    falls back to courts only if 1bowl is missing from the API."""
    body = await graphql(client, "getStartLocations", LOCATIONS_QUERY, {})
    categories = (body.get("data") or {}).get("diningCourtCategories") or []
    courts = []
    one_bowl = None
    for category in categories:
        for court in category.get("diningCourts") or []:
            name = court.get("name")
            if not name:
                continue
            if category.get("name") == "Dining Courts":
                courts.append(name)
            if "1bowl" in name.lower() and one_bowl is None:
                one_bowl = name
    if not courts:
        raise RuntimeError("no dining courts found in API response")
    return courts + ([one_bowl] if one_bowl else [])


async def fetch_menu(client, court_name, date_str):
    """Fetch and flatten one location's menu. Returns
    {court, formal_name, meals: [{name, status, items: [{station, item, traits}]}]}."""
    body = await graphql(
        client, "getLocationMenu", MENU_QUERY, {"name": court_name, "date": date_str}
    )
    court = (body.get("data") or {}).get("diningCourtByName")
    if not court:
        raise RuntimeError(f"no data for location {court_name!r}")
    formal_name = court.get("formalName", court_name)
    meals = []
    for meal in (court.get("dailyMenu") or {}).get("meals") or []:
        items = []
        for station in meal.get("stations") or []:
            for entry in station.get("items") or []:
                item = entry.get("item")
                if not item:
                    continue
                traits = [t["name"] for t in (item.get("traits") or []) if t.get("name")]
                items.append(
                    {"station": station["name"], "item": item["name"], "traits": traits}
                )
        meals.append({"name": meal["name"], "status": meal.get("status", ""), "items": items})
    return {"court": court_name, "formal_name": formal_name, "meals": meals}


def trait_markup(trait):
    lowered = trait.lower()
    if lowered == "vegan":
        return r"[green]\[vegan][/green]"
    if lowered == "vegetarian":
        return r"[yellow]\[vegetarian][/yellow]"
    return rf"[dim]\[{escape(trait)}][/dim]"


def filter_meals(meals, meal_filter):
    """Keep only meals whose name matches meal_filter (case-insensitive).
    None or empty means no filtering."""
    if not meal_filter:
        return meals
    target = meal_filter.strip().lower()
    return [m for m in meals if m["name"].strip().lower() == target]


def menu_markup(entry, show_traits=False, meal_filter=None):
    all_meals = entry["meals"]
    if not all_meals:
        return "[dim italic]Closed or no menu for this date.[/dim italic]"
    meals = filter_meals(all_meals, meal_filter)
    if not meals:
        return f"[dim italic](no {escape(meal_filter)} served here)[/dim italic]"
    parts = []
    for meal in meals:
        status = meal["status"].strip().upper()
        if status == "OPEN":
            status_text = "[green]\N{bullet} OPEN[/green]"
        elif status:
            status_text = f"[dim]({escape(meal['status'])})[/dim]"
        else:
            status_text = ""
        header = f"[bold]{escape(meal['name'])}[/bold]  {status_text}".rstrip()
        parts.append(header)
        by_station = {}
        for item in meal["items"]:
            by_station.setdefault(item["station"], []).append(item)
        for station, items in by_station.items():
            parts.append(f"[bold cyan]{escape(station)}[/bold cyan]")
            for item in items:
                line = f"  \N{bullet} {escape(item['item'])}"
                if show_traits and item["traits"]:
                    tags = " ".join(trait_markup(t) for t in item["traits"])
                    line = f"{line} {tags}"
                parts.append(line)
            parts.append("")
        parts.append("")
    return "\n".join(parts).rstrip()


class LocationPane(VerticalScroll):
    """One location's menu, independently scrollable."""

    def __init__(self, court_name, **kwargs):
        super().__init__(**kwargs)
        self.court_name = court_name
        self.border_title = court_name
        self.entry = None

    async def show_loading(self):
        self.entry = None
        self.border_title = self.court_name
        await self.remove_children()
        await self.mount(LoadingIndicator())

    async def show_error(self, message):
        self.entry = None
        await self.remove_children()
        await self.mount(Static(f"[red]Error: {escape(str(message))}[/red]"))

    async def show_menu(self, entry):
        self.entry = entry
        self.border_title = entry["formal_name"]
        await self.refresh_content()

    async def refresh_content(self):
        await self.remove_children()
        await self.mount(
            Static(menu_markup(self.entry, self.app.show_traits, self.app.meal_filter))
        )
        self.scroll_to(y=0, animate=False)


class DiningApp(App):
    TITLE = "Purdue Dining"

    CSS = """
    #panes {
        height: 1fr;
    }
    LocationPane {
        width: 40;
        height: 1fr;
        border: tall $primary;
        padding: 0 1;
        background: $surface;
    }
    LocationPane:focus {
        border: tall $secondary;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "today", "Today"),
        ("n", "next_day", "Next day"),
        ("p", "previous_day", "Prev day"),
        ("v", "toggle_traits", "Diet labels"),
        ("b", "filter_breakfast", "Breakfast"),
        ("l", "filter_lunch", "Lunch"),
        ("d", "filter_dinner", "Dinner"),
        ("a", "filter_all", "All meals"),
    ]

    def __init__(self):
        super().__init__()
        self._date = date.today()
        self._loaded = False
        self._loaded_date = None
        self.show_traits = False
        self.meal_filter = None
        self.courts = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield HorizontalScroll(id="panes")
        yield Footer()

    async def on_mount(self) -> None:
        container = self.query_one("#panes", HorizontalScroll)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                self.courts = await pick_locations(client)
        except Exception as exc:
            await container.mount(
                Static(f"[red]Failed to load locations: {escape(str(exc))}[/red]")
            )
            return
        panes = [LocationPane(court) for court in self.courts]
        await container.mount_all(panes)
        panes[0].focus()
        await self.load_menus()

    async def load_menus(self) -> None:
        self._loaded = False
        date_str = self._date.isoformat()
        self.update_sub_title()
        panes = list(self.query(LocationPane))
        for pane in panes:
            await pane.show_loading()
        async with httpx.AsyncClient(timeout=15) as client:
            results = await asyncio.gather(
                *(fetch_menu(client, pane.court_name, date_str) for pane in panes),
                return_exceptions=True,
            )
        for pane, result in zip(panes, results):
            if isinstance(result, BaseException):
                await pane.show_error(result)
            else:
                await pane.show_menu(result)
        self._loaded = True
        self._loaded_date = date_str

    def update_sub_title(self):
        date_str = self._date.isoformat()
        weekday = self._date.strftime("%A")
        meal = self.meal_filter or "all meals"
        self.sub_title = f"{date_str} ({weekday}) \N{RIGHTWARDS DOUBLE ARROW} {meal}"

    def set_meal_filter(self, meal):
        if not self.courts or meal == self.meal_filter:
            return
        self.meal_filter = meal
        self.update_sub_title()
        for pane in self.query(LocationPane):
            if pane.entry is not None:
                pane.call_after_refresh(pane.refresh_content)

    def change_date(self, new_date):
        if not self.courts:
            return
        if new_date == self._date and self._loaded:
            return
        self._date = new_date
        self.run_worker(self.load_menus(), exclusive=True)

    def action_today(self):
        self.change_date(date.today())

    def action_next_day(self):
        self.change_date(self._date + timedelta(days=1))

    def action_previous_day(self):
        self.change_date(self._date - timedelta(days=1))

    async def action_toggle_traits(self):
        if not self.courts:
            return
        self.show_traits = not self.show_traits
        for pane in self.query(LocationPane):
            if pane.entry is not None:
                await pane.refresh_content()

    def action_filter_breakfast(self):
        self.set_meal_filter("Breakfast")

    def action_filter_lunch(self):
        self.set_meal_filter("Lunch")

    def action_filter_dinner(self):
        self.set_meal_filter("Dinner")

    def action_filter_all(self):
        self.set_meal_filter(None)


if __name__ == "__main__":
    DiningApp().run()