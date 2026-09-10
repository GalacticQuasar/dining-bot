---
name: purdue-dining
description: Use when the user asks about Purdue dining menus, dining courts, what's for breakfast/lunch/dinner, food options, specific foods (e.g. chicken, pizza), dietary restrictions (vegan, vegetarian, gluten-free), allergens, or which dining court serves something. Triggers on Purdue dining, dining courts, campus food, Earhart, Ford, Hillenbrand, Wiley, Windsor, meal times, and food search queries.
compatibility: Requires Python 3.8+ and network access to api.hfs.purdue.edu. Uses uv (or system python3 with requests installed) to run the bundled script.
metadata:
  author: GalacticQuasar
  version: "1.1"
---

# Purdue Dining Courts

Answer dining questions by running the bundled CLI script. Do not call the API any other way.

## Available scripts

- **`scripts/menu.py`** — Queries the Purdue dining courts GraphQL API: lists locations, shows menus, searches menu items. Supports `--help` on every subcommand.

## CLI reference

Run with the skill directory as the working directory, or use absolute paths. All output goes to stdout; warnings go to stderr. Exit code is 0 even when nothing is found.

Preferred (self-contained, auto-installs `requests` via inline PEP 723 metadata):

```
uv run scripts/menu.py --help
```

Fallback (plain python3, requires `requests` in the environment):

```
python3 scripts/menu.py locations [--json]
python3 scripts/menu.py menu --court COURT [--date DATE] [--meal MEAL] [--json]
python3 scripts/menu.py search "TEXT" [--court COURT] [--date DATE] [--meal MEAL] [--json]
```

- `COURT`: a location name (e.g. `Ford`), `courts` (the 5 dining courts only), or `all` (every location, default for search).
- `DATE`: `today` (default), `tomorrow`, `yesterday`, a weekday (e.g. `friday` — next occurrence, including today), or `YYYY-MM-DD`.
- `MEAL`: case-insensitive name, e.g. `breakfast`, `lunch`, `dinner`. Courts also serve `Brunch` / `Late Lunch` on some days — if the user's meal matches nothing, stderr lists what was available; try a nearby meal or drop the flag.

## Known locations

Dining courts (use `courts` to query all 5 at once): `Earhart`, `Ford`, `Hillenbrand`, `Wiley`, `Windsor`.

Other locations (rarely relevant; included by `all`): `1bowl at Meredith Hall`, `Pete's Za at Tarkington Hall`, `Sushi Boss at South Hall`, plus `Earhart On-the-GO!`, `Ford On-the-GO!`, `Lawson On-the-GO!`, `Windsor On-the-GO!`.

If unsure a name is valid, run `python3 scripts/menu.py locations` first.

## Answering questions

**"What are some chicken options for dinner today?"** — food-type questions. Search across all locations, then pick appealing options (vary by court/station, note standouts):

```
python3 scripts/menu.py search "chicken" --court all --date today --meal dinner
```

**"What's for dinner at Ford?" / "Ford menu"** — show the menu for a specific court:

```
python3 scripts/menu.py menu --court Ford --date today --meal dinner
```

**"Where can I get a vegan/gluten-free/vegetarian dinner?"** — dietary questions. Fetch JSON and filter on traits:

```
python3 scripts/menu.py menu --court courts --date today --meal dinner --json
```

Each menu item has a `traits` list. Common traits: `Vegan`, `Vegetarian`, `Gluten` (contains gluten — so "gluten-free" means items WITHOUT the `Gluten` trait), `Milk`, `Eggs`, `Peanuts`, `Tree Nuts`, `Soy`, `Wheat`, `Fish`, `Shellfish`, `Sesame`, `Coconut`. Note allergen traits mark what a food *contains*, not what it's free of. Filter in a small Python one-liner or read the readable output directly, whichever is easier.

**"When is X available this week?"** — loop over dates. E.g. `today`, `tomorrow`, then weekday names:

```
python3 scripts/menu.py search "pad thai" --court all --date monday
python3 scripts/menu.py search "pad thai" --court all --date tuesday
...
```

**"What's open right now?"** — meal `status` is shown in menu output (e.g. `OPEN`); meals not currently served show other statuses or are absent.

## Conventions

- When the user doesn't specify a date, use `today`; no meal, use their stated meal; no court, use `courts` (or `all` for food searches).
- If a court is closed or has no menu, the CLI prints a note on stderr — relay that naturally ("Windsor is closed today").
- Search is a case-insensitive substring match on item names — keep queries short (`"chicken"`, not `"spicy chicken sandwich"`). Try related terms (`"pizza"`, `"pasta"`, `"burger"`) if the first finds nothing.
- Prefer `search` when the user names a food, `menu` when they name a court.
- The date is resolved to an ISO string shown in the output header — if the user asked for "Friday", confirm the output date matches their intent.