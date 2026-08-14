# Format Detection Rules

This reference documents how SkillForge identifies the source format of an
imported tree. Detection is heuristic and score-based; the highest-scoring
format wins unless the second-best score is within 0.5 points and human
judgment is requested.

## Format signatures

| Format | Primary signature | Secondary signals |
|---|---|---|
| `hermes_skill` | `SKILL.md` with `metadata.hermes` frontmatter | Hermes tool names (`terminal`, `skill_view`) in body |
| `agent_skills` | `SKILL.md` with `name` frontmatter and optional `allowed-tools` or `compatibility` | Parent dir `.claude/`, `.codex/`, `.agents/` |
| `cursor_rules` | `.mdc` files present | `.cursor/rules/` path structure |
| `plugin_repo` | `plugin.yaml` at root | `register()` calls in an `__init__.py` subpackage |
| `mcp_server` | MCP imports/config: `FastMCP`, `mcp.server`, `@mcp.tool` | `mcp` in filenames |
| `python_tool` | ≥1 `.py` file containing `def ` | `requirements*.txt`, `setup.py` |
| `js_tool` | `.js` / `.mjs` / `.ts` files | `package.json` |
| `shell_scripts` | `.sh` files | shebangs `#!/bin/bash` |
| `rest_api` | `openapi`, `/v1/`, endpoint tables | curl examples in docs |
| `workflow_repo` | `workflows/`, `.github/workflows/`, `playbooks/`, `agents/` dirs | README/agent/workflow-prefixed files |
| `system_prompt` | Unstructured markdown/text > 800 chars, ≤1 code file | No structured headers or scripts |

## Confidence

`high` requires a score ≥ 3.0 (a canonical marker such as `plugin.yaml` or a
frontmatter-parsed `SKILL.md`). `medium` requires ≥ 1.5; `low` below that, in
which case the agent must ask the user what the source is for.

## Ambiguity handling

An Agent Skills `SKILL.md` without Hermes metadata still converts correctly
because the open standard layout (name/description frontmatter, body,
`scripts/`, `references/`, `assets/`) is nearly drop-in compatible. The
converter rewrites the frontmatter to Hermes fields and normalizes the body.

## Detection limits

The engine never claims a format it cannot see. If the tree contains a mix
(e.g., a repo with both an MCP server and shell scripts), the primary format
is the one driving the SKILL.md structure, and everything else is mapped as
capabilities (scripts preserved, MCP server documented in `references/`).
