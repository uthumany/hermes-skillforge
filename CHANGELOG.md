# Changelog

All notable changes to Hermes SkillForge will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-08-15

### Added
- Universal conversion engine (`scripts/skillforge.py`) supporting 20+ source
  formats: Agent Skills / agentskills.io, Claude / Codex / Cursor skills,
  GitHub repositories and agent workflows, plugin repos, MCP server manifests,
  prompt packs, rules files, script collections, REST APIs, and existing
  Hermes skills.
- Ten interactive commands: `analyze`, `import`, `convert`, `preview`,
  `validate`, `test`, `repair`, `install`, `rollback`, `batch`.
- Official Hermes SKILL.md generation with the modern section order,
  frontmatter, and the 60-character description budget enforced.
- Per-skill pytest test-suite generation; engine self-suite at 10/10 passing.
- 0-100 quality scoring, secret detection and redaction, and unmapped
  functionality tracking.
- Auto-repair loop that iterates validation fixes until the skill is clean.
- Install to `~/.hermes/skills/<category>/` with conflict detection and
  rollback snapshots.
- Scoring-based format detection with high-confidence MCP manifest recognition
  (`mcp-server.json`, `*.mcp.json`, `tools`/`mcpServers` JSON).
- Safe handling of host-dependent placeholder scripts (static validation
  instead of execution).

### Security
- Detected secrets are redacted from generated files and reported in
  `references/security-findings.md`; tokens are never written into skill output.
