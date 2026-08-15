#!/usr/bin/env python3
"""
Responsive terminal banner: HERMES SKILLFORGE
Block-style ASCII art with green -> sky blue truecolor gradient.
Fully responsive: adapts font/size to terminal width, falls back on
256-color / 16-color / monochrome terminals, honors NO_COLOR.

Usage:
    python3 hermes_skillforge_banner.py            # auto-detect width
    python3 hermes_skillforge_banner.py --width 50 # force width
    python3 hermes_skillforge_banner.py --no-color # plain ASCII
    python3 hermes_skillforge_banner.py --animate  # typewriter draw-on

Stdlib-only, Python 3.10+.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

# ---------------------------------------------------------------------------
# Fonts — each glyph is a list of row strings; '1' = filled.
# ---------------------------------------------------------------------------

# 5x7 block alphabet (A-Z, digits, space, hyphen, slash)
FONT_BLOCK: dict[str, list[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["11111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00001", "00010", "00100", "01000", "10000", "10000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00000", "00100"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
}

# 4x7 compact block alphabet
FONT_BLOCK_4: dict[str, list[str]] = {
    "A": ["0110", "1001", "1111", "1001", "1001", "1001", "1001"],
    "B": ["1110", "1001", "1001", "1110", "1001", "1001", "1110"],
    "C": ["0110", "1001", "1000", "1000", "1000", "1001", "0110"],
    "D": ["1110", "1001", "1001", "1001", "1001", "1001", "1110"],
    "E": ["1111", "1000", "1000", "1110", "1000", "1000", "1111"],
    "F": ["1111", "1000", "1000", "1110", "1000", "1000", "1000"],
    "G": ["0110", "1001", "1000", "1011", "1001", "1001", "0111"],
    "H": ["1001", "1001", "1001", "1111", "1001", "1001", "1001"],
    "I": ["1111", "0010", "0010", "0010", "0010", "0010", "1111"],
    "J": ["1111", "0010", "0010", "0010", "0010", "1010", "0100"],
    "K": ["1001", "1010", "1100", "1100", "1010", "1001", "1001"],
    "L": ["1000", "1000", "1000", "1000", "1000", "1000", "1111"],
    "M": ["1001", "1111", "1010", "1010", "1001", "1001", "1001"],
    "N": ["1001", "1101", "1011", "1011", "1001", "1001", "1001"],
    "O": ["0110", "1001", "1001", "1001", "1001", "1001", "0110"],
    "P": ["1110", "1001", "1001", "1110", "1000", "1000", "1000"],
    "Q": ["0110", "1001", "1001", "1001", "1011", "1100", "0111"],
    "R": ["1110", "1001", "1001", "1110", "1010", "1001", "1001"],
    "S": ["0111", "1000", "1000", "0110", "0001", "0001", "1110"],
    "T": ["1111", "0010", "0010", "0010", "0010", "0010", "0010"],
    "U": ["1001", "1001", "1001", "1001", "1001", "1001", "0110"],
    "V": ["1001", "1001", "1001", "1001", "1001", "0110", "0000"],
    "W": ["1001", "1001", "1010", "1111", "1111", "1010", "1001"],
    "X": ["1001", "1001", "0110", "0000", "0110", "1001", "1001"],
    "Y": ["1001", "1001", "0110", "0000", "0010", "0010", "0010"],
    "Z": ["1111", "0001", "0010", "0100", "1000", "1000", "1111"],
    "0": ["0110", "1001", "1011", "1101", "1001", "1001", "0110"],
    "1": ["0010", "0110", "0010", "0010", "0010", "0010", "0111"],
    "2": ["0110", "1001", "0001", "0010", "0100", "1000", "1111"],
    "3": ["1110", "0001", "0001", "0110", "0001", "0001", "1110"],
    "4": ["0010", "0110", "1010", "1111", "0010", "0010", "0010"],
    "5": ["1111", "1000", "1000", "1110", "0001", "0001", "1110"],
    "6": ["0110", "1000", "1000", "1110", "1001", "1001", "0110"],
    "7": ["1111", "0001", "0010", "0100", "0100", "0100", "0100"],
    "8": ["0110", "1001", "1001", "0110", "1001", "1001", "0110"],
    "9": ["0110", "1001", "1001", "0111", "0001", "0001", "0110"],
    " ": ["0000", "0000", "0000", "0000", "0000", "0000", "0000"],
    "-": ["0000", "0000", "0000", "1111", "0000", "0000", "0000"],
    "/": ["0001", "0001", "0010", "0100", "1000", "1000", "0000"],
    ".": ["0000", "0000", "0000", "0000", "0000", "0000", "0010"],
    "+": ["0000", "0010", "0010", "1111", "0010", "0010", "0000"],
}

# 2x5 thin stroke alphabet (for narrow terminals)
FONT_THIN: dict[str, list[str]] = {
    "A": ["01", "11", "10", "11", "10"],
    "B": ["10", "11", "10", "11", "10"],
    "C": ["11", "10", "10", "10", "11"],
    "D": ["10", "11", "10", "11", "10"],
    "E": ["11", "10", "11", "10", "11"],
    "F": ["11", "10", "11", "10", "10"],
    "G": ["11", "10", "11", "11", "11"],
    "H": ["11", "11", "10", "11", "11"],
    "I": ["11", "01", "01", "01", "11"],
    "J": ["01", "01", "01", "11", "10"],
    "K": ["11", "10", "11", "10", "11"],
    "L": ["10", "10", "10", "10", "11"],
    "M": ["11", "10", "11", "11", "11"],
    "N": ["11", "10", "11", "11", "11"],
    "O": ["11", "11", "10", "11", "11"],
    "P": ["11", "10", "11", "10", "10"],
    "Q": ["11", "11", "10", "11", "01"],
    "R": ["11", "10", "11", "10", "11"],
    "S": ["11", "10", "01", "01", "11"],
    "T": ["11", "01", "01", "01", "01"],
    "U": ["11", "11", "10", "11", "11"],
    "V": ["11", "11", "10", "10", "10"],
    "W": ["11", "11", "10", "11", "11"],
    "X": ["11", "10", "01", "10", "11"],
    "Y": ["11", "10", "01", "01", "01"],
    "Z": ["11", "01", "10", "10", "11"],
    "0": ["11", "11", "10", "11", "11"],
    "1": ["01", "01", "01", "01", "01"],
    "2": ["11", "01", "10", "10", "11"],
    "3": ["11", "01", "11", "01", "11"],
    "4": ["01", "11", "10", "01", "01"],
    "5": ["11", "10", "11", "01", "11"],
    "6": ["11", "10", "11", "11", "11"],
    "7": ["11", "01", "10", "10", "10"],
    "8": ["11", "11", "11", "11", "11"],
    "9": ["11", "11", "01", "11", "11"],
    " ": ["00", "00", "00", "00", "00"],
    "-": ["00", "00", "11", "00", "00"],
    "/": ["01", "01", "00", "10", "10"],
    ".": ["00", "00", "00", "00", "01"],
    "+": ["00", "01", "11", "01", "00"],
}

BLOCK = "\u2588"  # full block

# Gradient endpoints: green -> sky blue
START = (0x22, 0xC5, 0x5E)
END = (0x38, 0xBD, 0xF8)

ACCENT_16 = 92  # bright green under 16-color mode


def get_glyphs(font_name: str) -> dict[str, list[str]]:
    return {
        "block": FONT_BLOCK,
        "block4": FONT_BLOCK_4,
        "thin": FONT_THIN,
    }[font_name]


# ---------------------------------------------------------------------------
# Terminal / color capability detection
# ---------------------------------------------------------------------------

def get_width(override: int | None) -> int:
    """Return available terminal width (never below 10, never above 1024)."""
    width = override
    if width is None:
        try:
            width = shutil.get_terminal_size((80, 24)).columns
        except Exception:
            width = 80
    return max(10, min(1024, int(width)))


def color_mode() -> str:
    """Return 'truecolor', 'ansi256', 'ansi16', or 'mono'."""
    if os.environ.get("NO_COLOR", "") != "" or os.environ.get("TERM", "") == "dumb":
        return "mono"
    colorterm = os.environ.get("COLORTERM", "")
    if colorterm in ("truecolor", "24bit"):
        return "truecolor"
    term = os.environ.get("TERM_PROGRAM", "")
    if term in ("iTerm.app", "WezTerm", "Hyper", "WindowsTerminal", "vscode"):
        return "truecolor"
    term_prog = os.environ.get("TERM", "")
    if term_prog.startswith(("xterm", "screen", "tmux")):
        return "truecolor"  # modern xterm-family all support 24-bit
    try:
        import curses  # noqa: F401
    except ImportError:
        pass
    return "ansi256"  # conservative default


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * max(0.0, min(1.0, t)))


def nearest_256(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return 16 + 36 * (r // 43) + 6 * (g // 43) + (b // 43)


def render_rows(word: str, font: str) -> list[str]:
    glyphs = get_glyphs(font)
    rows = [""] * 7 if font in ("block", "block4") else [""] * 5
    for ch in word.upper():
        glyph = glyphs.get(ch, glyphs[" "])
        for r in range(len(rows)):
            rows[r] += "".join(BLOCK if c == "1" else " " for c in glyph[r])
            rows[r] += " "
    return rows


def banner_lines(width: int) -> tuple[list[str], str]:
    """Pick the best font tier for the width; return (lines, tier_name)."""
    single_w = width  # for one-liner mode
    block_w = FONT_BLOCK["W"][0].__len__  # 5
    w4 = FONT_BLOCK_4["W"][0].__len__  # 4

    # Full block: "HERMES" = 6*6-1 = 35 cols; "SKILLFORGE" = 10*6-1 = 59 cols
    if width >= 80:
        lines = render_rows("HERMES", "block") + [""] + render_rows("SKILLFORGE", "block")
        return lines, "block"
    # Compact block 4-wide: HERMES = 6*5-1 = 29; SKILLFORGE = 10*5-1 = 49
    if width >= 64:
        lines = render_rows("HERMES", "block4") + [""] + render_rows("SKILLFORGE", "block4")
        return lines, "block4"
    # Thin one-liner
    if width >= 40:
        glyphs = get_glyphs("thin")
        row_parts = [""] * 5
        text = "HERMES SKILLFORGE"
        for ch in text:
            glyph = glyphs.get(ch, glyphs[" "])
            for r in range(5):
                row_parts[r] += "".join(BLOCK if c == "1" else " " for c in glyph[r])
                row_parts[r] += " "
        lines = [""] * (5 - len(row_parts)) + row_parts
        # prepend a small divider banner line
        lines = [f"\u2500" * min(width, 48)] + lines + [f"\u2500" * min(width, 48)]
        return lines, "thin"
    # Minimal mono logo
    label = "HERMES SKILLFORGE"
    lines = [label]
    return lines, "minimal"


def gradient_line(line: str, width: int, mode: str, no_color: bool) -> str:
    if no_color or mode == "mono":
        return line
    out = []
    col_idx = 0
    total = width
    for ch in line:
        t = col_idx / max(total - 1, 1) if ch != " " else None
        if ch == " ":
            out.append(" ")
        else:
            r = lerp(START[0], END[0], t or 0.0)
            g = lerp(START[1], END[1], t or 0.0)
            b = lerp(START[2], END[2], t or 0.0)
            if mode == "truecolor":
                out.append(f"\033[1m\033[38;2;{r};{g};{b}m{ch}\033[0m")
            elif mode == "ansi256":
                out.append(f"\033[1m\033[38;5;{nearest_256((r, g, b))}m{ch}\033[0m")
            else:
                out.append(f"\033[1m\033[38;5;{ACCENT_16}m{ch}\033[0m")
        col_idx += 1
    return "".join(out)


def build(width: int, no_color: bool = False) -> dict:
    mode = "mono" if no_color else color_mode()
    lines, tier = banner_lines(width)
    rendered_width = max((len(line) for line in lines), default=0) or width
    rendered = [gradient_line(line, rendered_width, mode, no_color) for line in lines]
    return {"width": width, "tier": tier, "color_mode": mode,
            "rendered_width": rendered_width, "lines": rendered}


def print_banner(width: int | None = None, no_color: bool = False,
                 animate: bool = False) -> dict:
    result = build(get_width(width), no_color)
    text_lines = result["lines"]

    if animate and result["color_mode"] != "mono":
        # Typewriter draw-on: reveal column by column
        import time
        try:
            w = shutil.get_terminal_size().columns
        except Exception:
            w = 80
        for frame in range(1, result["rendered_width"] + 1):
            sys.stdout.write("\033[2J\033[H")
            partial = []
            for line in text_lines:
                # strip ANSI to count visible columns
                stripped = _strip_ansi(line)
                partial.append(stripped[:frame].ljust(result["rendered_width"]))
            for pl in partial:
                sys.stdout.write(pl.rstrip() + "\n")
            sys.stdout.flush()
            time.sleep(0.012)
        sys.stdout.write("\033[2J\033[H")
        for line in text_lines:
            print(line)
    else:
        for line in text_lines:
            print(line)
    return result


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes SkillForge responsive banner")
    parser.add_argument("--width", type=int, default=None, help="force render width")
    parser.add_argument("--no-color", action="store_true",
                        help="plain ASCII, no ANSI colors")
    parser.add_argument("--animate", action="store_true",
                        help="typewriter draw-on animation")
    parser.add_argument("--json", action="store_true",
                        help="print render metadata as JSON (no banner)")
    # Allow being invoked after a parent CLI (e.g. `skillforge banner ...`)
    # where argv[1] is the word "banner": drop leading positional words
    # that come before the first "--" option.
    extra = sys.argv[1:]
    while extra and not extra[0].startswith("-") and extra[0] not in ("banner", "--"):
        extra = extra[1:]
    if extra and extra[0] == "banner":
        extra = extra[1:]
    args = parser.parse_args(extra)

    result = build(get_width(args.width), args.no_color)
    if args.json:
        import json
        meta = {k: v for k, v in result.items() if k != "lines"}
        meta["line_count"] = len(result["lines"])
        print(json.dumps(meta))
        return 0
    print_banner(width=args.width, no_color=args.no_color, animate=args.animate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
