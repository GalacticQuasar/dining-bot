#!/usr/bin/env python3
"""Non-interactive CLI for the Purdue dining courts API. Designed for agent use.

Examples:
    python3 menu.py locations
    python3 menu.py menu --court Ford --date today
    python3 menu.py menu --court all --date tomorrow --meal dinner
    python3 menu.py search "chicken" --meal dinner
    python3 menu.py menu --court all --date friday --json
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta

import requests

DINING_API_URL = "https://api.hfs.purdue.edu/menus/v3/GraphQL"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def graphql(operation_name, query, variables):
    payload = {"operationName": operation_name, "query": query, "variables": variables}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(DINING_API_URL, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        print(f"error: API request failed: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        body = response.json()
    except ValueError:
        detail = response.text[:200] if response.text else response.reason
        print(
            f"error: API returned HTTP {response.status_code} with no JSON body: {detail}",
            file=sys.stderr,
        )
        sys.exit(1)
    if response.status_code >= 400 and "data" not in body:
        messages = "; ".join(e.get("message", "?") for e in body.get("errors", []))
        print(
            f"error: API returned HTTP {response.status_code}: {messages or body}",
            file=sys.stderr,
        )
        sys.exit(1)
    return body


def get_locations():
    query = """
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
    data = graphql("getStartLocations", query, {})
    return data.get("data", {}).get("diningCourtCategories", [])


def get_menu(court_name, date_str):
    query = """
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
    return graphql("getLocationMenu", query, {"name": court_name, "date": date_str})


def resolve_date(date_arg):
    """Resolve a date argument: today, tomorrow, yesterday, a weekday name,
    or an explicit YYYY-MM-DD string. Weekdays resolve to the next occurrence,
    including today."""
    arg = date_arg.strip().lower()
    today = date.today()
    if arg == "today":
        return today
    if arg == "tomorrow":
        return today + timedelta(days=1)
    if arg == "yesterday":
        return today - timedelta(days=1)
    if arg in WEEKDAYS:
        target_index = WEEKDAYS.index(arg)
        offset = (target_index - today.weekday()) % 7
        return today + timedelta(days=offset)
    try:
        parsed = datetime.strptime(date_arg.strip(), "%Y-%m-%d").date()
    except ValueError:
        print(
            f"error: invalid date {date_arg!r}. Use today, tomorrow, yesterday, "
            "a weekday name (e.g. friday), or YYYY-MM-DD.",
            file=sys.stderr,
        )
        sys.exit(1)
    return parsed


def flatten_menu(court_name, data):
    """Flatten a menu response into a list of meal dicts with items.
    Returns (formal_name, meals) where each meal has name, status, and a
    flat list of {station, item, traits}."""
    court = (data.get("data") or {}).get("diningCourtByName")
    if not court:
        return None, []
    formal_name = court.get("formalName", court_name)
    daily_menu = court.get("dailyMenu")
    if not daily_menu:
        return formal_name, []
    meals = []
    for meal in daily_menu.get("meals") or []:
        flat_items = []
        for station in meal.get("stations") or []:
            for entry in station.get("items") or []:
                item = entry.get("item")
                if not item:
                    continue
                traits = [t["name"] for t in (item.get("traits") or []) if t.get("name")]
                flat_items.append(
                    {"station": station["name"], "item": item["name"], "traits": traits}
                )
        meals.append({"name": meal["name"], "status": meal["status"], "items": flat_items})
    return formal_name, meals


def fetch_menus(courts, date_str):
    """Fetch and flatten menus for one or more courts.
    Returns a list of {court, formal_name, meals} plus warnings."""
    results = []
    warnings = []
    for court in courts:
        data = get_menu(court, date_str)
        if (data.get("errors") or []) and not (data.get("data") or {}).get(
            "diningCourtByName"
        ):
            messages = "; ".join(e.get("message", "?") for e in data["errors"])
            warnings.append(f"{court}: API error: {messages}")
            continue
        formal_name, meals = flatten_menu(court, data)
        if formal_name is None:
            warnings.append(f"{court}: unknown location")
            continue
        if not meals:
            warnings.append(f"{formal_name}: closed or no menu for {date_str}")
        results.append({"court": court, "formal_name": formal_name, "meals": meals})
    return results, warnings


def filter_meals(menus, meal_filter):
    """Keep only meals whose name matches the filter (case-insensitive).
    Warn if the filter matched nothing anywhere."""
    if not meal_filter:
        return menus, []
    target = meal_filter.strip().lower()
    filtered = []
    seen_meal_names = set()
    for entry in menus:
        for m in entry["meals"]:
            seen_meal_names.add(m["name"])
        entry["meals"] = [m for m in entry["meals"] if m["name"].strip().lower() == target]
        filtered.append(entry)
    warnings = []
    if not any(entry["meals"] for entry in filtered) and seen_meal_names:
        warnings.append(
            f"no meal named {meal_filter!r}; available meals were: "
            f"{', '.join(sorted(seen_meal_names))}"
        )
    return filtered, warnings


def search_items(menus, query_text):
    """Return matches for a case-insensitive substring search across all meals."""
    needle = query_text.strip().lower()
    matches = []
    for entry in menus:
        for meal in entry["meals"]:
            for it in meal["items"]:
                if needle in it["item"].lower():
                    matches.append(
                        {
                            "court": entry["formal_name"],
                            "meal": meal["name"],
                            "station": it["station"],
                            "item": it["item"],
                            "traits": it["traits"],
                        }
                    )
    return matches


def known_courts():
    """Return (dining_court_names, all_location_names) from the API."""
    categories = get_locations()
    dining = []
    all_names = []
    for cat in categories:
        for court in cat.get("diningCourts") or []:
            if court.get("name"):
                all_names.append(court["name"])
                if cat["name"] == "Dining Courts":
                    dining.append(court["name"])
    return dining, all_names


def resolve_courts(court_arg):
    """Resolve the --court argument to a list of court names.
    'all' means every location; 'courts' means the 5 dining courts."""
    if court_arg in ("all", "courts"):
        dining, all_names = known_courts()
        if court_arg == "all":
            return all_names
        return dining
    return [court_arg]


def print_locations(as_json):
    categories = get_locations()
    if as_json:
        print(json.dumps(categories, indent=2))
        return
    if not categories:
        print("No locations found.")
        return
    for cat in categories:
        print(cat["name"])
        for court in cat.get("diningCourts") or []:
            print(f"  {court['name']}  ({court.get('formalName', court['name'])})")


def print_menu(menus, date_str, as_json, warnings, meal_filter=None):
    if as_json:
        print(json.dumps({"date": date_str, "menus": menus, "warnings": warnings}, indent=2))
        return
    for warning in warnings:
        print(f"note: {warning}", file=sys.stderr)
    if not menus:
        print(f"No menus available for {date_str} (see notes on stderr).")
        return
    print(f"=== Menus for {date_str} ===")
    for entry in menus:
        print(f"\n--- {entry['formal_name']} ---")
        if not entry["meals"]:
            if meal_filter:
                print(f"  (no {meal_filter} served here)")
            else:
                print("  (closed or no menu)")
            continue
        for meal in entry["meals"]:
            print(f"\n[ {meal['name']} ] ({meal['status']})")
            by_station = {}
            for it in meal["items"]:
                by_station.setdefault(it["station"], []).append(it)
            for station, items in by_station.items():
                print(f"  {station}:")
                for it in items:
                    trait_str = f" ({', '.join(it['traits'])})" if it["traits"] else ""
                    print(f"    - {it['item']}{trait_str}")
    for warning in warnings:
        print(f"\nnote: {warning}", file=sys.stderr)


def print_search(matches, query_text, date_str, as_json):
    if as_json:
        print(
            json.dumps(
                {"date": date_str, "query": query_text, "matches": matches}, indent=2
            )
        )
        return
    print(f"=== Matches for {query_text!r} on {date_str} ===")
    if not matches:
        print("No matching items found.")
        return
    for match in matches:
        trait_str = f" ({', '.join(match['traits'])})" if match["traits"] else ""
        print(f"  {match['court']} [{match['meal']}] {match['station']}: {match['item']}{trait_str}")


def add_date_meal_args(parser):
    parser.add_argument(
        "--date",
        default="today",
        help="today (default), tomorrow, yesterday, a weekday (e.g. friday), or YYYY-MM-DD",
    )
    parser.add_argument("--meal", help="filter to one meal, e.g. breakfast, lunch, dinner")
    parser.add_argument("--json", action="store_true", help="output JSON instead of text")


def main():
    parser = argparse.ArgumentParser(
        description="Query Purdue dining court menus (non-interactive)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    locations_parser = subparsers.add_parser("locations", help="List all dining locations")
    locations_parser.add_argument("--json", action="store_true", help="output JSON instead of text")

    menu_parser = subparsers.add_parser("menu", help="Show a menu, grouped by meal and station")
    menu_parser.add_argument(
        "--court",
        required=True,
        help="court name (e.g. Ford), 'courts' for the 5 dining courts, or 'all' for every location",
    )
    add_date_meal_args(menu_parser)

    search_parser = subparsers.add_parser("search", help="Search menu items by substring")
    search_parser.add_argument("query", help="text to search for (case-insensitive substring)")
    search_parser.add_argument(
        "--court",
        default="all",
        help="court name, 'courts' for the 5 dining courts, or 'all' (default)",
    )
    add_date_meal_args(search_parser)

    args = parser.parse_args()

    if args.command == "locations":
        print_locations(args.json)
        return

    target_date = resolve_date(args.date)
    date_str = target_date.isoformat()
    courts = resolve_courts(args.court)

    menus, warnings = fetch_menus(courts, date_str)
    menus, meal_warnings = filter_meals(menus, getattr(args, "meal", None))
    warnings.extend(meal_warnings)

    if args.command == "menu":
        print_menu(menus, date_str, args.json, warnings, getattr(args, "meal", None))
    elif args.command == "search":
        matches = search_items(menus, args.query)
        print_search(matches, args.query, date_str, args.json)


if __name__ == "__main__":
    main()