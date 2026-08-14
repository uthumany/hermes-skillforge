# Contributing to Hermes SkillForge

Thank you for considering a contribution! Hermes SkillForge converts diverse
source formats into install-ready Hermes Agent skills, and every contribution
helps agents do more.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind,
be constructive, and assume good intent.

## How to Contribute

1. **Fork** the repository and create a feature branch
   (`git checkout -b feature/my-improvement`).
2. **Make your changes.** Follow the code conventions in `scripts/` — the
   engine is stdlib-only Python; no third-party imports please.
3. **Test your changes:**
   ```
   python3 -m pytest tests/ -q          # engine suite
   python3 -m py_compile scripts/skillforge.py
   ```
4. **Open a pull request** using the PR template. Describe the problem, the
   fix, and how it was verified. Mention any new formats you added detection
   for.

## Adding Support for a New Source Format

1. Add the format identifier to `FORMATS` in `scripts/skillforge.py`.
2. Extend `detect_format()` with scored evidence (file names, manifest
   structures, text markers).
3. Extend `extract_capabilities()` to harvest commands, scripts, tools,
   config keys, and dependencies from the new format.
4. Add a fixture under `examples/` and a test in
   `tests/test_skillforge_engine.py` covering the new detection path.
5. Document the format in `references/format-detection.md` and this README.

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `security:`.

## Questions

Open a discussion or an issue with the **question** label — we are happy to
help before you invest time in a big change.
