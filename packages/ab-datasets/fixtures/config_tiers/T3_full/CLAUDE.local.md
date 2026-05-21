# CLAUDE.local.md

Operator-local overrides not shared with team. Anonymized seed.

## Local paths

- Vault root: `~/Documents/<vault>/`
- Project root: `~/code/<project>/`
- Cache dir: `~/.cache/<project>/`

## Preferences

- Tool preferences:
  - `uv` over `pip` / `poetry`.
  - `pnpm` over `npm` / `yarn`.
  - `ripgrep` (`rg`) over `grep` when searching trees.
  - `fd` over `find` for filename search.
- Style preferences:
  - Black-formatted Python; line length 88 unless project says otherwise.
  - Ruff lint must pass before commit.
  - Two-space indent for YAML; tab for Makefiles.
  - No emoji in commit messages or PR descriptions.

## Workflow

- Always run tests before declaring done.
- Always run `gitnexus-impact-analysis` before editing exported APIs.
- Use `memory-session` skill on session start; do not skip.
- Conversational language: respond in the language the user wrote in.
- Russian and English both fine for chat; code + memory stays English.

## Local mocks

- `obsidian-memory` MCP runs against `~/Documents/<vault>/` by default.
- Override with `OBSIDIAN_VAULT_PATH` env if the run dir is elsewhere.
- `gitnexus` MCP indexes whatever git repo the current working
  directory is inside.

## Do NOT

- Do NOT modify operator config files (`~/.config/`, `~/.zshrc`, etc.)
  without explicit confirmation.
- Do NOT commit anything to the operator's local repos without
  asking.
- Do NOT auto-push tags or releases.
