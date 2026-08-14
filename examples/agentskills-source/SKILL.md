---
name: text-transform-pipeline
description: Text transformation pipeline helpers
version: 1.0.0
tools:
  terminal: required
---

# Text Transform Pipeline

Convert, normalize, and summarize text files using stdlib-only Python.

## Instructions

1. Copy `scripts/transform.py` into your working directory.
2. Run with `python3 scripts/transform.py --mode <mode> --input <path> --output <path>`.
3. Supported modes: `normalize` (whitespace/encoding cleanup), `dedupe` (remove duplicate lines), `wordcount` (frequency stats).

## Scripts

- `scripts/transform.py` — the pipeline itself; requires only Python 3.9+.

## Notes

- Works entirely offline; no network access required.
- Large files (>200 MB) should be processed in chunks manually.
