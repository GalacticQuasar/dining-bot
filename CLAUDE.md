# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Python clients for Purdue's unofficial dining GraphQL API (`https://api.hfs.purdue.edu/menus/v3/GraphQL`), distributed mainly as an [Agent Skills](https://agentskills.io) skill (`purdue-dining`). There is no package, build step, linter config, or requirements file: every script is a single file carrying its dependencies in inline PEP 723 metadata (`# /// script`), so run them with `uv run`.

## Commands

```bash
# Skill CLI (agent-facing)
uv run .agents/skills/purdue-dining/scripts/menu.py --help
uv run .agents/skills/purdue-dining/scripts/menu.py menu --court Ford --date today --meal dinner
uv run .agents/skills/purdue-dining/scripts/menu.py search "chicken" --court courts --json

# TUI (Textual)
uv run tui.py

# TUI smoke test: headless, no pytest, one script (there are no other tests)
uv run test_tui.py
```

`test_tui.py` drives the app through Textual's `run_test` pilot against the **live API**. Some assertions depend on the real menu for the day the test runs (e.g. 6 panes, Earhart serving Lunch, 1bowl serving dinner but no breakfast). Before treating a failure as a regression, check whether it comes from that day's data, or from a slow API response (the 30s load wait can time out). Prefer assertions that read the day's `pane.entry` over hardcoded item names: the search test picks a word from Earhart's menu that way, and the diet filter test checks rendered items against their traits.

The test runs the app twice. The first run uses `DiningApp(auto_meal=False)` because its checks assume the all-meals view. The second runs at 80 columns with the default app, to check horizontal scrolling and the automatic meal choice. It also reads TUI internals: `app._loaded`, `app._loaded_date`, `app._date`, `app._menus` (to wait for the next-day prefetch), `app.courts`, `app.meal_filter`, `app.diet_filter`, `app.search_query`, `app.hidden_courts`, `app.palette`, `app.screen` (expected to be a `CourtPicker` while it's open), the `#legend` widget, `pane.entry`, `pane.display`, `pane.markup` (the markup string behind the pane's content), the pane's `collapsed` class, and `tui.ITEM_PREFIX`, `tui.meals_served`, `tui.is_vegan`/`is_vegetarian`. It also checks that each `LocationPane` holds a single `Static`. Keep those working, or update the test along with them.

## Architecture

Three separate clients call the same API. Each one carries its own copy of the `getStartLocations` and `getLocationMenu` GraphQL queries, and nothing is shared between them:

- **`.agents/skills/purdue-dining/scripts/menu.py`**: the non-interactive CLI the skill runs (sync `requests`, courts fetched one after another). It has to stay self-contained because users install the skill folder by itself (`npx skills add`, or by copying the directory), so it must not import anything from the rest of the repo. Its output contract, which `SKILL.md` documents for agents: results go to stdout, `note:` warnings go to stderr (with `--json` they go in the output's `warnings` list instead, for both `menu` and `search`), and the exit code is 0 even when nothing matched. Only request failures and bad arguments exit 1.
- **`tui.py`**: the Textual app (async `httpx`, all location menus fetched in parallel with `asyncio.gather`). Locations come from the API: every court in the `"Dining Courts"` category, plus the first location whose name contains "1bowl", pinned last. More detail below.
- **`script.py`**: the original interactive prompt-driven CLI, kept as a legacy tool.

### TUI internals

- **View state.** `DiningApp` holds `_date`, `meal_filter`, `diet_filter` (`None`, `"vegetarian"` or `"vegan"`), `show_traits`, `search_query` and `hidden_courts`. Every fetch runs in an exclusive worker, the first load (`initial_load`) included, so keys work while menus load and a date change cancels a fetch still in flight. Don't await `load_menus` from `on_mount`. The meal and diet filters, trait toggle and search only re-render each pane's cached `entry`. `LocationPane.refresh_content` updates its existing `Static` in place. Don't switch it back to remove-and-remount: search re-renders on every keystroke, and overlapping remounts can leave a pane with two `Static`s.
- **Rendering.** `menu_markup` returns `(markup, empty)`. The pane keeps the string as `pane.markup`, and `markup_renderable` turns it into a Rich `Group`: runs of lines starting with `ITEM_PREFIX` become a two-column grid (hanging indent for wrapped names), and a line starting with `RULE_MARK` becomes a `Rule`. Colors come from `app.palette`, built from the theme's hex colors by `theme_palette` and rebuilt when the theme changes. `old-gold` is registered and set as the default theme; like the court selection, a theme change lasts only for the session. A 30s interval re-renders panes without resetting scroll, to keep "closes in 40m" current. Meal hours are shown in the API's time zone, not the machine's.
- **Pane sizing.** A pane with `empty` markup gets the `collapsed` class and becomes a `COLLAPSED_WIDTH` strip titled with the short court name. `size_panes` sets every visible pane's width by hand (the others share the rest, never below `PANE_MIN_WIDTH`), because `1fr` inside a `HorizontalScroll` resolves against the whole viewport. It runs whenever `PaneRow` (the `#panes` container) is resized, when a pane collapses or expands, and when courts are hidden or shown. Collapsed panes are still focusable and still reached by `←`/`→`.
- **Cache and prefetch.** `_menus` maps `(date, court)` to `(monotonic time, entry)` for `MENU_CACHE_SECONDS`. `load_menus` shows cached panes at once and fetches only the rest; errors aren't cached. After each load, a worker in the `"prefetch"` group fetches the next day. `change_date` clears `_loaded` itself before starting the worker.
- **Pane list.** Use `app.panes`, the list built at mount, and never `app.query(LocationPane)`. While a modal screen is open, `App.query()` searches the modal instead of the main view, so a query from a running worker would find no panes.
- **Court picker.** `c` opens `CourtPicker`, a `ModalScreen` with a `SelectionList`. It hides panes with `display = False` and still fetches every location, so showing one again is instant. It always keeps at least one court visible. The selection lasts only until the app quits: the user does not want it saved to disk or anywhere else, so don't add persistence.
- **Meals and footer.** `m`/`M` cycle through `None` plus `meals_served(...)` for the shown date (serving order per `MEAL_ORDER`, meals closed everywhere left out). The footer shows only the everyday keys: `b`/`l`/`d`/`a`, `p`, `M` and the arrows are `show=False` and listed in the help panel that `?` toggles.
- **Keys and modals.** `check_action` disables every main-view action except `quit` and `command_palette` while a modal is open. Escape is a priority app binding (`clear_search`) so the search bar can claim it. `check_action` turns it off while the bar is hidden, so Esc still reaches the picker and the screen.
- **Navigation and search.** `LocationPane` binds `←`/`→` to `app.focus_pane`, replacing `VerticalScroll`'s horizontal scroll keys. Navigation skips hidden panes. `/` shows the `#search` `Input` (kept as `app._search`), which matches item names only and ignores case.
- **Meal on startup.** Once today's menus load, `current_meal()` sets `meal_filter` to the meal being served now, or the next one to start, using each meal's `startTime`/`endTime`. It leaves the filter alone after the last meal ends. This happens only at startup, and not at all if the date changes before the first load finishes.
- **Header.** `format_title` is overridden so the meal name (and the diet filter, when set) in the subtitle use `$footer-key-foreground`, the same color as the footer keys.

`menu.py` and `tui.py` flatten API responses into the same shape, `{court, formal_name, meals: [{name, status, items: [{station, item, traits}]}]}`. The TUI also queries `startTime`/`endTime` and adds `start`/`end` to each meal. These are timezone-aware `datetime`s, or `None` when a meal has no hours (closed meals). A change to how the API is queried or flattened usually has to be made in more than one file.

## Skill layout

- `.claude/skills` is a symlink to `../.agents/skills`, so Claude Code can find the skill. Edit the files under `.agents/skills/` and never replace the symlink.
- `SKILL.md` has frontmatter (`name`, `description` with the trigger keywords, `metadata.version`) and documents the CLI flags. If you change `menu.py`'s interface, update `SKILL.md` and the README's CLI section to match.
- Domain detail that is easy to get wrong: allergen traits mark what an item *contains*. `Gluten` means the item contains gluten, so "gluten-free" means the item has no `Gluten` trait. `--court courts` covers the 5 dining courts and `--court all` covers every location. A weekday passed to `--date` resolves to its next occurrence, counting today.
