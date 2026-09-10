# Dining Bot

Purdue Dining Courts Bot

## Agent Skill

An [Agent Skills](https://agentskills.io) compatible skill lives at `.agents/skills/purdue-dining/` (spec: `SKILL.md` + `scripts/menu.py`). Any spec-compliant agent (OpenCode, Claude Code, VS Code/Copilot, Gemini CLI, Codex, Goose, etc.) discovers it automatically from that directory.

- Interactive CLI: `python3 script.py`
- Agent CLI (non-interactive, used by the skill): `uv run .agents/skills/purdue-dining/scripts/menu.py --help`

## Future Feature Ideas

Basic:
- Set notifications on favorite Purdue Dining food options
- Weekly Schedule highlighting when favorited foods are available in the future

Extended w/ LLM:
- Daily summary of what foods are available
    - Filter by dietary restrictions (LLM-powered filtering)
- Ask complex queries (search for when certain food will next be available, what certain foods are, etc.)

