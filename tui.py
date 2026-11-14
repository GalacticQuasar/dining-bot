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
from datetime import date, datetime, timedelta

import httpx
from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalScroll, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, LoadingIndicator, SelectionList, Static

PANE_MIN_WIDTH = 38
COLLAPSED_WIDTH = 18

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
        startTime
        endTime
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
    {court, formal_name, meals: [{name, status, start, end, items: [{station, item, traits}]}]},
    where start/end are aware datetimes, or None when the API gives no hours."""
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
        meals.append(
            {
                "name": meal["name"],
                "status": meal.get("status", ""),
                "start": parse_time(meal.get("startTime")),
                "end": parse_time(meal.get("endTime")),
                "items": items,
            }
        )
    return {"court": court_name, "formal_name": formal_name, "meals": meals}


def parse_time(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def current_meal(entries, now):
    """Name of the meal being served at `now` at any location, else the
    next one to start. None once every meal has ended."""
    windows = sorted(
        (meal["start"], meal["end"], meal["name"])
        for entry in entries
        for meal in entry["meals"]
        if meal["start"] and meal["end"]
    )
    for start, end, name in windows:
        if start <= now < end:
            return name
    for start, _, name in windows:
        if start > now:
            return name
    return None


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


def highlight(text, query):
    """Escape text for markup, marking every case-insensitive match of query."""
    if not query:
        return escape(text)
    lowered, target = text.lower(), query.lower()
    parts = []
    start = 0
    while (found := lowered.find(target, start)) != -1:
        end = found + len(target)
        parts.append(escape(text[start:found]))
        parts.append(f"[bold reverse]{escape(text[found:end])}[/bold reverse]")
        start = end
    parts.append(escape(text[start:]))
    return "".join(parts)


ITEM_PREFIX = "  \N{bullet} "


def markup_renderable(markup):
    """Turn menu markup into a Rich renderable. Runs of item lines go into a
    two-column grid, so a long name wraps under itself, not under the bullet."""
    parts = []
    grid = None
    for line in markup.split("\n"):
        if not line.startswith(ITEM_PREFIX):
            grid = None
            parts.append(Text.from_markup(line))
            continue
        if grid is None:
            grid = Table.grid(padding=(0, 1), expand=True)
            grid.add_column(width=len(ITEM_PREFIX) - 1, no_wrap=True)
            grid.add_column(ratio=1, overflow="fold")
            parts.append(grid)
        grid.add_row(ITEM_PREFIX.rstrip(), Text.from_markup(line[len(ITEM_PREFIX):]))
    return Group(*parts)


def notice(text):
    return f"[dim italic]{text}[/dim italic]"


def menu_markup(entry, show_traits=False, meal_filter=None, query=""):
    """Markup for one location's menu, plus whether it has no items to show
    (closed, meal not served, or nothing matches), so the pane can collapse."""
    all_meals = entry["meals"]
    if not all_meals:
        return notice("Closed or no menu for this date."), True
    meals = filter_meals(all_meals, meal_filter)
    if not meals:
        return notice(f"(no {escape(meal_filter)} served here)"), True
    query = query.strip()
    if query:
        target = query.lower()
        meals = [
            {**meal, "items": [it for it in meal["items"] if target in it["item"].lower()]}
            for meal in meals
        ]
        meals = [meal for meal in meals if meal["items"]]
        if not meals:
            return notice(f"(no matches for {escape(query)!r})"), True
    if not any(meal["items"] for meal in meals):
        if meal_filter:
            return notice(f"({escape(meal_filter)} closed)"), True
        return notice("(closed all day)"), True
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
                line = f"{ITEM_PREFIX}{highlight(item['item'], query)}"
                if show_traits and item["traits"]:
                    tags = " ".join(trait_markup(t) for t in item["traits"])
                    line = f"{line} {tags}"
                parts.append(line)
            parts.append("")
        parts.append("")
    return "\n".join(parts).rstrip(), False


class LocationPane(VerticalScroll):
    """One location's menu, independently scrollable."""

    # Override VerticalScroll's horizontal scroll keys: left/right move
    # between panes instead.
    BINDINGS = [
        Binding("left", "app.focus_pane(-1)", "Prev court", key_display="\N{LEFTWARDS ARROW}"),
        Binding("right", "app.focus_pane(1)", "Next court", key_display="\N{RIGHTWARDS ARROW}"),
    ]

    def __init__(self, court_name, **kwargs):
        super().__init__(**kwargs)
        self.court_name = court_name
        self.border_title = court_name
        self.entry = None
        # The markup behind the current content (tests read it).
        self.markup = ""

    async def show_loading(self):
        self.entry = None
        self.markup = ""
        self.border_title = self.court_name
        self.remove_class("collapsed")
        await self.remove_children()
        await self.mount(LoadingIndicator())

    async def show_error(self, message):
        self.entry = None
        self.markup = f"[red]Error: {escape(str(message))}[/red]"
        self.remove_class("collapsed")
        await self.remove_children()
        await self.mount(Static(markup_renderable(self.markup)))

    async def show_menu(self, entry):
        self.entry = entry
        await self.refresh_content()

    async def refresh_content(self):
        self.markup, empty = menu_markup(
            self.entry, self.app.show_traits, self.app.meal_filter, self.app.search_query
        )
        # Nothing to show: shrink to a narrow strip so menus get the room.
        if self.has_class("collapsed") != empty:
            self.set_class(empty, "collapsed")
            self.app.size_panes()
        self.border_title = self.court_name if empty else self.entry["formal_name"]
        renderable = markup_renderable(self.markup)
        # Update in place when possible: overlapping remove/mount calls (e.g.
        # one per search keystroke) could otherwise leave two Statics.
        children = list(self.children)
        if len(children) == 1 and isinstance(children[0], Static):
            children[0].update(renderable)
        else:
            await self.remove_children()
            await self.mount(Static(renderable))
        self.scroll_to(y=0, animate=False)


class CourtPicker(ModalScreen):
    """Checklist of locations; toggling one shows/hides its pane right away."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("c", "dismiss", "Close"),
    ]

    CSS = """
    CourtPicker {
        align: center middle;
    }
    #picker {
        width: 44;
        height: auto;
        border: tall $primary;
        background: $surface;
        padding: 0 1;
    }
    #picker SelectionList {
        height: auto;
        border: none;
    }
    """

    def __init__(self, courts, hidden):
        super().__init__()
        self.courts = courts
        self.hidden = set(hidden)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker") as picker:
            picker.border_title = "Locations"
            yield SelectionList(
                *((court, court, court not in self.hidden) for court in self.courts)
            )
            yield Static("[dim]Space/Enter toggles \N{middle dot} Esc closes[/dim]")

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        selected = set(event.selection_list.selected)
        if not selected:
            # Keep at least one pane: put back the one just unchecked.
            for court in self.courts:
                if court not in self.hidden:
                    event.selection_list.select(court)
            self.app.notify("Keep at least one location", severity="warning")
            return
        self.hidden = set(self.courts) - selected
        self.app.set_hidden_courts(self.hidden)


class DiningApp(App):
    TITLE = "Purdue Dining"

    CSS = """
    #panes {
        height: 1fr;
    }
    LocationPane {
        height: 1fr;
        border: tall $primary;
        padding: 0 1;
        background: $surface;
    }
    LocationPane:focus {
        border: tall $secondary;
    }
    LocationPane.collapsed {
        color: $text-muted;
    }
    #search {
        display: none;
    }
    #search.visible {
        display: block;
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
        ("c", "pick_courts", "Courts"),
        Binding("slash", "search", "Search", key_display="/"),
        # Priority so the screen's own escape binding doesn't swallow it.
        Binding("escape", "clear_search", "Clear search", show=False, priority=True),
    ]

    def __init__(self, auto_meal=True):
        super().__init__()
        self.auto_meal = auto_meal
        self.hidden_courts = set()
        self._date = date.today()
        self._loaded = False
        self._loaded_date = None
        self.show_traits = False
        self.meal_filter = None
        self.search_query = ""
        self._search_return = None
        self._search = None
        self.courts = []
        # Kept as a list rather than queried: while a modal is open,
        # App.query() searches the modal instead of the main screen.
        self.panes = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield HorizontalScroll(id="panes")
        self._search = Input(placeholder="Search items (Enter to keep, Esc to clear)", id="search")
        yield self._search
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
        self.panes = [LocationPane(court) for court in self.courts]
        await container.mount_all(self.panes)
        self.size_panes()
        self.panes[0].focus()
        # In a worker so keys work while menus load; a date change cancels it.
        self.run_worker(self.initial_load(), exclusive=True)

    async def initial_load(self):
        await self.load_menus()
        if self.auto_meal:
            self.select_current_meal()

    def select_current_meal(self):
        """Filter to the meal being served now (or next) today."""
        if self._date != date.today():
            return
        entries = [p.entry for p in self.panes if p.entry is not None]
        meal = current_meal(entries, datetime.now().astimezone())
        if meal:
            self.set_meal_filter(meal)

    async def load_menus(self) -> None:
        self._loaded = False
        date_str = self._date.isoformat()
        self.update_sub_title()
        panes = list(self.panes)
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

    def format_title(self, title, sub_title):
        """Like the default (dim subtitle), but the meal stands out in the
        footer's key color."""
        meal = self.meal_filter or "all meals"
        if not sub_title.endswith(meal):
            return super().format_title(title, sub_title)
        prefix = sub_title[: -len(meal)]
        return Content.assemble(
            Content(title),
            (" \N{EM DASH} ", "dim"),
            Content(prefix).stylize("dim"),
            (meal, "$footer-key-foreground"),
        )

    def set_meal_filter(self, meal):
        if not self.courts or meal == self.meal_filter:
            return
        self.meal_filter = meal
        self.update_sub_title()
        self.refresh_panes()

    def refresh_panes(self):
        for pane in self.panes:
            if pane.entry is not None:
                pane.call_after_refresh(pane.refresh_content)

    def action_search(self):
        if not self.courts:
            return
        search = self._search
        if isinstance(self.focused, LocationPane):
            self._search_return = self.focused
        search.add_class("visible")
        search.focus()

    def check_action(self, action, parameters):
        # Main-view keys do nothing while a modal (the court picker) is open.
        if isinstance(self.screen, ModalScreen):
            return action in ("quit", "command_palette")
        # Only claim escape while the search bar is open.
        if action == "clear_search":
            return self._search is not None and self._search.has_class("visible")
        return True

    def action_clear_search(self):
        search = self._search
        search.value = ""
        search.remove_class("visible")
        self.return_from_search()

    def return_from_search(self):
        pane = self._search_return
        if pane is None or not pane.display:
            panes = self.visible_panes()
            pane = panes[0] if panes else None
        if pane is not None:
            pane.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search" or event.value == self.search_query:
            return
        self.search_query = event.value
        self.refresh_panes()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search":
            return
        if not event.value.strip():
            event.input.remove_class("visible")
        self.return_from_search()

    def change_date(self, new_date):
        if not self.courts:
            return
        if new_date == self._date and self._loaded:
            return
        self._date = new_date
        self.run_worker(self.load_menus(), exclusive=True)

    def size_panes(self):
        """Collapsed panes get a fixed strip; the others share the rest of the
        width, but never shrink below PANE_MIN_WIDTH (the row scrolls instead).
        Done by hand because `1fr` inside a HorizontalScroll resolves against
        the whole viewport."""
        panes = self.visible_panes()
        if not panes:
            return
        container = self.query_one("#panes", HorizontalScroll)
        expanded = [p for p in panes if not p.has_class("collapsed")]
        room = container.size.width - COLLAPSED_WIDTH * (len(panes) - len(expanded))
        if expanded:
            share, extra = divmod(max(room, 0), len(expanded))
        for pane in panes:
            if pane.has_class("collapsed"):
                width = COLLAPSED_WIDTH
            else:
                width = max(PANE_MIN_WIDTH, share + (1 if extra > 0 else 0))
                extra -= 1
            pane.styles.width = width

    def on_resize(self, event) -> None:
        self.call_after_refresh(self.size_panes)

    def visible_panes(self):
        return [p for p in self.panes if p.display]

    def set_hidden_courts(self, hidden):
        self.hidden_courts = set(hidden)
        for pane in self.panes:
            pane.display = pane.court_name not in self.hidden_courts
        self.size_panes()

    def action_pick_courts(self):
        if not self.courts:
            return
        self.push_screen(CourtPicker(self.courts, self.hidden_courts), self.after_pick_courts)

    def after_pick_courts(self, _result=None):
        # The pane that had focus may have been hidden.
        focused = self.screen.focused
        if focused not in self.visible_panes():
            visible = self.visible_panes()
            if visible:
                visible[0].focus()

    def action_focus_pane(self, step):
        """Focus the visible pane `step` places from the focused one,
        stopping at either end. Focusing scrolls the pane into view."""
        panes = self.visible_panes()
        if not panes:
            return
        if self.focused not in panes:
            panes[0].focus()
            return
        index = panes.index(self.focused) + step
        panes[max(0, min(index, len(panes) - 1))].focus()

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
        for pane in self.panes:
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