# Validator Rules (Hermes Hardline)

The engine's validator mirrors the hardline constraints enforced by the Hermes
`skill_manager_tool` in `NousResearch/hermes-agent`. Violations are errors;
the 27 hardline rules in the repo's validator include, among others, the
subset below. Softline rules become warnings.

## Frontmatter (errors if violated)

| Rule | Constraint |
|---|---|
| Structure | SKILL.md must start with `---` immediately (no leading blank line, BOM, or text) |
| Closing fence | Frontmatter must end with `---` followed by a newline |
| `name` | required; 1–64 chars; `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`; must equal the skill directory name |
| `description` | required; ≤1024 chars; ≤60 chars for new skills (index truncates at 57 + "..."); must end with a period |
| Content size | full file ≤100,000 characters |
| Sections | `## When to Use` and `## Procedure` required in body |
| Naming collisions | `skill`, `skill-forge`, `skillforge` disallowed as names |

## Supporting files (errors if violated)

| Rule | Constraint |
|---|---|
| Supporting file size | ≤1 MiB each (`references/`, `templates/`, `scripts/`) |
| Binary scripts | scripts must be UTF-8 text |
| Missing references | files named in `skill_view(...)` calls must exist |
| Leaked secrets | any secret pattern surviving redaction fails validation |

## Softline (warnings)

Missing `version`, `platforms`, `metadata.hermes.tags`, and optional
references that are mentioned in body prose but absent.

## What the generated test suite asserts

The auto-generated pytest suite additionally enforces: frontmatter parses and
contains all required fields; the name matches the directory and obeys the
regex; the description fits the 60-char budget and ends with a period; the
body contains the minimum sections (When to Use, Procedure, Verification); no
raw shell utilities (`sh`, `bash`, `cat`, `grep` …) appear in backtick spans
without `terminal` framing; scripts exit recognizably on bad input; declared
dependencies are checkable; no network assumptions go undocumented; unmapped
functionality is recorded in the README; and referenced files exist.
