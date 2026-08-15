# Hermes SkillForge — Responsive TUI Banner Design

## Goal

A fully responsive terminal banner (`hermes_skillforge_banner.py` / `skillforge banner`) that renders "HERMES / SKILLFORGE" block-style ASCII art with a green-to-sky-blue truecolor gradient, adapting gracefully to any terminal width and any color capability.

## Responsiveness tiers (by available width)

| Tier | Condition (width) | Rendering mode |
|---|---|---|
| 1 — Full block | >= 80 cols | 5x7 block glyphs (`█`), two stacked words, gradient per character column |
| 2 — Compact block | >= 64 cols | Block glyphs but thinner 4-wide letterforms; tighter kerning |
| 3 — One-liner | >= 40 cols | Thin 2-wide stroke letters, single line "HERMES SKILLFORGE" |
| 4 — Minimal | < 40 cols | Monochrome text logo: `◆ HERMES SKILLFORGE` with a single gradient swatch |

Each tier also re-computes the gradient so that it spans the actual rendered width (no clipped or repeated colors). On resize during live rendering, the banner is simply re-rendered at the current width.

## Font definitions

- `FONT_BLOCK` (5x7): letters A–Z, 0–9, space, hyphen, slash (derived from the user's provided glyph grid for H E R M S K I L F O G; missing letters synthesized in the same 5x7 block style to keep the set complete).
- `FONT_BLOCK_4` (4x7): compact version of the same alphabet.
- `FONT_THIN` (2x5): minimal stroke font for narrow terminals.

## Color handling (with fallbacks)

1. Detect truecolor via `COLORTERM=truecolor` / `TERM_PROGRAM` / terminfo.
2. If truecolor unavailable but 256-color: map each glyph column to the nearest 6x6x6 cube color (roundtrip-safe, same gradient feel).
3. If only 16 colors: single accent (bright green) banner.
4. If `--no-color` or NO_COLOR env: plain `█` art, still responsive.
5. Respect `NO_COLOR` per no-color.org convention.

## CLI

- Standalone: `python3 hermes_skillforge_banner.py`
- CLI flag: `skillforge banner` (new command), also printed by `skillforge --banner`.
- Options: `--width N` (force width), `--no-color`, `--animate` (draw-on animation, disabled under NO_COLOR), `--json` (emit render info for tests).
- No dependencies (stdlib only); works on Python 3.10+.

## Integration

- Module placed at `skill/scripts/banner.py` (importable) and `hermes_skillforge_banner.py` (standalone copy in repo root).
- `skillforge banner` command added to the engine CLI; banner also shown at the top of `skillforge` with no args (help screen).
- Tests: deterministic width-forced renders asserted via `--json` output; pytest cases in `skill/tests/`.
- CI: banner rendered on Linux (works, TIOCGWINSZ fallback to 80 cols when not a tty — so CI always prints a valid banner).
