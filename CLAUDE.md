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

`test_tui.py` drives the app through Textual's `run_test` pilot against the **live API**. Some assertions depend on the real menu for the day the test runs (e.g. 6 panes, Earhart serving Lunch, 1bowl serving dinner but no breakfast). Before treating a failure as a regression, check whether it comes from that day's data, or from a slow API response (the 30s load wait can time out). Prefer assertions that read the day's `pane.entry` over hardcoded item names: the search test picks a word from Earhart's menu that way.

The test runs the app twice. The first run uses `DiningApp(auto_meal=False)` because its checks assume the all-meals view. The second runs at 80 columns with the default app, to check horizontal scrolling and the automatic meal choice. It also reads TUI internals: `app._loaded`, `app._loaded_date`, `app._date`, `app.courts`, `app.meal_filter`, `app.search_query`, `app.hidden_courts`, `app.screen` (expected to be a `CourtPicker` while it's open), `pane.entry`, `pane.display`, and `pane.children[0].content`, which assumes each `LocationPane` holds a single `Static`. Keep those working, or update the test along with them.

## Architecture

Three separate clients call the same API. Each one carries its own copy of the `getStartLocations` and `getLocationMenu` GraphQL queries, and nothing is shared between them:

- **`.agents/skills/purdue-dining/scripts/menu.py`**: the non-interactive CLI the skill runs (sync `requests`, courts fetched one after another). It has to stay self-contained because users install the skill folder by itself (`npx skills add`, or by copying the directory), so it must not import anything from the rest of the repo. Its output contract, which `SKILL.md` documents for agents: results go to stdout, `note:` warnings go to stderr, and the exit code is 0 even when nothing matched. Only request failures and bad arguments exit 1.
- **`tui.py`**: the Textual app (async `httpx`, all location menus fetched in parallel with `asyncio.gather`). Locations come from the API: every court in the `"Dining Courts"` category, plus the first location whose name contains "1bowl", pinned last. More detail below.

### TUI internals

- **View state.** `DiningApp` holds `_date`, `meal_filter`, `show_traits`, `search_query` and `hidden_courts`. Every fetch runs in an exclusive worker, the first load (`initial_load`) included, so keys work while menus load and a date change cancels a fetch still in flight. Don't await `load_menus` from `on_mount`. The meal filter, trait toggle and search only re-render each pane's cached `entry`. `LocationPane.refresh_content` updates its existing `Static` in place. Don't switch it back to remove-and-remount: search re-renders on every keystroke, and overlapping remounts can leave a pane with two `Static`s.
- **Pane list.** Use `app.panes`, the list built at mount, and never `app.query(LocationPane)`. While a modal screen is open, `App.query()` searches the modal instead of the main view, so a query from a running worker would find no panes.
- **Court picker.** `c` opens `CourtPicker`, a `ModalScreen` with a `SelectionList`. It hides panes with `display = False` and still fetches every location, so showing one again is instant. It always keeps at least one court visible. The selection lasts only until the app quits: the user does not want it saved to disk or anywhere else, so don't add persistence.
- **Keys and modals.** `check_action` disables every main-view action except `quit` and `command_palette` while a modal is open. Escape is a priority app binding (`clear_search`) so the search bar can claim it. `check_action` turns it off while the bar is hidden, so Esc still reaches the picker and the screen.
- **Navigation and search.** `LocationPane` binds `←`/`→` to `app.focus_pane`, replacing `VerticalScroll`'s horizontal scroll keys. Navigation skips hidden panes. `/` shows the `#search` `Input` (kept as `app._search`), which matches item names only and ignores case.
- **Meal on startup.** Once today's menus load, `current_meal()` sets `meal_filter` to the meal being served now, or the next one to start, using each meal's `startTime`/`endTime`. It leaves the filter alone after the last meal ends. This happens only at startup, and not at all if the date changes before the first load finishes.
- **Header.** `format_title` is overridden so the meal name in the subtitle uses `$footer-key-foreground`, the same color as the footer keys.
- **`script.py`**: the original interactive prompt-driven CLI, kept as a legacy tool.

`menu.py` and `tui.py` flatten API responses into the same shape, `{court, formal_name, meals: [{name, status, items: [{station, item, traits}]}]}`. The TUI also queries `startTime`/`endTime` and adds `start`/`end` to each meal. These are timezone-aware `datetime`s, or `None` when a meal has no hours (closed meals). A change to how the API is queried or flattened usually has to be made in more than one file.

## Skill layout

- `.claude/skills` is a symlink to `../.agents/skills`, so Claude Code can find the skill. Edit the files under `.agents/skills/` and never replace the symlink.
- `SKILL.md` has frontmatter (`name`, `description` with the trigger keywords, `metadata.version`) and documents the CLI flags. If you change `menu.py`'s interface, update `SKILL.md` and the README's CLI section to match.
- Domain detail that is easy to get wrong: allergen traits mark what an item *contains*. `Gluten` means the item contains gluten, so "gluten-free" means the item has no `Gluten` trait. `--court courts` covers the 5 dining courts and `--court all` covers every location. A weekday passed to `--date` resolves to its next occurrence, counting today.
