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
import math
import re
import time
from datetime import date, datetime, timedelta

import httpx
from rich.console import Group
from rich.markup import escape
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalScroll, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Footer, Header, Input, LoadingIndicator, SelectionList, Static

# Loaded menus are reused for this long before being fetched again.
MENU_CACHE_SECONDS = 30 * 60
# Purdue's black and gold; the default theme (ctrl+p switches for the session).
OLD_GOLD = Theme(
    name="old-gold",
    primary="#CFB991",
    secondary="#8E6F3E",
    accent="#DAAA00",
    warning="#DDB945",
    error="#E06C5A",
    success="#8FBF6A",
    foreground="#ECE8E1",
    background="#0E0E0E",
    surface="#161616",
    panel="#24221E",
    dark=True,
)

# Rich styles for menu markup. The app swaps in its theme's colors; these
# are the fallbacks.
DEFAULT_PALETTE = {
    "meal": "bold",
    "station": "bold cyan",
    "rule": "dim",
    "open": "green",
    "soon": "yellow",
    "vegan": "bold green",
    "vegetarian": "bold yellow",
}

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


def clock(moment):
    """11:00a / 2:30p, in the time zone the API gave (Purdue's)."""
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d}{'a' if moment.hour < 12 else 'p'}"


def duration(delta):
    minutes = max(1, math.ceil(delta.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def meal_status_markup(meal, now=None, palette=DEFAULT_PALETTE):
    """The line under a meal's name: its hours, plus where `now` falls in them
    when the meal is today. Meals without hours fall back to the API status."""
    start, end = meal.get("start"), meal.get("end")
    if not (start and end):
        status = meal["status"].strip()
        return f"[dim]{escape(status.capitalize())}[/dim]" if status else ""
    hours = f"{clock(start)}\N{EN DASH}{clock(end)}"
    if now is None or start.date() != now.astimezone(start.tzinfo).date():
        return f"[dim]{hours}[/dim]"
    if now < start:
        return f"[dim]{hours} \N{MIDDLE DOT}[/dim] [{palette['soon']}]opens in {duration(start - now)}[/]"
    if now < end:
        return (
            f"[{palette['open']}]\N{BLACK CIRCLE} {hours}[/] [dim]\N{MIDDLE DOT}[/dim] "
            f"[{palette['open']}]closes in {duration(end - now)}[/]"
        )
    return f"[dim]ended {clock(end)}[/dim]"


# Allergen traits say what an item *contains*. Two letters each keeps a
# fully labelled item on one or two lines; the legend spells them out.
ALLERGENS = {
    "Gluten": "Gl",
    "Wheat": "Wh",
    "Milk": "Mi",
    "Eggs": "Eg",
    "Soy": "So",
    "Sesame": "Se",
    "Peanuts": "Pn",
    "Tree Nuts": "TN",
    "Fish": "Fi",
    "Shellfish": "Sh",
    "Coconut": "Co",
}
DIET_FILTERS = (None, "vegetarian", "vegan")


def is_vegan(traits):
    return any(t.lower() == "vegan" for t in traits)


def is_vegetarian(traits):
    return any(t.lower() in ("vegan", "vegetarian") for t in traits)


def traits_markup(traits, palette=DEFAULT_PALETTE):
    """Compact labels: a colored VG/V mark, then dim allergen codes."""
    tags = []
    if is_vegan(traits):
        tags.append(f"[{palette['vegan']}]VG[/]")
    elif is_vegetarian(traits):
        tags.append(f"[{palette['vegetarian']}]V[/]")
    codes = [
        ALLERGENS.get(t, escape(t))
        for t in traits
        if t.lower() not in ("vegan", "vegetarian")
    ]
    if codes:
        tags.append(f"[dim]{' '.join(codes)}[/dim]")
    return " ".join(tags)


def legend_markup(palette=DEFAULT_PALETTE):
    codes = "  ".join(f"{code} [dim]{name.lower()}[/dim]" for name, code in ALLERGENS.items())
    return (
        f"[{palette['vegan']}]VG[/] [dim]vegan[/dim]  "
        f"[{palette['vegetarian']}]V[/] [dim]vegetarian[/dim]  "
        f"[dim]\N{BOX DRAWINGS LIGHT VERTICAL} contains:[/dim] {codes}"
    )


def filter_diet(meals, diet):
    """Keep only vegan (or vegetarian, which includes vegan) items."""
    if not diet:
        return meals
    keep = is_vegan if diet == "vegan" else is_vegetarian
    meals = [{**m, "items": [it for it in m["items"] if keep(it["traits"])]} for m in meals]
    return [m for m in meals if m["items"]]


# Serving order for the meal cycle; unknown names go after, by start time.
MEAL_ORDER = ("Breakfast", "Brunch", "Lunch", "Late Lunch", "Dinner")


def meals_served(entries):
    """Names of the meals with items or hours at any location, in serving
    order. Meals that are closed everywhere are left out."""
    earliest = {}
    for entry in entries:
        for meal in entry["meals"]:
            if not (meal["items"] or meal["start"]):
                continue
            start = meal["start"].timestamp() if meal["start"] else math.inf
            earliest[meal["name"]] = min(start, earliest.get(meal["name"], math.inf))

    def key(name):
        rank = MEAL_ORDER.index(name) if name in MEAL_ORDER else len(MEAL_ORDER)
        return (rank, earliest[name], name)

    return sorted(earliest, key=key)


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
# A markup line starting with this is a horizontal rule; the rest is its style.
RULE_MARK = "\x1e"


def markup_renderable(markup):
    """Turn menu markup into a Rich renderable. Runs of item lines go into a
    two-column grid, so a long name wraps under itself, not under the bullet."""
    parts = []
    grid = None
    for line in markup.split("\n"):
        if not line.startswith(ITEM_PREFIX):
            grid = None
            if line.startswith(RULE_MARK):
                parts.append(Rule(style=line[len(RULE_MARK):]))
            else:
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


def menu_markup(
    entry, show_traits=False, meal_filter=None, query="", now=None, diet=None,
    palette=DEFAULT_PALETTE,
):
    """Markup for one location's menu, plus whether it has no items to show
    (closed, meal not served, or nothing matches), so the pane can collapse."""
    all_meals = entry["meals"]
    if not all_meals:
        return notice("Closed or no menu for this date."), True
    meals = filter_meals(all_meals, meal_filter)
    if not meals:
        return notice(f"(no {escape(meal_filter)} served here)"), True
    if not any(meal["items"] for meal in meals):
        if meal_filter:
            return notice(f"({escape(meal_filter)} closed)"), True
        return notice("(closed all day)"), True
    meals = filter_diet(meals, diet)
    if not meals:
        return notice(f"(nothing {diet} here)"), True
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
    parts = []
    for meal in meals:
        parts.append(f"[{palette['meal']}]{escape(meal['name'])}[/]")
        status = meal_status_markup(meal, now, palette)
        if status:
            parts.append(status)
        parts.append(RULE_MARK + palette["rule"])
        by_station = {}
        for item in meal["items"]:
            by_station.setdefault(item["station"], []).append(item)
        for station, items in by_station.items():
            parts.append(f"[{palette['station']}]{escape(station)}[/]")
            for item in items:
                line = f"{ITEM_PREFIX}{highlight(item['item'], query)}"
                if show_traits and item["traits"]:
                    line = f"{line}  {traits_markup(item['traits'], palette)}"
                parts.append(line)
            parts.append("")
        parts.append("")
    return "\n".join(parts).rstrip(), False


class LocationPane(VerticalScroll):
    """One location's menu, independently scrollable."""

    # Override VerticalScroll's horizontal scroll keys: left/right move
    # between panes instead.
    BINDINGS = [
        Binding(
            "left", "app.focus_pane(-1)", "Prev court", key_display="\N{LEFTWARDS ARROW}", show=False
        ),
        Binding(
            "right", "app.focus_pane(1)", "Next court", key_display="\N{RIGHTWARDS ARROW}", show=False
        ),
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

    async def refresh_content(self, reset_scroll=True):
        if self.entry is None:
            return
        self.markup, empty = menu_markup(
            self.entry,
            self.app.show_traits,
            self.app.meal_filter,
            self.app.search_query,
            now=datetime.now().astimezone(),
            diet=self.app.diet_filter,
            palette=self.app.palette,
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
        if reset_scroll:
            self.scroll_to(y=0, animate=False)


class PaneRow(HorizontalScroll):
    """The row of panes. Re-sizes them whenever its own width changes (window
    resize, help panel opening), not just when the app is resized."""

    def on_resize(self, event) -> None:
        self.call_after_refresh(self.app.size_panes)


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
        border: tall $primary 35%;
        border-title-color: $text-muted;
        padding: 0 1;
        background: $surface;
    }
    LocationPane:focus {
        border: tall $accent;
        border-title-color: $accent;
        border-title-style: bold;
    }
    LocationPane.collapsed {
        color: $text-muted;
        border: tall $primary 15%;
    }
    LocationPane.collapsed:focus {
        border: tall $accent;
    }
    #search {
        display: none;
    }
    #search.visible {
        display: block;
    }
    #legend {
        display: none;
        height: auto;
        padding: 0 1;
        background: $panel;
    }
    #legend.visible {
        display: block;
    }
    """

    # The footer shows the everyday keys; the rest are listed under `?`.
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "today", "Today"),
        ("n", "next_day", "Next day"),
        Binding("p", "previous_day", "Prev day", show=False),
        Binding("m", "cycle_meal(1)", "Meal", tooltip="Next meal served that day, then all"),
        Binding("M", "cycle_meal(-1)", "Prev meal", show=False),
        Binding("b", "filter_breakfast", "Breakfast", show=False),
        Binding("l", "filter_lunch", "Lunch", show=False),
        Binding("d", "filter_dinner", "Dinner", show=False),
        Binding("a", "filter_all", "All meals", show=False),
        Binding("v", "toggle_traits", "Labels", tooltip="Diet and allergen labels"),
        Binding("f", "cycle_diet", "Veg", tooltip="Vegetarian only, vegan only, off"),
        Binding("c", "pick_courts", "Courts", tooltip="Choose which locations to show"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("question_mark", "toggle_help", "Keys", key_display="?"),
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
        # (date, court) -> (time.monotonic() when fetched, entry)
        self._menus = {}
        self.show_traits = False
        self.diet_filter = None
        self.meal_filter = None
        self.search_query = ""
        self._search_return = None
        self._search = None
        self._legend = None
        self.register_theme(OLD_GOLD)
        self.theme = OLD_GOLD.name
        self.palette = self.theme_palette()
        self.courts = []
        # Kept as a list rather than queried: while a modal is open,
        # App.query() searches the modal instead of the main screen.
        self.panes = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield PaneRow(id="panes")
        self._search = Input(placeholder="Search items (Enter to keep, Esc to clear)", id="search")
        yield self._search
        self._legend = Static(legend_markup(self.palette), id="legend")
        yield self._legend
        yield Footer(compact=True)

    def theme_palette(self):
        """DEFAULT_PALETTE with the current theme's colors, where it gives
        plain hex values (Rich can't read Textual's 'auto 60%' and the like)."""
        variables = self.get_css_variables()

        def color(name, fallback):
            value = variables.get(name, "")
            return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback

        return {
            "meal": f"bold {color('foreground', 'default')}",
            "station": f"bold {color('primary', 'cyan')}",
            "rule": f"{color('primary', 'default')} dim",
            "open": color("success", "green"),
            "soon": color("warning", "yellow"),
            "vegan": f"bold {color('success', 'green')}",
            "vegetarian": f"bold {color('warning', 'yellow')}",
        }

    def on_theme_change(self, _theme) -> None:
        self.palette = self.theme_palette()
        self._legend.update(legend_markup(self.palette))
        self.refresh_panes(reset_scroll=False)

    async def on_mount(self) -> None:
        self.theme_changed_signal.subscribe(self, self.on_theme_change)
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
        # Keep "closes in 40m" current.
        self.set_interval(30, self.tick_clock)
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

    def cached_menu(self, date_str, court):
        hit = self._menus.get((date_str, court))
        if hit and time.monotonic() - hit[0] < MENU_CACHE_SECONDS:
            return hit[1]
        return None

    async def fetch_menus(self, date_str, courts):
        """{court: entry or exception} for `courts`, caching what loads."""
        async with httpx.AsyncClient(timeout=15) as client:
            results = await asyncio.gather(
                *(fetch_menu(client, court, date_str) for court in courts),
                return_exceptions=True,
            )
        for court, result in zip(courts, results):
            if not isinstance(result, BaseException):
                self._menus[(date_str, court)] = (time.monotonic(), result)
        return dict(zip(courts, results))

    async def load_menus(self) -> None:
        self._loaded = False
        date_str = self._date.isoformat()
        self.update_sub_title()
        panes = list(self.panes)
        # Days already seen (or prefetched) show at once; only the rest load.
        missing = []
        for pane in panes:
            entry = self.cached_menu(date_str, pane.court_name)
            if entry is not None:
                await pane.show_menu(entry)
            else:
                missing.append(pane)
                await pane.show_loading()
        if missing:
            results = await self.fetch_menus(date_str, [p.court_name for p in missing])
            for pane in missing:
                result = results[pane.court_name]
                if isinstance(result, BaseException):
                    await pane.show_error(result)
                else:
                    await pane.show_menu(result)
        self._loaded = True
        self._loaded_date = date_str
        # Most date changes are "next day", so have it ready.
        self.run_worker(
            self.prefetch(self._date + timedelta(days=1)), group="prefetch", exclusive=True
        )

    async def prefetch(self, day):
        date_str = day.isoformat()
        courts = [c for c in self.courts if self.cached_menu(date_str, c) is None]
        if courts:
            await self.fetch_menus(date_str, courts)

    def update_sub_title(self):
        date_str = self._date.isoformat()
        weekday = self._date.strftime("%A")
        meal = self.meal_filter or "all meals"
        diet = f" \N{MIDDLE DOT} {self.diet_filter} only" if self.diet_filter else ""
        self.sub_title = f"{date_str} ({weekday}) \N{RIGHTWARDS DOUBLE ARROW} {meal}{diet}"

    def format_title(self, title, sub_title):
        """Like the default (dim subtitle), but the meal and diet filter stand
        out in the footer's key color."""
        meal = self.meal_filter or "all meals"
        marker = f"\N{RIGHTWARDS DOUBLE ARROW} {meal}"
        if marker not in sub_title:
            return super().format_title(title, sub_title)
        prefix, _, rest = sub_title.partition(marker)
        parts = [
            Content(title),
            (" \N{EM DASH} ", "dim"),
            Content(prefix + "\N{RIGHTWARDS DOUBLE ARROW} ").stylize("dim"),
            (meal, "$footer-key-foreground"),
        ]
        if self.diet_filter:
            parts += [(" \N{MIDDLE DOT} ", "dim"), (f"{self.diet_filter} only", "$footer-key-foreground")]
        return Content.assemble(*parts)

    def set_meal_filter(self, meal):
        if not self.courts or meal == self.meal_filter:
            return
        self.meal_filter = meal
        self.update_sub_title()
        self.refresh_panes()

    def tick_clock(self):
        for pane in self.panes:
            if pane.entry is not None:
                pane.call_after_refresh(pane.refresh_content, False)

    def refresh_panes(self, reset_scroll=True):
        for pane in self.panes:
            if pane.entry is not None:
                pane.call_after_refresh(pane.refresh_content, reset_scroll)

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
        # Cleared here, not just in the worker, so nothing sees the old day as loaded.
        self._loaded = False
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
        self._legend.set_class(self.show_traits, "visible")
        for pane in self.panes:
            if pane.entry is not None:
                await pane.refresh_content()

    def action_cycle_diet(self):
        """No filter -> vegetarian -> vegan -> no filter."""
        if not self.courts:
            return
        index = DIET_FILTERS.index(self.diet_filter)
        self.diet_filter = DIET_FILTERS[(index + 1) % len(DIET_FILTERS)]
        self.update_sub_title()
        self.refresh_panes()

    def action_cycle_meal(self, step):
        """Step through all meals plus each meal served on the shown date."""
        entries = [p.entry for p in self.panes if p.entry is not None]
        options = [None, *meals_served(entries)]
        index = options.index(self.meal_filter) if self.meal_filter in options else 0
        self.set_meal_filter(options[(index + step) % len(options)])

    def action_toggle_help(self):
        if self.screen.query("HelpPanel"):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

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