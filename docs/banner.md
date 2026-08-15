# Hermes SkillForge — Responsive TUI Banner

A fully responsive terminal banner that renders **HERMES / SKILLFORGE** in block-style ASCII art with a green-to-sky-blue truecolor gradient, adapting automatically to any terminal width and any color capability. Stdlib-only, Python 3.10+, zero dependencies.

## Quick start

```bash
# Standalone
python3 hermes_skillforge_banner.py

# Via the skillforge CLI
skillforge banner
# or with the repo wrapper
python3 scripts/skillforge banner
```

## Options

| Flag | Effect |
|---|---|
| `--width N` | Force a specific render width (useful for screenshots, embeds, non-tty contexts) |
| `--no-color` | Plain monochrome ASCII (also triggered by `NO_COLOR=1`) |
| `--animate` | Typewriter draw-on animation |
| `--json` | Print render metadata as JSON (tier, color mode, widths) — used by the test suite |

## Responsiveness tiers

The banner chooses its font and layout by measuring the terminal width at render time, so the same command looks right on a 200-column iTerm split pane and on a 35-character SSH window.

| Available width | Tier | Rendered layout |
|---|---|---|
| >= 80 cols | Full block (5x7 glyphs) | `HERMES` over `SKILLFORGE` |
| >= 64 cols | Compact block (4x7 glyphs) | `HERMES` over `SKILLFORGE` |
| >= 40 cols | Thin stroke (2x5 glyphs) | Single-line `HERMES SKILLFORGE` between rules |
| < 40 cols | Minimal | Plain text `HERMES SKILLFORGE` |

## Color handling

1. **Truecolor (24-bit)**: smooth per-character green `#22c55e` → sky blue `#38bdf8` gradient when `COLORTERM=truecolor/24bit`, a modern TERM_PROGRAM, or a TERM starting with `xterm`/`screen`/`tmux` is detected.
2. **ANSI 256**: nearest cube-color mapping preserves the gradient feel on older terminals.
3. **16-color**: single bright-green accent.
4. **Monochrome**: `NO_COLOR` or `TERM=dumb` produces plain block art — the banner never emits ANSI when colors are unavailable.

## As a library

```python
from banner import build, get_width

result = build(get_width(None))          # auto terminal width
print("\n".join(result["lines"]))        # ANSI-rendered lines
print(result["tier"], result["color_mode"], result["rendered_width"])
```

## Tests

Ten new cases in `skill/tests/test_skillforge_engine.py::TestBanner` cover tier selection at four widths, all three color modes, the CLI integration (`skillforge banner`), gradient start/end colors, and width bounds. The engine suite now totals 20 passing tests, and the CI matrix runs them on every push.
