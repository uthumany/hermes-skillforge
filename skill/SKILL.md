---
name: hermes-skillforge
description: Convert skills, repos, and tools into Hermes skills.
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
dependencies: [python3]
metadata:
  hermes:
    tags: [skills, conversion, import, agent-skills, plugin, automation]
    related_skills: [hermes-agent]
    category: software-development
---
# Hermes SkillForge
Convert an existing agent skill, repository, workflow, plugin, MCP integration,
rules file, script collection, or tool definition into a valid, install-ready
Hermes Agent skill. Accepts: GitHub/git repositories, local directories, ZIP
archives, `SKILL.md` files (Agent Skills / Claude / Codex / Cursor formats),
AI system prompts, MCP servers, Python/JS/TS/shell tools, REST API
integrations, prompt libraries, existing Hermes skills, and plugin repos.

## When to Use
- The user wants to bring an external skill, workflow, or tooling into Hermes
- A repository contains an agent workflow worth reusing as a Hermes skill
- An MCP server, script collection, or REST integration should become a skill
- A prompt pack, rules file, or Markdown instruction set should become a skill
- Batch-convert many skills found in one directory or repository
- Don't use for: skills that already live in `~/.hermes/skills/` (already
  installed — just run them); writing a brand-new skill from scratch with no
  source material (use the agent's normal workflow, not this converter)

## Prerequisites
- `python3` (3.9+) — the conversion engine is a stdlib-only script, no pip
  packages required for conversion itself
- Optional for certain sources: `git` (for GitHub/git repositories), `zip`
  or Python's `zipfile` (auto-available)
- Network access if the source is a URL; if the user provides local files, no
  network is needed

## How to Run
All conversion work is delegated to the engine script:

`terminal(command="python3 scripts/skillforge.py <subcommand> ...", timeout=120)`

Subcommands (all documented in `scripts/skillforge.py --help`):
- `import <source>` — full pipeline: import → analyze → convert
- `analyze <source>` — detect format and list detected capabilities without
  generating files
- `convert <source>` — convert without installing
- `preview` — render the generated SKILL.md of the last conversion
- `validate` — run the Hermes validator against the last conversion
- `test` — run the sandbox test suite for the last conversion
- `repair` — auto-repair failing validation/tests, re-runs both
- `install` — install the last validated conversion into
  `~/.hermes/skills/<category>/`
- `batch <directory>` — convert every convertible source found under a
  directory or cloned repository
- `rollback [--all]` — restore pre-install state from the last install (or all
  recorded installs)

State lives in `~/.hermes/skillforge/` (workspace: `last_conversion/`,
`installed/`, `rollbacks/`). The workspace is created automatically; no setup
needed.

## Procedure
1. **Detect** — run `python3 scripts/skillforge.py analyze <source>`
   (`<source>` may be a URL, repo path, directory, ZIP, or file). Record the
   detected format, capabilities, dependencies, and any compatibility issues
   the engine prints, and show them to the user.
2. **Confirm scope** — if the engine flags functionality with no safe Hermes
   equivalent, present the options (adapt, wrap in a generated plugin stub,
   skip with a documented limitation) and let the user choose. Only block
   when the user picks; auto-convert everything else.
3. **Convert** — run `python3 scripts/skillforge.py convert <source>`
   (or `import` to merge steps 1-3). Review the generated structure printed by
   the engine.
4. **Validate** — run `python3 scripts/skillforge.py validate`. The validator
   enforces Hermes hardline rules (see references/validator-rules.md).
5. **Repair if needed** — run `python3 scripts/skillforge.py repair`; it
   iterates validation + tests until clean or it identifies a genuine blocker.
   Report unresolved blockers precisely — never fake success.
6. **Test** — run `python3 scripts/skillforge.py test`.
7. **Preview and install** — run `preview`, then `install`. Confirm the
   install target printed by the engine, then verify live:
   `hermes skills list | grep <name>` or `hermes skills search <name>`.
8. **Report** — show the before/after summary, the quality score (0-100,
   printed by the engine), and any unresolved limitations.

**Batch mode:** `python3 scripts/skillforge.py batch <directory>` produces an
independent output directory, validation, test run, quality score, and error
report per converted skill.

## Cross-Format Mapping Quick Reference
| Source format | Primary mapping | Fallback |
|---|---|---|
| Agent Skills / Claude / Codex / Cursor skill (`SKILL.md`) | Direct structural copy + Hermes frontmatter | Adapt body sections to modern order |
| Git/GitHub repo with an agent workflow | Workflow → `## Procedure` steps; scripts → `scripts/` | Heavy logic → helper script + reference |
| Python/JS/TS/shell tool | Instruction wrapper around the tool; binary tool → generated plugin stub guidance | Document as unsupported, flag |
| MCP server | Document server + tool list; generated plugin skeleton | Keep as `references/mcp-tools.md`, skip install |
| REST API integration | Instructions + curl/HTTP snippets in body | Ship a small helper script |
| System prompt / prompt pack | Body sections (Procedure, Pitfalls); prompts → `templates/` | Flatten to one procedure |
| Existing Hermes skill | Re-validate + normalize frontmatter; copy as-is otherwise | Report as already compliant |
| Plugin repo | Install+enable guidance; surface bundled skills | Document as Hermes plugin, not a skill |

Full decision rules live in `references/format-detection.md` and
`references/conversion-rules.md`.

## Pitfalls
- The engine **never silently drops functionality**: everything unmappable is
  listed under "Unmapped functionality" in the conversion report; if the user
  does not want it documented, say so explicitly and it moves to a limitations
  note
- Secrets are stripped, never copied: API keys, tokens, and credentials
  detected by the security scanner become config fields in the generated
  frontmatter or placeholders, and are flagged in the report
- Prompt-injection text embedded in source files is quarantined into
  `references/security-findings.md` and flagged — the generated skill never
  inherits it as an instruction
- A generated Hermes plugin skeleton is documentation plus a working stub,
  not a shipped Python plugin: executable custom tools belong to the plugin
  system (`~/.hermes/plugins/`), and the engine tells the user how to enable
  one when needed
- Installed skills take effect in new sessions; run `/reset` or
  `hermes skills reset` for the current session
- The 60-character description hardline is enforced for new skills — the
  engine rewrites the source description to a trigger-first one-liner

## Verification
- `python3 scripts/skillforge.py validate` exits 0 and prints
  "VALID" for the generated skill
- `python3 scripts/skillforge.py test` shows all test cases passing
- `hermes skills search <name>` finds the installed skill, and
  `/skillforge-converted-name` appears as a slash command in a new session
