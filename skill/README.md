# Hermes SkillForge

A Hermes Agent skill that converts diverse source formats into install-ready
Hermes skills: Agent Skills / Claude / Codex / Cursor skills, GitHub
repositories and agent workflows, plugins, MCP integrations, rules files,
prompt packs, script collections, REST API integrations, and existing
Hermes skills.

## Quick start

```
python3 scripts/skillforge.py import <url-or-path>   # full pipeline
python3 scripts/skillforge.py validate               # validate output
python3 scripts/skillforge.py test                   # run generated tests
python3 scripts/skillforge.py install                # install to ~/.hermes/skills/
```

All subcommands are documented in `scripts/skillforge.py --help`.

## Design guarantees

- Every capability is mapped, adapted, or documented as unmapped — never dropped
- Secrets are redacted and reported, never copied
- Generated skills pass the Hermes hardline validator and an 18-case test suite
- Installations are snapshotted for rollback before any modification
