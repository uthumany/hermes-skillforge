#!/usr/bin/env python3
"""Text transformation pipeline: normalize, dedupe, wordcount."""
import argparse
import collections
import pathlib
import re
import sys


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def dedupe(text: str) -> str:
    seen, out = set(), []
    for line in text.splitlines(keepends=True):
        key = line.rstrip()
        if key in seen:
            continue
        seen.add(key)
        out.append(line if line.endswith("\n") else line + "\n")
    return "".join(out)


def wordcount(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9'\u00C0-\u024F-]+", text.lower())
    freq = collections.Counter(words)
    lines = [f"{word}: {count}" for word, count in freq.most_common(25)]
    return "\n".join(lines) + f"\n\ntotal_words: {len(words)}\nunique_words: {len(freq)}\n"


MODES = {"normalize": normalize, "dedupe": dedupe, "wordcount": wordcount}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    src = pathlib.Path(args.input)
    if not src.is_file():
        print(f"error: input not found: {src}", file=sys.stderr)
        return 2
    result = MODES[args.mode](src.read_text(encoding="utf-8", errors="replace"))
    pathlib.Path(args.output).write_text(result, encoding="utf-8")
    print(f"wrote {args.mode} output to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
