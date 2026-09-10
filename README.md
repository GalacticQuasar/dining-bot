# Dining Bot

Purdue Dining Courts Bot — a CLI for Purdue's dining menus API plus an [Agent Skills](https://agentskills.io) skill that lets any AI agent answer dining questions.

[![skills.sh](https://skills.sh/b/GalacticQuasar/dining-bot)](https://skills.sh/GalacticQuasar/dining-bot)

## Install the agent skill

Works with any Agent Skills-compatible agent (opencode, Claude Code, VS Code/Copilot, Gemini CLI, Codex, Goose, ...):

```bash
npx skills add GalacticQuasar/dining-bot
```

The CLI prompts you for which agent and whether to install project-level or global (`-g`). Add `-s purdue-dining` to skip the skill picker.

Or install manually:

```bash
git clone https://github.com/GalacticQuasar/dining-bot ~/.agents/skills/purdue-dining
```

Note: cloning the full repo puts the skill folder one level deep. For a clean manual install, copy just the skill directory:

```bash
git clone https://github.com/GalacticQuasar/dining-bot /tmp/dining-bot \
  && mkdir -p ~/.agents/skills \
  && cp -r /tmp/dining-bot/.agents/skills/purdue-dining ~/.agents/skills/
```

Then just ask your agent things like:

- "What are some chicken options for dinner today?"
- "What's for lunch at Ford tomorrow?"
- "Where can I get a vegan dinner tonight?"
- "When is pad thai available this week?"

## The skill

Located at `.agents/skills/purdue-dining/` (the cross-client convention every spec-compliant agent discovers):

```
.agents/skills/purdue-dining/
├── SKILL.md          # When to activate + how to answer dining questions
└── scripts/
    └── menu.py       # Self-contained CLI (PEP 723; runs via uv with no install)
```

It queries [Purdue's dining API](https://api.hfs.purdue.edu/menus/v3/GraphQL) (unofficial) to list locations, show menus by court/date/meal, search items, and filter by dietary traits (Vegan, Vegetarian, Gluten, allergens, ...).

## CLI usage

The script works standalone, no agent needed:

```bash
# Preferred: self-contained (auto-installs requests via uv)
uv run .agents/skills/purdue-dining/scripts/menu.py --help

# Plain python3 (requires requests)
python3 .agents/skills/purdue-dining/scripts/menu.py --help
```

Examples:

```bash
python3 .agents/skills/purdue-dining/scripts/menu.py locations
python3 .agents/skills/purdue-dining/scripts/menu.py menu --court Ford --date today --meal dinner
python3 .agents/skills/purdue-dining/scripts/menu.py search "chicken" --court courts --meal dinner
python3 .agents/skills/purdue-dining/scripts/menu.py menu --court all --date friday --json
```

`--date` accepts `today` (default), `tomorrow`, `yesterday`, a weekday (`friday` = next occurrence), or `YYYY-MM-DD`. `--court` accepts a court name (`Ford`), `courts` (the 5 dining courts), or `all` (every location).

There's also `script.py` — the original interactive CLI (pick a court and date from prompts).

## Features

- Browse menus by dining court, date, and meal
- Search for foods across all dining locations
- Dietary filtering (vegan, vegetarian, gluten-free, allergens) via item traits
- JSON output (`--json`) for programmatic use

## Requirements

- Python 3.8+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `requests` installed
- Network access to `api.hfs.purdue.edu`

## Disclaimer

Not affiliated with or endorsed by Purdue University. Menu data comes from Purdue's public dining API and may be incomplete or out of date — always confirm with [Purdue Dining](https://dining.purdue.edu/) if accuracy matters (allergens especially).
