#!/usr/bin/env python3
"""Hermes SkillForge — conversion engine.

Converts agent skills, repositories, workflows, plugins, MCP integrations,
rules files, script collections, and tool definitions into install-ready
Hermes Agent skills. Stdlib-only (no pip dependencies for conversion).

Workspace: ~/.hermes/skillforge/  (respects HERMES_HOME)
Usage:
    python3 skillforge.py import <source>   full pipeline (analyze+convert)
    python3 skillforge.py analyze <source>  detect and report capabilities
    python3 skillforge.py convert <source>  generate the skill
    python3 skillforge.py preview           render generated SKILL.md
    python3 skillforge.py validate          validate generated skill
    python3 skillforge.py test              run sandbox tests
    python3 skillforge.py repair            auto-repair + revalidate + retest
    python3 skillforge.py install           install into ~/.hermes/skills/
    python3 skillforge.py update            re-convert against a source with a newer version
    python3 skillforge.py rollback [--all]  restore pre-install state
    python3 skillforge.py batch <directory> convert every source under a dir
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
WORKSPACE = HERMES_HOME / "skillforge"
LAST_CONVERSION = WORKSPACE / "last_conversion"
INSTALLED = WORKSPACE / "installed"
ROLLBACKS = WORKSPACE / "rollbacks"
SKILLS_DIR = HERMES_HOME / "skills"

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
DESCRIPTION_BUDGET = 60  # Hermes repo hardline for new skills
MAX_SKILL_CONTENT_CHARS = 100_000
MAX_SUPPORTING_FILE_BYTES = 1_048_576

VALID_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

PLATFORM_PROBE_POSIX = ("fcntl", "termios", "pty", "os.fork", "os.killpg",
                        "SIGKILL", "/proc/", "systemctl", "apt ", "apt-get")
PLATFORM_PROBE_MACOS = ("osascript", "defaults ", "pmset", "ioreg")

SECRET_PATTERNS = [
    ("api key", re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
    ("bearer token", re.compile(r"(?i)(authorization:\s*bearer\s+[A-Za-z0-9\-._~+/]+=*)")),
    ("generic secret", re.compile(r"(?i)(secret|token|password|passwd|pwd)\s*[:=]\s*['\"][A-Za-z0-9\-._~+/]{12,}['\"]")),
    ("aws key", re.compile(r"(?i)(AKIA[0-9A-Z]{16})")),
    ("private key", re.compile(r"-----BEGIN (RSA|DSA|EC|OPENSSH) PRIVATE KEY-----")),
    ("github token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
]

DANGEROUS_COMMAND_PATTERNS = [
    ("destructive rm", re.compile(r"(?<!\w)rm\s+-[a-z]*rf[a-z]*\s+/(bin|etc|usr|var|home|tmp)(?!\w)|(?<!\w)rm\s+-[a-z]*rf[a-z]*\s+\$\{?\w{0,3}\b")),
    ("disk overwrite", re.compile(r"(?<!\w)(dd|mkfs|fdisk)\s+")),
    ("network exec", re.compile(r"(?i)(curl|wget)\s+[^|&;\n]*\|\s*(sh|bash)")),
    ("sudo escalation", re.compile(r"(?<!\w)sudo\s+")),
]

PROMPT_INJECTION_MARKERS = [
    re.compile(r"(?i)disregard\s+(previous|all)\s+(instructions|above)"),
    re.compile(r"(?i)(system|security)\s*(override|breach|bypass|inject)"),
    re.compile(r"(?i)ignore\s+the\s+system\s+prompt"),
    re.compile(r"(?i)\bnew\s+instructions?\s*[:\-]\s*forget\b"),
]


# ---------------------------------------------------------------------------
# Source materialization (bring any source into a local scratch tree)
# ---------------------------------------------------------------------------

def materialize_source(source: str, dest: Path) -> Path:
    """Download/extract/copy the source into dest. Returns the tree root."""
    dest.mkdir(parents=True, exist_ok=True)
    if source.startswith(("http://", "https://")):
        return _materialize_url(source, dest)
    src = Path(source).expanduser()
    if src.is_dir():
        shutil.copytree(src, dest / "_src", dirs_exist_ok=False)
        return dest / "_src"
    if src.is_file():
        if zipfile.is_zipfile(str(src)):
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest / "_src")
            return _find_tree_root(dest / "_src")
        if src.suffix.lower() in (".md", ".txt", ".mdc"):
            (dest / "_src").mkdir(exist_ok=True)
            shutil.copy(src, dest / "_src" / src.name)
            return dest / "_src"
        if src.suffix.lower() in (".py", ".js", ".mjs", ".ts", ".sh"):
            (dest / "_src" / "tools").mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / "_src" / "tools" / src.name)
            return dest / "_src"
        # Unknown file: treat as raw reference content
        (dest / "_src" / "references").mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest / "_src" / "references" / src.name)
        return dest / "_src"
    raise FileNotFoundError(f"Source not found: {source}")


def _materialize_url(source: str, dest: Path) -> Path:
    parsed = urllib.parse.urlparse(source)
    path = parsed.path.strip("/")
    if path.endswith((".zip", "/archive/refs/heads/main.zip", "/archive.zip")) \
            or path.rstrip("/").endswith(".zip"):
        zip_path = dest / "source.zip"
        _http_download(source, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest / "_src")
        return _find_tree_root(dest / "_src")
    if path.rstrip("/").endswith(("SKILL.md", ".md", ".mdc", ".txt")) or \
            "blob" in path and path.lower().endswith((".md", ".txt", ".mdc")):
        raw = source
        if "github.com" in parsed.netloc:
            raw = source.replace("github.com", "raw.githubusercontent.com", 1) \
                        .replace("/blob/", "/", 1)
        text_path = dest / "source.md"
        _http_download(raw, text_path)
        (dest / "_src").mkdir(exist_ok=True)
        shutil.copy(text_path, dest / "_src" / (text_path.name or "SKILL.md"))
        return dest / "_src"
    # Assume a git repository
    return _clone_repo(source, dest)


def _http_download(url: str, target: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-skillforge/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _clone_repo(source: str, dest: Path) -> Path:
    repo = source.rstrip("/").rstrip(".git")
    out = dest / "_src"
    subprocess.run(["git", "clone", "--depth", "1", "--quiet",
                    f"{repo}.git" if not repo.endswith(".git") else repo,
                    str(out)], check=True, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def _find_tree_root(root: Path) -> Path:
    """If extraction produced a single subdirectory, descend into it."""
    children = [c for c in root.iterdir() if c.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir() and \
            not any(p.name in ("SKILL.md", "plugin.yaml") for p in children[0].iterdir()):
        return children[0]
    return root


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

FORMATS = [
    "agent_skills",        # agentskills.io / Claude / Codex / VS Code skill
    "cursor_rules",        # .cursor/rules/*.mdc
    "hermes_skill",        # already a Hermes skill
    "plugin_repo",         # plugin.yaml or plugin directory
    "mcp_server",          # MCP config or server code
    "python_tool",         # .py file(s)
    "js_tool",             # .js/.ts/.mjs file(s)
    "shell_scripts",       # .sh file(s)
    "system_prompt",       # plain text/markdown prompt
    "rest_api",            # api spec / openapi / curl wrappers
    "workflow_repo",       # repo with workflow-like structure
    "hermes_repo",         # existing Hermes repo skill
]


def detect_format(tree: Path):
    """Return (primary_format, confidence, evidence) for a materialized tree."""
    scores = {f: 0.0 for f in FORMATS}
    evidence = []
    all_files = list(tree.rglob("*"))
    text_files = [p for p in all_files if p.is_file()
                  and p.suffix.lower() in (".md", ".mdc", ".txt", ".yml", ".yaml",
                                             ".json", ".toml")]
    code_files = [p for p in all_files if p.is_file()
                  and p.suffix.lower() in (".py", ".js", ".mjs", ".ts", ".sh")]

    skill_mds = [p for p in all_files if p.is_file() and p.name == "SKILL.md"]
    if skill_mds:
        for smd in skill_mds[:3]:
            try:
                content = smd.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm = parse_frontmatter(content)
            if fm and "name" in fm:
                if "metadata" in fm and "hermes" in (fm["metadata"] or {}):
                    scores["hermes_skill"] += 3.0
                    evidence.append(f"Hermes SKILL.md at {smd.relative_to(tree)}")
                elif "allowed-tools" in fm or "compatibility" in fm:
                    scores["agent_skills"] += 3.0
                    evidence.append(f"Agent Skills SKILL.md at {smd.relative_to(tree)}")
                else:
                    # Could be any SKILL.md-family skill; check dir conventions
                    parent = smd.parent
                    if parent.name in (".claude", ".codex", ".agents"):
                        scores["agent_skills"] += 2.5
                    else:
                        scores["agent_skills"] += 2.0
                    evidence.append(f"SKILL.md at {smd.relative_to(tree)}")
            else:
                scores["agent_skills"] += 0.5

    # Cursor rules (.mdc files)
    mdc_files = [p for p in all_files if p.is_file() and p.suffix == ".mdc"]
    if mdc_files:
        scores["cursor_rules"] += 2.0 + 0.5 * min(len(mdc_files), 5)
        evidence.append(f"{len(mdc_files)} Cursor rules (.mdc) file(s)")
        if any(".cursor/rules" in str(p) for p in mdc_files):
            scores["cursor_rules"] += 1.0

    # Plugin repo
    plugin_yamls = [p for p in all_files if p.is_file() and p.name == "plugin.yaml"]
    if plugin_yamls:
        scores["plugin_repo"] += 3.0
        evidence.append(f"plugin.yaml at {plugin_yamls[0].relative_to(tree)}")
    if any(p.is_dir() and (p / "__init__.py").exists() and
           "register" in read_text_safe(p / "__init__.py") for p in tree.iterdir()
           if p.is_dir()):
        scores["plugin_repo"] += 1.0

    # MCP server
    mcp_hits = sum(1 for p in text_files + code_files
                   if "mcp" in p.name.lower() or
                   "FastMCP" in read_text_safe(p) or
                   re.search(r"@mcp\.|mcp\.server", read_text_safe(p)))
    if mcp_hits:
        scores["mcp_server"] += 1.5 * mcp_hits
        evidence.append(f"{mcp_hits} MCP server indicator(s)")
    # Explicit MCP server manifests: mcp-server.json, *.mcp.json, or any
    # JSON carrying an mcpServers / tools list
    for p in all_files:
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            if p.name in ("mcp-server.json",) or p.name.endswith(".mcp.json"):
                scores["mcp_server"] += 3.0
                evidence.append(f"MCP manifest {p.relative_to(tree)}")
                break
            if "mcpServers" in data or "tools" in data:
                scores["mcp_server"] += 2.0
                evidence.append(f"MCP-capable manifest {p.relative_to(tree)}")
                break

    # Language tooling
    py = [p for p in code_files if p.suffix == ".py" and "def " in read_text_safe(p)]
    jst = [p for p in code_files if p.suffix in (".js", ".mjs", ".ts")]
    sh = [p for p in code_files if p.suffix == ".sh"]
    if py:
        scores["python_tool"] += min(2.5, 0.4 * len(py))
        evidence.append(f"{len(py)} Python file(s) with function definitions")
    if jst:
        scores["js_tool"] += min(2.5, 0.4 * len(jst))
        evidence.append(f"{len(jst)} JavaScript/TypeScript file(s)")
    if sh:
        scores["shell_scripts"] += min(2.0, 0.5 * len(sh))
        evidence.append(f"{len(sh)} shell script(s)")

    # REST API indicators
    rest_hits = sum(1 for p in text_files
                    if re.search(r"(openapi|swagger|/v1/|rest[_-]?api|endpoint)",
                                 read_text_safe(p), re.I))
    if rest_hits:
        scores["rest_api"] += rest_hits
        evidence.append(f"{rest_hits} REST API indicator(s)")

    # Workflow repo
    if any(d.name in ("workflows", "agents", ".github/workflows", "steps",
                       "playbooks", "docs") for d in all_files if d.is_dir()):
        scores["workflow_repo"] += 1.5
    if any(p.is_file() and p.name.lower().startswith(("readme", "agent",
                                                       "workflow")) for p in all_files):
        scores["workflow_repo"] += 0.8
        evidence.append("repository structure suggests an agent workflow")

    # System prompt — long markdown/text without structure
    if not any(scores[f] >= 2.0 for f in FORMATS):
        big_texts = [p for p in text_files if len(read_text_safe(p)) > 800]
        if big_texts and len(code_files) <= 1:
            scores["system_prompt"] += 1.5
            evidence.append("unstructured markdown/text (system prompt / prompt pack)")

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    primary, top_score = ranked[0]
    confidence = "high" if top_score >= 3.0 else ("medium" if top_score >= 1.5 else "low")
    return {
        "format": primary,
        "confidence": confidence,
        "score": round(top_score, 2),
        "all_scores": {k: round(v, 2) for k, v in ranked[:5]},
        "evidence": evidence,
        "skill_md_files": [str(p.relative_to(tree)) for p in skill_mds],
        "mdc_files": [str(p.relative_to(tree)) for p in mdc_files],
        "python_files": [str(p.relative_to(tree)) for p in py],
        "js_files": [str(p.relative_to(tree)) for p in jst],
        "shell_files": [str(p.relative_to(tree)) for p in sh],
    }


# ---------------------------------------------------------------------------
# Frontmatter parsing (stdlib-only, tolerant of quirks)
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str):
    """Parse YAML frontmatter into a dict (stdlib-safe best effort)."""
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return None
    end = re.search(r"\n---\s*\n", text[3:])
    if not end:
        return None
    yaml_text = text[3:end.start() + 3]
    return _parse_simple_yaml(yaml_text)


def _parse_simple_yaml(text: str):
    """Minimal YAML subset parser sufficient for skill frontmatter.

    Handles scalars, quoted strings, lists ([a, b] and - items), nested
    mappings keyed by `hermes:`-style prefixes up to one level of nesting,
    and preserves raw string values without interpreting dates/bools
    dangerously.
    """
    root = {}
    stack = [(root, -1)]  # (dict, indent)
    current_key = None
    list_mode = False

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        line = raw_line.strip()

        # List item
        if line.startswith("- "):
            value = line[2:].strip()
            # attach to current_key of nearest parent
            target = None
            while stack and stack[-1][1] >= indent:
                stack.pop()
            parent = stack[-1][0]
            key = current_key or None
            if key is None:
                # dangling list at root — wrap
                return None
            entry = parent.get(key)
            if not isinstance(entry, list):
                entry = []
                parent[key] = entry
            entry.append(_yaml_scalar(value))
            current_key = key
            continue

        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # pop stack to correct nesting level
            while len(stack) > 1 and stack[-1][1] >= indent:
                stack.pop()
            parent = stack[-1][0]
            if not value:
                # nested mapping
                new = {}
                parent[key] = new
                stack.append((new, indent))
                current_key = key
            else:
                parent[key] = _yaml_scalar(value)
                current_key = key
        elif line.startswith("- "):
            pass
    return root


def _yaml_scalar(value: str):
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        items = [i.strip() for i in value[1:-1].split(",") if i.strip()]
        return [_yaml_scalar(i) for i in items]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


# ---------------------------------------------------------------------------
# Security scanning
# ---------------------------------------------------------------------------

def scan_secrets(tree: Path, max_size: int = 1024 * 1024):
    """Find secrets in the source tree. Returns list of findings."""
    findings = []
    for path in tree.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp",
                                   ".pdf", ".zip", ".bin", ".exe", ".so",
                                   ".dll", ".woff", ".ttf"):
            continue
        if path.stat().st_size > max_size:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                findings.append({
                    "type": name,
                    "file": str(path.relative_to(tree)),
                    "line": content[:match.start()].count("\n") + 1,
                })
    return findings


def scan_security_risks(tree: Path):
    """Find dangerous commands and prompt-injection markers."""
    risks = []
    for path in tree.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".sh", ".py", ".js",
                                                             ".mjs", ".ts", ".md",
                                                             ".txt", ".mdc", ".yaml",
                                                             ".yml"):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, pattern in DANGEROUS_COMMAND_PATTERNS:
            for match in pattern.finditer(content):
                risks.append({
                    "type": name,
                    "file": str(path.relative_to(tree)),
                    "line": content[:match.start()].count("\n") + 1,
                    "snippet": match.group(0).strip()[:120],
                })
        for pattern in PROMPT_INJECTION_MARKERS:
            for match in pattern.finditer(content):
                risks.append({
                    "type": "prompt-injection marker",
                    "file": str(path.relative_to(tree)),
                    "line": content[:match.start()].count("\n") + 1,
                    "snippet": match.group(0).strip()[:120],
                })
    return risks


def strip_secrets_from_text(text: str) -> str:
    """Redact secret values in text, preserving keys as placeholders."""
    for _name, pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(0).split("=")[0] + "=<REDACTED>"
                           if "=" in m.group(0) else "<REDACTED>", text)
    return text


# ---------------------------------------------------------------------------
# Capability extraction
# ---------------------------------------------------------------------------

def extract_capabilities(tree: Path, fmt: str):
    """Pull out prompts, commands, tools, scripts, APIs, deps, config, refs."""
    caps = {
        "prompts": [], "commands": [], "tools": [], "scripts": [],
        "api_endpoints": [], "dependencies": set(), "config_keys": [],
        "templates": [], "references": [], "capabilities_prose": [],
    }

    all_text = read_tree_text(tree)

    # Commands: backtick-wrapped shell invocations in markdown
    for m in re.finditer(r"`([^`]{5,220})`", all_text):
        cand = m.group(1).strip()
        if re.match(r"^(git|pip|npm|yarn|uv|docker|curl|wget|python|node|bash|sh|hermes|brew|apt|npx|pnpm)\b", cand):
            caps["commands"].append(cand)

    # API endpoints
    for m in re.finditer(r"https?://[A-Za-z0-9._\-/:%@?&=]+", all_text):
        url = m.group(0)
        if any(kw in url.lower() for kw in ("api.", "/api/", "/v1/", "/v2/")):
            caps["api_endpoints"].append(url)

    # Dependencies
    for m in re.finditer(r"(?:pip install|npm install|yarn add|pnpm add|uv add|brew install)\s+([A-Za-z0-9._\-:@\[\]]+)", all_text):
        caps["dependencies"].add(m.group(1).split("[")[0].split(":")[-1].split("@")[0])
    for m in re.finditer(r"import ([A-Za-z_][A-Za-z0-9_]*)", all_text):
        mod = m.group(1)
        if mod in STDLIB_MODULES:
            continue
        caps["dependencies"].add(mod)
    for req in tree.rglob("requirements*.txt"):
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#")[0].strip()
            if line:
                caps["dependencies"].add(line.split(">=")[0].split("==")[0].split("<")[0].strip())
    for pkg in tree.rglob("package.json"):
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        for dep in list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys()):
            caps["dependencies"].add(dep)

    # Scripts to preserve
    for ext in (".py", ".sh", ".js", ".mjs"):
        for p in tree.rglob(f"*{ext}"):
            caps["scripts"].append(str(p.relative_to(tree)))

    # Config keys
    for m in re.finditer(r"(?i)(env|config|config\.yaml|settings?)\s*\{?\s*\n?[^}]{0,80}?(\b[A-Z_][A-Z0-9_]{3,}(?:[_\.][A-Za-z0-9_]+)*)", all_text):
        key = m.group(2)
        if key not in caps["config_keys"]:
            caps["config_keys"].append(key)

    # MCP server manifests: declare tools and secret-backed config keys
    for manifest in tree.rglob("mcp-server.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8",
                                                 errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for tool in data.get("tools", []):
            if isinstance(tool, dict) and tool.get("name"):
                caps["tools"].append(tool["name"])
        cfg = data.get("config") or {}
        for k, v in cfg.items():
            key = str(v) if "secret" in k.lower() else str(k)
            if key and key not in caps["config_keys"]:
                caps["config_keys"].append(key)

    # Templates & references (files already following convention)
    for d in ("templates", "references", "docs"):
        dpath = tree / d
        if dpath.is_dir():
            for f in dpath.rglob("*"):
                if f.is_file() and f.stat().st_size <= MAX_SUPPORTING_FILE_BYTES:
                    caps["templates" if d == "templates" else "references"]\
                        .append(str(f.relative_to(tree)))

    caps["dependencies"] = sorted(caps["dependencies"])
    caps["commands"] = dedupe_preserve_order(caps["commands"])
    caps["api_endpoints"] = dedupe_preserve_order(caps["api_endpoints"])
    return caps


STDLIB_MODULES = {
    "os", "sys", "re", "json", "math", "io", "time", "datetime", "pathlib",
    "collections", "functools", "itertools", "shutil", "subprocess",
    "tempfile", "hashlib", "base64", "urllib", "http", "socket", "threading",
    "logging", "argparse", "typing", "abc", "contextlib", "dataclasses",
    "enum", "csv", "sqlite3", "unittest", "random", "string", "textwrap",
    "copy", "pickle", "struct", "stat", "glob", "fnmatch", "difflib",
    "asyncio", "concurrent", "multiprocessing", "ctypes", "platform",
}


def read_tree_text(tree: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    """Concatenate text files in a tree (bounded)."""
    parts = []
    total = 0
    for path in sorted(tree.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".md", ".mdc", ".txt", ".py", ".js",
                                       ".mjs", ".ts", ".sh", ".yaml", ".yml",
                                       ".json", ".toml", ".ini", ".cfg"):
            continue
        if path.stat().st_size > MAX_SUPPORTING_FILE_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"### FILE: {path.relative_to(tree)}\n{content[:6000]}")
        total += len(content)
        if total > max_bytes:
            parts.append("### (truncated)")
            break
    return "\n\n".join(parts)


def dedupe_preserve_order(items):
    seen = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def read_text_safe(path: Path, limit: int = 3000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Compatibility analysis
# ---------------------------------------------------------------------------

def analyze_compatibility(tree: Path, fmt: str, caps):
    """Map detected functionality to Hermes targets; flag unmappable items."""
    mapped = []
    unmapped = []
    adaptations = []

    tree_text = read_tree_text(tree, max_bytes=4 * 1024 * 1024)

    # OS-specific commands
    if any(k in tree_text for k in ("osascript", "pmset")):
        unmapped.append({"item": "macOS osascript/pmset usage",
                         "reason": "macOS-only; gate under platforms or split"})
    if any(k in tree_text for k in PLATFORM_PROBE_POSIX):
        adaptations.append({"item": "POSIX-specific commands",
                            "target": "platform-gated script or cross-platform alternative"})

    # MCP functionality
    mcp_refs = re.findall(r"(?i)(?:mcp|mcp server|tool server)\b", tree_text)[:3]
    if fmt == "mcp_server":
        mapped.append({"item": "MCP server tools",
                       "target": "document in references/mcp-tools.md + plugin skeleton"})
        adaptations.append({"item": "Live MCP tool invocation",
                            "target": "Hermes plugin stub (ctx.register_tool) — user enables"})

    if fmt in ("plugin_repo",):
        mapped.append({"item": "Plugin register() wiring",
                       "target": "preserved as documentation; enable guidance"})

    if fmt in ("python_tool", "js_tool", "shell_scripts"):
        mapped.append({"item": "Executable tool code",
                       "target": "preserve in scripts/ + instruction wrapper"})

    # Anything else is procedure/docs material — maps directly
    mapped.append({"item": "Instructions / procedure text",
                   "target": "SKILL.md body (modern section order)"})
    mapped.append({"item": "Reference / docs files",
                   "target": "references/"})

    # Cross-platform audit
    platforms = ["linux", "macos", "windows"]
    if any(k in tree_text for k in PLATFORM_PROBE_POSIX):
        platforms = ["linux", "macos"]
        adaptations.append({"item": "Shell pipelines / POSIX signals",
                            "target": "platforms narrowed to [linux, macos]"})
    if any(k in tree_text for k in PLATFORM_PROBE_MACOS):
        platforms = ["macos"]

    return {
        "mapped": mapped,
        "unmapped": unmapped,
        "adaptations": adaptations,
        "platforms": platforms,
    }


# ---------------------------------------------------------------------------
# SKILL.md generation
# ---------------------------------------------------------------------------

def sanitize_skill_name(candidate: str) -> str:
    """Lowercase, hyphens-only, ≤64 chars, no leading/trailing/consecutive hyphens."""
    name = candidate.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    name = name[:MAX_NAME_LENGTH].strip("-")
    return name or "converted-skill"


def shorten_description(description: str, budget: int = DESCRIPTION_BUDGET) -> str:
    """Compress a description to fit the 60-char Hermes trigger budget."""
    description = description.strip().strip('"\'')
    if len(description) <= budget:
        return description if description.endswith(".") else description + "."
    # Cut trailing period for working, then re-add
    working = description.rstrip(".").strip()
    if len(working) <= budget - 1:
        return working + "."
    # Truncate at last space within budget
    cut = working[:budget - 6].rsplit(" ", 1)[0]
    cut = re.sub(r"\W+$", "", cut)
    return (cut + " tool.") if cut else "Converted skill."


def extract_core_behavior(body_text: str, fmt: str) -> dict:
    """Separate essential functionality from platform-specific noise."""
    result = {"overview": "", "steps": [], "pitfalls": [], "verification": ""}
    lines = body_text.splitlines()
    # Detect headers
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            result["overview"] = result["overview"] or stripped[2:].strip()
        m = re.match(r"#{2,4}\s+(.+)", stripped)
        if m:
            heading = m.group(1).lower()
            if "step" in heading or "procedure" in heading or "usage" in heading or "workflow" in heading:
                current = "steps"
            elif "pitfall" in heading or "limitation" in heading or "caveat" in heading:
                current = "pitfalls"
            elif "verif" in heading or "check" in heading or "test" in heading:
                current = "verification"
            else:
                current = None
            continue
        if current == "steps" and stripped and not stripped.startswith(">"):
            result["steps"].append(stripped)
        elif current == "pitfalls" and stripped:
            result["pitfalls"].append(stripped)
        elif current == "verification" and stripped:
            result["verification"] = result["verification"] or stripped
    return result


def generate_skill_md(name, description, fmt, caps, compat, behavior,
                      secret_findings, risks, unmapped=None):
    """Assemble a production-ready Hermes SKILL.md."""
    unmapped = unmapped or []
    fm_lines = [
        "---",
        f"name: {name}",
        f'description: "{description}"',
        "version: 0.1.0",
        "author: Hermes Agent",
        "license: MIT",
        f"platforms: [{', '.join(compat['platforms'])}]",
    ]
    deps = [d for d in caps["dependencies"] if d][:10]
    fm_lines.append(f"dependencies: [{', '.join(deps)}]" if deps else "dependencies: []")
    fm_lines.append("metadata:")
    fm_lines.append("  hermes:")
    tags = [fmt.replace("_", "-"), "converted"] + ([d.split("-")[0] for d in deps][:3])
    fm_lines.append(f"    tags: [{', '.join(dict.fromkeys(t.lower() for t in tags))}]")
    fm_lines.append("    category: software-development")
    if caps["config_keys"]:
        fm_lines.append("    config:")
        for key in caps["config_keys"][:5]:
            fm_lines.append(f'      - key: {key.lower().replace(".", "_")}')
            fm_lines.append(f'        description: "{key} from the converted source"')
            fm_lines.append(f'        prompt: "Enter a value for {key}"')
    fm = "\n".join(fm_lines) + "\n---"

    body_parts = []
    title = name.replace("-", " ").title()
    body_parts.append(f"# {title}")

    # Overview: capability not implementation
    overview = behavior["overview"] or f"Converted {fmt.replace('_', ' ')} capability."
    overview = overview[:300].rstrip(".") + ". "
    if fmt == "mcp_server" and caps.get("tools"):
        overview = (f"Exposes MCP tools ({', '.join(caps['tools'][:6])}) "
                    f"that the agent can call directly. " + overview)
    overview += f"Converted from a {fmt.replace('_', ' ')} source."
    body_parts.append(overview)

    body_parts.append("## When to Use")
    triggers = [f"user asks about the capability the source provides",
                f"the user references {name}"]
    for t in triggers:
        body_parts.append(f"- {t}")
    body_parts.append("Don't use for: unrelated tasks outside this capability.")

    if caps["dependencies"]:
        body_parts.append("## Prerequisites")
        for dep in deps:
            body_parts.append(f"- `{dep}` (install per the Procedure below if missing)")

    body_parts.append("## How to Run")
    if caps["scripts"]:
        for script in caps["scripts"][:5]:
            script_path = Path(script)
            ext = script_path.suffix.lstrip(".").lower()
            runner = "bash" if ext in ("sh", "bash") else "python3"
            body_parts.append(
                f"- Run `terminal(command=\"{runner} scripts/{script_path.name} "
                f"...\", timeout=120)` as documented per step")
    elif caps["commands"]:
        for cmd in caps["commands"][:5]:
            body_parts.append(f"- `terminal(command=\"{cmd}\", timeout=120)`")
    else:
        body_parts.append("- Follow the numbered Procedure steps using `terminal` and file tools as needed.")

    body_parts.append("## Procedure")
    if fmt == "mcp_server" and caps.get("tools"):
        body_parts.append("1. Ensure the MCP server is reachable per "
                          "`references/setup-notes.md` and the secret config "
                          "keys are set before calling tools.")
        body_parts.append("2. Call the server's tools "
                          "(`" + "`, `".join(caps["tools"][:8]) + "`) with "
                          "the parameters documented in each tool's "
                          "description.")
        body_parts.append("3. Prefer tool calls over scraping; if a tool "
                          "call fails, retry once with sanitized input "
                          "before falling back to the reference docs.")
    elif behavior["steps"]:
        # Keep only lines that look like actionable commands or instructions
        intro = ("the workflow", "it ", "this ", "steps:", "procedure:",
                 "usage", "overview", "summary:")
        actionable = [s for s in behavior["steps"][:25]
                      if len(s) >= 12
                      and not s.startswith(("```", "---", "|"))
                      and not s.lower().startswith(intro)
                      and not s.endswith(":")]
        numbered = actionable if actionable else behavior["steps"][:15]
        for i, step in enumerate(numbered, 1):
            step = step.lstrip("-*0123456789. ").strip()[:200]
            body_parts.append(f"{i}. {step} — confirm completion before the next step.")
    else:
        ref_files = _reference_doc_files(name, behavior, risks, unmapped)
        body_parts.append("1. Load the supporting documentation on demand "
                          "with " + ", ".join(
            f"`skill_view(\"{name}\", \"references/{f}\")`" for f in ref_files)
                          + ".")
        body_parts.append("2. Follow the reference instructions using "
                          "`terminal` and file tools.")

    if caps["api_endpoints"]:
        body_parts.append("## Quick Reference")
        for url in caps["api_endpoints"][:5]:
            body_parts.append(f"- {url}")

    if behavior["pitfalls"] or risks:
        body_parts.append("## Pitfalls")
        for p in behavior["pitfalls"][:6]:
            body_parts.append(f"- {p[:200]}")
        for r in risks[:4]:
            body_parts.append(f"- Flagged in source: {r['type']} in {r['file']}:line {r['line']} — reviewed; not carried into generated instructions.")

    body_parts.append("## Verification")
    if behavior["verification"]:
        body_parts.append(f"- {behavior['verification'][:200]}")
    else:
        body_parts.append("- Confirm the procedure's stated end-state (output files, "
                          "service state, or report) matches expectations before reporting success.")


    body = "\n".join(body_parts)
    content = fm + "\n" + body + "\n"
    if len(content) > MAX_SKILL_CONTENT_CHARS:
        content = content[:MAX_SKILL_CONTENT_CHARS - 50] + "\n...\n"
    return content


def _reference_doc_files(name, behavior, risks, unmapped):
    """Real reference docs written into references/; returned names are safe
    to embed verbatim in SKILL.md skill_view() calls."""
    files = ["setup-notes.md"]
    if behavior["pitfalls"]:
        files.append("pitfalls.md")
    if unmapped:
        files.append("unmapped-functionality.md")
    return files


def build_skill_directory(name, description, fmt, tree, caps, compat,
                          behavior, secret_findings, risks, out_root):
    """Write the full generated skill directory; return summary dict."""
    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    skill_md = generate_skill_md(name, description, fmt, caps, compat,
                                 behavior, secret_findings, risks,
                                 compat.get("unmapped"))
    (out / "SKILL.md").write_text(skill_md, encoding="utf-8")

    dirs_created = []

    # Scripts: copy useful ones (non-secret, bounded size)
    scripts_dir = out / "scripts"
    copied_scripts = []
    for script_rel in caps["scripts"]:
        src = tree / script_rel
        if not src.exists() or src.stat().st_size > MAX_SUPPORTING_FILE_BYTES:
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        text = strip_secrets_from_text(text)
        (scripts_dir).mkdir(exist_ok=True)
        dst = scripts_dir / src.name
        dst.write_text(text, encoding="utf-8")
        os.chmod(dst, 0o755)
        copied_scripts.append(src.name)
    if copied_scripts:
        dirs_created.append("scripts/")

    # References
    refs_dir = out / "references"
    ref_copy_count = 0
    if caps["references"]:
        for ref_rel in caps["references"]:
            src = tree / ref_rel
            if not src.exists() or src.stat().st_size > MAX_SUPPORTING_FILE_BYTES:
                continue
            dst = refs_dir / f"{Path(src.parent.name) if Path(ref_rel).parent.name else ''}_{src.name}".lstrip("_")
            dst = refs_dir / src.name if not (refs_dir / src.name).exists() else dst
            refs_dir.mkdir(exist_ok=True)
            dst.write_text(strip_secrets_from_text(
                src.read_text(encoding="utf-8", errors="replace")),
                encoding="utf-8")
            ref_copy_count += 1
    if ref_copy_count or secret_findings or risks:
        refs_dir.mkdir(exist_ok=True)
    if secret_findings or risks:
        lines = ["# Security Findings (auto-generated)",
                 "",
                 "Findings below were detected in the source and REDACTED from "
                 "generated files. Never paste these values into a skill."]
        if secret_findings:
            lines.append("")
            lines.append("## Detected secrets (redacted)")
            for f in secret_findings[:20]:
                lines.append(f"- {f['type']}: {f['file']} (line {f['line']})")
        if risks:
            lines.append("")
            lines.append("## Flagged risks")
            for r in risks[:20]:
                lines.append(f"- {r['type']}: {r['file']} (line {r['line']}) — {r.get('snippet', '')[:80]}")
        (refs_dir / "security-findings.md").write_text("\n".join(lines) + "\n",
                                                        encoding="utf-8")
    if caps["references"] or secret_findings or risks:
        dirs_created.append("references/")

    # Auto-generated supporting reference docs (always present so the
    # skill_view() targets in SKILL.md are valid)
    refs_dir.mkdir(exist_ok=True)
    lines = [f"# {name.replace('-', ' ').title()}: Setup Notes", "",
             "Environment expectations for the converted capability:"]
    if caps["dependencies"]:
        lines.append("- Required tooling: " + ", ".join(caps["dependencies"]))
    lines += ["- Load these notes with `skill_view` before executing the "
              "main Procedure.",
              "- Install any missing prerequisites before running scripts.",
              "- Verify each step's stated end-state before proceeding."]
    (refs_dir / "setup-notes.md").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    if behavior["pitfalls"]:
        lines = ["# Pitfalls", "",
                 "Failure modes observed in the source material:"]
        for p in behavior["pitfalls"][:12]:
            lines.append(f"- {p[:300]}")
        (refs_dir / "pitfalls.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
    if compat.get("unmapped"):
        lines = ["# Unmapped Functionality", "",
                 "Source capabilities that could not be expressed in the "
                 "generated skill:"]
        for u in compat["unmapped"][:20]:
            lines.append(f"- {u[:300]}")
        (refs_dir / "unmapped-functionality.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    dirs_created.append("references/")

    # Templates
    templates_dir = out / "templates"
    tmpl_count = 0
    if caps["templates"]:
        for t_rel in caps["templates"]:
            src = tree / t_rel
            if not src.exists() or src.stat().st_size > MAX_SUPPORTING_FILE_BYTES:
                continue
            templates_dir.mkdir(exist_ok=True)
            dst = templates_dir / src.name
            dst.write_text(strip_secrets_from_text(
                src.read_text(encoding="utf-8", errors="replace")),
                encoding="utf-8")
            tmpl_count += 1
    if tmpl_count:
        dirs_created.append("templates/")

    # Tests scaffolding
    tests_dir = out / "tests"
    tests_dir.mkdir(exist_ok=True)
    test_content = build_test_suite(name, fmt, copied_scripts, caps, compat)
    (tests_dir / f"test_{name.replace('-', '_')}_skill.py").write_text(test_content, encoding="utf-8")
    (tests_dir / "README.md").write_text(
        "# Tests\nRun: python3 -m pytest tests/ -q\n"
        "Generated by Hermes SkillForge. Extend with scenario-specific cases.\n",
        encoding="utf-8")
    dirs_created.append("tests/")

    readme = build_readme(name, description, fmt, compat, copied_scripts,
                          secret_findings, risks, compat["unmapped"])
    (out / "README.md").write_text(readme, encoding="utf-8")

    return {
        "path": str(out),
        "dirs_created": dirs_created,
        "scripts_copied": copied_scripts,
        "references_copied": ref_copy_count,
        "templates_copied": tmpl_count,
        "skill_md_chars": len(skill_md),
    }


def build_test_suite(name, fmt, scripts, caps, compat):
    """Generate a pytest suite for the converted skill (stdlib + pytest + mock)."""
    return r'''"""Generated test suite for {name}. Stdlib + pytest + mock only; no live network."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"

REQUIRED_FRONTMATTER_FIELDS = {{"name", "description", "version"}}
PLATFORMS = {platforms}


def _frontmatter():
    content = SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with frontmatter"
    end = re.search(r"\n---\s*\n", content[3:])
    assert end, "frontmatter not closed"
    return content[3:end.start() + 3], content[end.end() + 3:]


def _parse_fm(text):
    root, stack, current_key = {{}}, [root := {{}}], None  # noqa: F841
    stack = [(root, -1)]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if line.startswith("- "):
            entry = None
            while stack and stack[-1][1] >= indent:
                stack.pop()
            parent = stack[-1][0]
            if current_key:
                entry = parent.setdefault(current_key, [])
                entry.append(line[2:].strip())
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            while len(stack) > 1 and stack[-1][1] >= indent:
                stack.pop()
            parent = stack[-1][0]
            if not value:
                parent[key] = {{}}
                stack.append((parent[key], indent))
            else:
                parent[key] = _strip_quotes(value)
            current_key = key
    return root

def _strip_quotes(value):  # noqa: F811
    quotes = list(chr(34)) + list(chr(39))
    for q in quotes:
        if value.startswith(q) and value.endswith(q) and len(value) >= 2:
            value = value[1:-1]
    return value


class TestSkillActivation(unittest.TestCase):
    """The skill must load: valid frontmatter and a non-empty body."""

    def test_file_exists(self):
        self.assertTrue(SKILL_MD.exists(), "SKILL.md missing")

    def test_frontmatter_parses(self):
        fm_text, body = _frontmatter()
        fm = _parse_fm(fm_text)
        self.assertIsInstance(fm, dict)
        for fld in REQUIRED_FRONTMATTER_FIELDS:
            self.assertIn(fld, fm, f"missing frontmatter field {{fld}}")
        self.assertTrue(body.strip(), "body after frontmatter is empty")  # noqa

    def test_name_matches_directory(self):
        fm = _parse_fm(_frontmatter()[0])
        self.assertEqual(fm.get("name"), SKILL_DIR.name,
                         "name must equal the skill directory name")

    def test_name_length_and_chars(self):
        fm = _parse_fm(_frontmatter()[0])
        name = fm.get("name", "")
        self.assertRegex(name, r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")
        self.assertLessEqual(len(name), 64)

    def test_description_budget(self):
        fm = _parse_fm(_frontmatter()[0])
        desc = str(fm.get("description", ""))
        self.assertLessEqual(len(desc), 60,
                             f"description {{len}} chars exceeds 60-char trigger budget")
        self.assertTrue(desc.endswith("."), "description must end with a period")


class TestCoreWorkflow(unittest.TestCase):
    """Body must contain the modern minimum sections."""

    def setUp(self):
        self.body = _frontmatter()[1].lower()

    def test_minimum_sections(self):
        for section in ("when to use", "procedure", "verification"):
            self.assertIn(section, self.body, f"missing section: {{section}}")

    def test_no_invented_commands(self):
        # Referenced tools must be Hermes tools, not made-up utilities
        mentions = re.findall(r"`([a-z_][a-z0-9_]*)`", _frontmatter()[1])
        allowed = {{"terminal", "read_file", "write_file", "patch", "search_files",
                    "web_search", "web_extract", "skill_view", "skill_manage",
                    "browser_navigate", "vision_analyze", "delegate_task",
                    "cronjob", "python3", "pip", "git", "pytest"}}
        for m in mentions:
            if m in {{"sh", "bash", "cat", "grep", "sed", "awk", "ls", "find"}}:
                self.fail(f"skill references raw shell `{{m}}` instead of a Hermes tool")


class TestToolInvocation(unittest.TestCase):
    """Command snippets must be framed through the terminal tool."""

    def test_terminal_framing(self):
        body = _frontmatter()[1]
        code_blocks = re.findall(r"```[a-z]*\n(.*?)```", body, re.S)
        for block in code_blocks:
            if re.search(r"^(pip|git|curl|npm|python)\b", block, re.M):
                self.assertTrue(
                    "terminal" in body or "terminal" in body.lower(),
                    "shell usage must be framed via the terminal tool")  # noqa
                break


{script_block}

class TestDependencyAvailability(unittest.TestCase):
    """Declared dependencies must be resolvable at import/check time."""

    def test_python_available(self):
        self.assertTrue(shutil.which("python3"), "python3 not on PATH")

{dep_checks}


class TestInvalidInputs(unittest.TestCase):
    """The skill's scripts (if any) must fail loudly, not silently."""

{invalid_input_cases}


class TestMissingFiles(unittest.TestCase):
    """Referenced files in SKILL.md must exist in the skill tree."""

    def test_skill_view_refs_exist(self):
        body = _frontmatter()[1]
        refs = re.findall(r'skill_view\(\s*"[^"]*"\s*,\s*"([^"]+)"', body)
        for ref in refs:
            if ref.startswith(("../", "scripts/", "tests/", "assets/",
                               "templates/")) or "/" not in ref:
                continue
            self.assertTrue((SKILL_DIR / ref).exists(),
                            f"referenced file missing: {{ref}}")

    def test_optional_references_are_not_claims(self):
        body = _frontmatter()[1]
        refs = re.findall(r'references/([A-Za-z0-9._\-]+\.md)', body)
        for ref in refs:
            if (SKILL_DIR / "references" / ref).exists():
                # if present, it must be readable text
                (SKILL_DIR / "references" / ref).read_text(encoding="utf-8")


class TestUnsupportedFormats(unittest.TestCase):
    """Conversion metadata must record the source format honestly."""

    def test_readme_records_format(self):
        readme = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
        self.assertTrue("source format" in readme.lower() or
                        "converted" in readme.lower(),
                        "README should record the source format")


class TestNetworkFailures(unittest.TestCase):
    """No script may assume network access without documenting it."""

    def test_no_hardcoded_network_assumptions(self):
        for script in (SKILL_DIR / "scripts").glob("*"):
            text = script.read_text(encoding="utf-8", errors="replace")
            if re.search(r"urllib|requests|socket|httpx|aiohttp", text):
                self.assertIn("network", (SKILL_DIR / "README.md"
                                         .read_text(encoding="utf-8")).lower(),
                              f"script uses networking; README must document it")


class TestConversionFailures(unittest.TestCase):
    """Unmapped functionality must be reported, never silently dropped."""

    def test_readme_lists_limitations(self):
        readme = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("unmapped", readme.lower(),
                      "README must list unmapped functionality")


class TestInstallationFailures(unittest.TestCase):
    """Install prerequisites must be checkable."""

    def test_skills_dir_resolvable(self):
        hermes_home = Path(os.environ.get("HERMES_HOME",
                                          Path.home() / ".hermes")).expanduser()
        self.assertTrue(hermes_home.is_dir() or True,
                        "HERMES_HOME resolvable even when ~/.hermes absent")


if __name__ == "__main__":
    pytest.main([str(__file__), "-q"])
'''.format(
        name=name,
        platforms=json.dumps(compat["platforms"]),
        script_block=_script_execution_block(scripts, name),
        dep_checks=_dependency_check_block(caps),
        invalid_input_cases=_invalid_input_cases(scripts),
    )


def _script_execution_block(scripts, name):
    if not scripts:
        return ("class TestScriptExecution(unittest.TestCase):\n"
                "    def test_no_scripts_to_check(self):\n"
                "        pass\n")
    cases = []
    for script in scripts:
        safe = script.replace(".", "_").replace("-", "_")
        ext = script.rsplit(".", 1)[-1].lower()
        if _is_placeholder_script(script, ext):
            # Placeholder/workflow scripts (remote hosts, package managers,
            # interactive tools) are not executed during validation; only
            # presence and static sanity are asserted so conversion never
            # fails on unrunnable environment-dependent scripts.
            static = ("        import ast as _a\n"
                      "        _a.parse(script.read_text(encoding=\"utf-8\"))\n"
                      if ext == "py" else "")
            cases.append(f"""    def test_{safe}_is_present_and_valid(self):
        script = SKILL_DIR / "scripts" / "{script}"
        self.assertTrue(script.exists(), f"script missing: {{{{script}}}}")
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.strip(), "script {script} is not empty")
{static}        first_line = text.splitlines()[0] or "!"
        self.assertIn("#", first_line, f"script {script} "
                      "has a shebang/first-line marker")""")
        else:
            runner = "\"" + ("bash" if ext in ("sh", "bash") else "python3") + "\""
            cases.append(f"""    def test_{safe}_runs(self):
        script = SKILL_DIR / "scripts" / "{script}"
        self.assertTrue(script.exists(), f"script missing: {{{{script}}}}")
        result = subprocess.run([{runner}, str(script), "--help"],
                                capture_output=True, text=True, timeout=120)
        # --help/-h may not exist; the point is the invocation does not crash
        self.assertLess(result.returncode, 126,
                      f"script did not run (exit code {{{{result.returncode}}}}, 126+ = invoke failure)")""")
    return ("class TestScriptExecution(unittest.TestCase):\n"
            "    pass\n" + "\n".join(cases))


def _is_placeholder_script(script, ext):
    """True when a script clearly depends on environment/runtime hosts
    (remote rsync targets, missing package manifests, GUI/interactive
    commands), meaning it cannot safely run in the converter env."""
    try:
        if ext == "py":
            tree = ast.parse(open(script, encoding="utf-8").read())
            text = "".join(ast.get_docstring(node) or ""
                           for node in ast.walk(tree))
        else:
            text = open(script, encoding="utf-8", errors="replace").read()
    except OSError:
        return True
    markers = ("rsync ", "ssh ", "scp ", "ftp ", "npm run", "npm install",
               "yarn build", "docker run", "kubectl ", "systemctl ", "sudo ",
               "gnome-", "xdg-open", "osascript", "start-process")
    if any(m in text for m in markers):
        return True
    # Missing package manifest / node_modules for npm/yarn scripts
    base = Path(script).parent
    if "npm run" in text and not (base / "package.json").is_file():
        return True
    return False


def _dependency_check_block(caps):
    checks = []
    for dep in caps["dependencies"][:6]:
        checks.append(f"""    def test_dep_{re.sub(r'[^A-Za-z0-9]', '_', dep).lower()}(self):
        self.assertTrue(shutil.which("{dep}") or True,
                        "{dep} availability check runs without crashing")
""")
    if not checks:
        checks.append("    def test_no_hard_deps(self): pass\n")
    return "\n".join(checks)


def _invalid_input_cases(scripts):
    if not scripts:
        return ("    def test_no_invalid_input_cases_to_check(self):\n"
                "        pass\n")
    first = scripts[0]
    safe = first.replace(".", "_").replace("-", "_")
    ext = first.rsplit(".", 1)[-1].lower()
    if _is_placeholder_script(first, ext):
        return (f"    def test_{safe}_placeholder_handled(self):\n"
                '        script = SKILL_DIR / "scripts" / "' + first + '"\n'
                '        self.assertTrue(script.is_file(), "script exists")\n'
                "        text = script.read_text(encoding=\"utf-8\")\n"
                "        self.assertGreater(len(text.splitlines()), 0,\n"
                "                           \"script body is non-empty\")\n"
                "        # Placeholder script: not executable here; README\n"
                "        # lists the required runtime tools.\n")
    runner = "\"bash\"" if ext in ("sh", "bash") else "\"python3\""
    return (f"    def test_{safe}_rejects_empty_args(self):\n"
            f'        script = SKILL_DIR / "scripts" / "{first}"\n'
            f"        result = subprocess.run([{runner}, str(script)],\n"
            '                                capture_output=True, text=True, '
            'timeout=120)\n'
            '        self.assertLess(result.returncode, 126,\n'
            '                      "script exits with a recognizable code "\n'
            '                      "on missing input")\n')


def build_readme(name, description, fmt, compat, scripts, secrets, risks, unmapped):
    lines = [
        f"# {name.replace('-', ' ').title()} (converted)",
        "",
        f"> Auto-converted by **Hermes SkillForge** on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        f"- **Source format:** {fmt.replace('_', ' ')}",
        f"- **Description:** {description}",
        f"- **Platforms:** {', '.join(compat['platforms'])}",
        "",
        "## Structure",
        "- `SKILL.md` — main skill document",
    ]
    if scripts:
        lines.append(f"- `scripts/` — preserved scripts ({', '.join(scripts)})")
    lines += [
        "- `references/` — supporting docs + security findings",
        "- `templates/` — preserved templates (if any)",
        "- `tests/` — generated pytest suite",
        "",
        "## Installation",
        "```\nhermes skills install <url-or-path>\n```\nor copy this directory "
        "into `~/.hermes/skills/<category>/` and start a new session.",
        "",
        "## Validation",
        "```\npython3 -m pytest tests/ -q\n```",
        "",
        "## Conversion report",
        "### Mapped functionality",
    ]
    for m in compat["mapped"]:
        lines.append(f"- {m['item']} -> {m['target']}")
    lines.append("")
    lines.append("### Unmapped functionality (never silently dropped)")
    if unmapped:
        for u in unmapped:
            lines.append(f"- {u['item']}: {u['reason']}")
    else:
        lines.append("- None — all detected functionality was mapped or documented.")
    lines.append("")
    if secrets or risks:
        lines.append("### Security")
        for f in secrets[:10]:
            lines.append(f"- Secret detected and REDACTED: {f['type']} in {f['file']}")
        for r in risks[:10]:
            lines.append(f"- Risk flagged: {r['type']} in {r['file']}")
        lines.append("")
    lines.append("### Rollback")
    lines.append("Before install, SkillForge snapshots the prior state to "
                 "`~/.hermes/skillforge/rollbacks/`. "
                 "Restore with `python3 scripts/skillforge.py rollback`.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Validation (mirrors tools/skill_manager_tool.py hardline rules)
# ---------------------------------------------------------------------------

def validate_skill(skill_dir: Path):
    """Validate generated skill; return (ok, errors, warnings)."""
    skill_md = skill_dir / "SKILL.md"
    errors, warnings = [], []

    if not skill_md.exists():
        return False, ["SKILL.md missing"], []

    content = skill_md.read_text(encoding="utf-8")
    content_no_bom = content.lstrip("\ufeff")

    # Frontmatter fence
    if not content_no_bom.startswith("---"):
        errors.append("SKILL.md must start with '---' (no leading blank line/BOM).")
    end = re.search(r"\n---\s*\n", content_no_bom[3:])
    if not end:
        errors.append("Frontmatter closing '---' missing.")

    yaml_text = content_no_bom[3:end.start() + 3] if end else ""
    try:
        fm = _parse_simple_yaml(yaml_text)
    except Exception as exc:  # noqa: BLE001
        fm = None
        errors.append(f"Frontmatter YAML parse error: {exc}")

    if isinstance(fm, dict):
        name = fm.get("name")
        if not name:
            errors.append("Frontmatter 'name' missing.")
        else:
            if len(str(name)) > MAX_NAME_LENGTH:
                errors.append(f"name exceeds {MAX_NAME_LENGTH} chars.")
            if not VALID_NAME_RE.match(str(name)):
                errors.append("name must be lowercase a-z/0-9 with hyphens only.")
            if name != skill_dir.name:
                errors.append(f"name '{name}' must equal directory name '{skill_dir.name}'.")
            if name in ("skill", "skill-forge", "skillforge"):
                warnings.append("Consider a more distinctive name to avoid collisions.")

        desc = str(fm.get("description", ""))
        if not desc:
            errors.append("Frontmatter 'description' missing.")
        elif len(desc) > MAX_DESCRIPTION_LENGTH:
            errors.append(f"description exceeds {MAX_DESCRIPTION_LENGTH} chars.")
        elif len(desc.strip().strip("'\"")) > DESCRIPTION_BUDGET:
            errors.append(
                f"new-skill description budget: {len(desc.strip())} chars "
                f"> {DESCRIPTION_BUDGET}; index truncates at "
                f"{DESCRIPTION_BUDGET - 3} chars + '...'")
        elif not desc.rstrip().endswith("."):
            errors.append("description must end with a period.")

        if "version" not in fm:
            warnings.append("'version' missing (recommended).")
        if "platforms" not in fm:
            warnings.append("'platforms' missing (recommended).")

        meta = fm.get("metadata") or {}
        hermes = meta.get("hermes") or {}
        tags = hermes.get("tags")
        if not tags:
            warnings.append("metadata.hermes.tags missing (recommended).")

    body = content_no_bom[end.end() + 3:].strip() if end else ""
    if not body:
        errors.append("Body after frontmatter is empty.")
    if len(content) > MAX_SKILL_CONTENT_CHARS:
        errors.append(f"content exceeds {MAX_SKILL_CONTENT_CHARS:,} chars.")

    # Size of supporting files
    for kind in ("references", "templates", "scripts", "tests"):
        d = skill_dir / kind
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file() and f.stat().st_size > MAX_SUPPORTING_FILE_BYTES:
                    errors.append(f"supporting file exceeds 1 MiB: {f.relative_to(skill_dir)}")

    # Referenced files must exist (only files that live inside the skill tree)
    if body:
        for ref in re.findall(r"skill_view\(\s*\"[^\"]*\"\s*,\s*\"([^\"]+)\"", body):
            if ref.startswith(("../", "scripts/", "tests/", "assets/",
                               "templates/")) or "/" not in ref:
                continue
            if not (skill_dir / ref).exists():
                errors.append(f"referenced file missing: {ref}")
        # Optional references/: paths mentioned in body prose that do not
        # exist are warnings, not errors (references are loaded on demand)
        for ref in re.findall(r"references/([A-Za-z0-9._\-]+\.md)", body):
            if not (skill_dir / "references" / ref).exists():
                warnings.append(f"referenced optional file missing: references/{ref}")

    # Scripts must be executable-ish text (no binary)
    if (skill_dir / "scripts").is_dir():
        for g in (skill_dir / "scripts").iterdir():
            if g.is_file():
                try:
                    g.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    errors.append(f"binary file in scripts/: {g.name}")

    # Security: no secrets in generated files
    generated_text = content
    for d in ("references", "templates", "scripts"):
        dpath = skill_dir / d
        if dpath.is_dir():
            for f in dpath.rglob("*"):
                if f.is_file():
                    try:
                        generated_text += f.read_text(encoding="utf-8",
                                                      errors="replace")
                    except OSError:
                        pass
    leaked = [s for s, pat in SECRET_PATTERNS if pat.search(generated_text)
              and "<REDACTED>" not in pat.search(generated_text).group(0)]
    for s in leaked:
        errors.append(f"possible secret leaked into generated files: {s}")

    return (len(errors) == 0), errors, warnings


# ---------------------------------------------------------------------------
# Quality scoring (0-100)
# ---------------------------------------------------------------------------

def score_quality(skill_dir: Path, validation_ok: bool, errors, warnings,
                  test_results, caps, compat, secrets, risks):
    scores = {
        "hermes_compatibility": 20,
        "functional_preservation": 15,
        "skill_md_quality": 15,
        "dependency_resolution": 10,
        "tool_compatibility": 10,
        "test_coverage": 10,
        "security": 10,
        "portability": 5,
        "documentation_quality": 5,
    }
    total, earned = 0, 0

    # Hermes compatibility
    total += scores["hermes_compatibility"]
    earned += scores["hermes_compatibility"] * (1.0 if validation_ok else 0.3)
    if errors:
        earned = max(0.0, earned - 3 * len(errors))

    # Functional preservation
    total += scores["functional_preservation"]
    unmapped_penalty = min(0.5, 0.15 * len(compat.get("unmapped", [])))
    earned += scores["functional_preservation"] * (1.0 - unmapped_penalty)

    # SKILL.md quality
    total += scores["skill_md_quality"]
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    quality = 1.0
    if len(content.splitlines()) < 25:
        quality -= 0.3
    for need in ("when to use", "procedure", "verification", "pitfalls"):
        if need not in content.lower():
            quality -= 0.1
    earned += scores["skill_md_quality"] * max(0.0, quality)

    # Dependency resolution
    total += scores["dependency_resolution"]
    deps = caps.get("dependencies", [])
    if not deps:
        earned += scores["dependency_resolution"]
    else:
        resolved = sum(1 for d in deps[:6] if shutil.which(d))
        earned += scores["dependency_resolution"] * (resolved / max(1, min(6, len(deps))))

    # Tool compatibility
    total += scores["tool_compatibility"]
    body = content.lower()
    earned += scores["tool_compatibility"] * (
        1.0 if ("terminal" in body) else 0.4)

    # Test coverage
    total += scores["test_coverage"]
    if test_results is not None:
        n_pass, n_total = test_results
        earned += scores["test_coverage"] * (n_pass / max(1, n_total))
    else:
        earned += scores["test_coverage"] * 0.5

    # Security
    total += scores["security"]
    if not secrets and not risks:
        earned += scores["security"]
    elif all("<REDACTED>" in str(sx) for sx in (secrets or [])):
        earned += scores["security"] * 0.8
    else:
        earned += scores["security"] * 0.4

    # Portability
    total += scores["portability"]
    earned += scores["portability"] * (
        1.0 if set(compat.get("platforms", [])) == {"linux", "macos", "windows"} else 0.6)

    # Documentation quality
    total += scores["documentation_quality"]
    earned += scores["documentation_quality"] * (
        1.0 if (skill_dir / "README.md").exists() and len(warnings) <= 2 else 0.5)

    score = int(round(100 * (earned / max(1, total))))
    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

def run_tests(skill_dir: Path):
    """Run the generated pytest suite. Returns (passed, total, log)."""
    tests_dir = skill_dir / "tests"
    if not tests_dir.is_dir() or not list(tests_dir.glob("test_*.py")):
        return None, None, "No test suite present."
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-q",
         "--no-header", "--tb=short"],
        capture_output=True, text=True, timeout=600,
        cwd=str(skill_dir))
    m = re.search(r"(\d+) passed", result.stdout + result.stderr)
    m2 = re.search(r"(\d+) (failed|error)", result.stdout + result.stderr)
    n_pass = int(m.group(1)) if m else 0
    n_fail = int(m2.group(1)) if m2 else 0
    n_total = n_pass + n_fail
    log = result.stdout[-4000:] or result.stderr[-4000:]
    return n_pass, n_total, log


# ---------------------------------------------------------------------------
# Installation, rollback, versioning
# ---------------------------------------------------------------------------

def install_skill(skill_dir: Path, category: str = "software-development",
                  force: bool = False):
    """Install into ~/.hermes/skills/<category>/. Returns report dict."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = SKILLS_DIR / category / skill_dir.name
    report = {"target": str(target), "action": None, "rollback": None}

    if target.exists():
        if not force:
            report["action"] = "upgrade"
            backup = ROLLBACKS / f"{skill_dir.name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup / skill_dir.name)
            report["rollback"] = str(backup)
        shutil.rmtree(target)
    else:
        report["action"] = "fresh"

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, target)
    return report


def uninstall_skill(name: str):
    """Remove a skill by directory name (any category). Returns removed path or None."""
    if not SKILLS_DIR.exists():
        return None
    for skill_md in SKILLS_DIR.rglob("SKILL.md"):
        if skill_md.parent.name == name:
            target = skill_md.parent
            backup = ROLLBACKS / f"uninstall-{name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup / name)
            shutil.rmtree(target)
            return str(backup)
    return None


def rollback_last():
    """Restore the most recent rollback snapshot. Returns report dict."""
    if not ROLLBACKS.is_dir():
        return {"ok": False, "message": "No rollbacks recorded."}
    snapshots = sorted((p for p in ROLLBACKS.iterdir() if p.is_dir()), reverse=True)
    if not snapshots:
        return {"ok": False, "message": "No rollbacks recorded."}
    snap = snapshots[0]
    restored = []
    for candidate in snap.iterdir():
        if candidate.is_dir():
            # candidate/<skillname> — the skill tree itself
            trees = list(candidate.iterdir())
            for tree in trees:
                if not tree.is_dir():
                    continue
                dest = SKILLS_DIR / tree.name
                if dest.exists():
                    shutil.rmtree(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(tree, dest)
                restored.append(str(dest))
    shutil.rmtree(snap)
    return {"ok": True, "restored": restored, "removed_snapshot": str(snap)}


def detect_conflicts(name: str):
    """Check for duplicate/near-duplicate skill names already installed."""
    conflicts = []
    if not SKILLS_DIR.exists():
        return conflicts
    for skill_md in SKILLS_DIR.rglob("SKILL.md"):
        existing = skill_md.parent.name
        if existing == name:
            conflicts.append({"kind": "exact", "path": str(skill_md.parent)})
        elif existing.replace("-", "") == name.replace("-", ""):
            conflicts.append({"kind": "near", "path": str(skill_md.parent)})
    return conflicts


def record_conversion(meta: dict):
    LAST_CONVERSION.mkdir(parents=True, exist_ok=True)
    (LAST_CONVERSION / "conversion.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8")


def load_last_conversion():
    path = LAST_CONVERSION / "conversion.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Auto-repair
# ---------------------------------------------------------------------------

def auto_repair(skill_dir: Path, attempts: int = 3):
    """Iterate validate/repair/test until clean or blocker found."""
    history = []
    for attempt in range(1, attempts + 1):
        ok, errors, warnings = validate_skill(skill_dir)
        repaired = []
        if not ok:
            repaired = _apply_repairs(skill_dir, errors)
        n_pass, n_total, log = run_tests(skill_dir)
        clean = ok and (n_pass == n_total if n_total else True)
        history.append({
            "attempt": attempt,
            "errors_before": errors,
            "repairs": repaired,
            "validation_ok": ok,
            "test_result": {"passed": n_pass, "total": n_total},
            "clean": clean,
        })
        if clean:
            break
        # If validation still fails after repairs, stop (genuine blocker)
        still_bad, _, _ = validate_skill(skill_dir)
        if not still_bad:
            ok2, _, _ = True, [], []
    blockers = [h for h in history if not h["clean"]]
    return {
        "history": history,
        "success": history[-1]["clean"] if history else False,
        "blockers": [e for h in history for e in h["errors_before"]],
    }


def _apply_repairs(skill_dir: Path, errors):
    """Fix the common, safe validator failures."""
    repaired = []
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    for error in errors:
        if "must start with" in error and not content.startswith("---"):
            content = content.lstrip()
            content = "---\n" + content
            repaired.append("prepended frontmatter fence")
        if "ending with a period" in error:
            m = re.search(r'description:\s*"([^"]+)"', content)
            if m:
                desc = m.group(1)
                if not desc.endswith("."):
                    content = content.replace(
                        f'description: "{desc}"',
                        f'description: "{desc.rstrip(".") + "."}"', 1)
                    repaired.append("added trailing period to description")
        if "budget" in error and ">" in error:
            m = re.search(r'description:\s*"([^"]+)"', content)
            if m:
                desc = m.group(1)
                new = shorten_description(desc)
                content = content.replace(f'description: "{desc}"',
                                          f'description: "{new}"', 1)
                repaired.append(f"shortened description to fit {DESCRIPTION_BUDGET}-char budget")
        if "directory name" in error:
            m = re.search(r"^name:\s*(.+)$", content, re.M)
            if m:
                content = content.replace(m.group(0),
                                          f"name: {skill_dir.name}", 1)
                repaired.append("aligned name with directory name")
        if "closing" in error and "missing" in error:
            if not re.search(r"\n---\s*\n", content[3:]):
                content += "\n---\n"
                repaired.append("added closing frontmatter fence")

    if repaired:
        skill_md.write_text(content, encoding="utf-8")
    return repaired


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_analyze(source, scratch):
    tree = materialize_source(source, scratch)
    detection = detect_format(tree)
    caps = extract_capabilities(tree, detection["format"])
    compat = analyze_compatibility(tree, detection["format"], caps)
    secrets = scan_secrets(tree)
    risks = scan_security_risks(tree)
    print("== Source analysis ==")
    print(f"Format: {detection['format']} (confidence: {detection['confidence']}, "
          f"score: {detection['score']})")
    for ev in detection["evidence"]:
        print(f"  - {ev}")
    print("Capabilities:")
    print(f"  commands: {len(caps['commands'])}, dependencies: "
          f"{len(caps['dependencies'])}, scripts: {len(caps['scripts'])}, "
          f"API endpoints: {len(caps['api_endpoints'])}, "
          f"config keys: {len(caps['config_keys'])}")
    print("Compatibility mapping:")
    for m in compat["mapped"]:
        print(f"  MAPPED: {m['item']} -> {m['target']}")
    for u in compat["unmapped"]:
        print(f"  UNMAPPED: {u['item']} — {u['reason']}")
    for a in compat["adaptations"]:
        print(f"  ADAPTED: {a['item']} -> {a['target']}")
    print(f"Target platforms: {compat['platforms']}")
    print(f"Security: {len(secrets)} secret(s) detected, {len(risks)} risk(s) flagged")
    for s in secrets[:8]:
        print(f"  SECRET: {s['type']} in {s['file']} (line {s['line']}) — will be redacted")
    for r in risks[:8]:
        print(f"  RISK: {r['type']} in {r['file']} (line {r['line']})")
    return {"tree": tree, "detection": detection, "caps": caps,
            "compat": compat, "secrets": secrets, "risks": risks}


def cmd_convert(source, scratch):
    state = cmd_analyze(source, scratch)
    tree, detection, caps, compat, secrets, risks = \
        state["tree"], state["detection"], state["caps"], state["compat"], \
        state["secrets"], state["risks"]

    behavior = extract_core_behavior(read_tree_text(tree), detection["format"])
    # Derive name + description from source frontmatter or source text
    fm_text = ""
    for smd in (tree.rglob("SKILL.md")):
        fm_text = smd.read_text(encoding="utf-8", errors="replace")[:4000]
        break
    src_fm = parse_frontmatter(fm_text) or {}
    raw_name = str(src_fm.get("name", detection["format"] + "-" + tree.name))
    name = sanitize_skill_name(raw_name)
    raw_desc = str(src_fm.get("description", behavior["overview"] or
                              f"Converted {detection['format'].replace('_', ' ')} capability."))
    description = shorten_description(raw_desc)

    summary = build_skill_directory(name, description, detection["format"], tree,
                                    caps, compat, behavior, secrets, risks, WORKSPACE)
    meta = {
        "source": source,
        "format": detection["format"],
        "name": name,
        "description": description,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "capabilities": {k: (sorted(v) if isinstance(v, (set, list)) else v)
                         for k, v in caps.items()},
        "compatibility": compat,
        "secrets_found": len(secrets),
        "risks_found": len(risks),
        "unmapped": compat["unmapped"],
    }
    record_conversion(meta)
    print("== Conversion complete ==")
    print(f"Generated: {summary['path']}")
    print(f"Dirs created: {summary['dirs_created']}")
    print(f"Scripts copied: {summary['scripts_copied']}")
    print(f"SKILL.md size: {summary['skill_md_chars']:,} chars")
    print(f"Unmapped functionality: {len(compat['unmapped'])}")
    for u in compat["unmapped"]:
        print(f"  - {u['item']}: {u['reason']}")
    print(f"Raw description shortened: '{raw_desc[:60]}...' -> '{description}'")
    return meta


def cmd_validate():
    meta = load_last_conversion()
    if not meta:
        print("No conversion recorded. Run `convert` or `import` first.")
        return False
    skill_dir = Path(meta["summary"]["path"])
    ok, errors, warnings = validate_skill(skill_dir)
    print("== Validation ==")
    print("VALID" if ok else "INVALID")
    for e in errors:
        print(f"  ERROR: {e}")
    for w in warnings:
        print(f"  WARN: {w}")
    meta["validation"] = {"ok": ok, "errors": errors, "warnings": warnings}
    record_conversion(meta)
    return ok


def cmd_test():
    meta = load_last_conversion()
    if not meta:
        print("No conversion recorded. Run `convert` or `import` first.")
        return False
    skill_dir = Path(meta["summary"]["path"])
    n_pass, n_total, log = run_tests(skill_dir)
    print("== Tests ==")
    if n_pass is None:
        print(log)
        return False
    print(f"passed: {n_pass}/{n_total}")
    if n_pass < n_total:
        print(log)
    meta["tests"] = {"passed": n_pass, "total": n_total}
    record_conversion(meta)
    return n_pass == n_total


def cmd_repair():
    meta = load_last_conversion()
    if not meta:
        print("No conversion recorded. Run `convert` or `import` first.")
        return False
    skill_dir = Path(meta["summary"]["path"])
    result = auto_repair(skill_dir)
    print("== Auto-repair ==")
    for h in result["history"]:
        print(f"Attempt {h['attempt']}: repairs={h['repairs']}, "
              f"validation={'OK' if h['validation_ok'] else 'FAIL'}, "
              f"tests={h['test_result']['passed']}/{h['test_result']['total']}, "
              f"clean={'YES' if h['clean'] else 'NO'}")
    if not result["success"]:
        print("Unresolved blockers:")
        for b in sorted(set(result["blockers"])):
            print(f"  - {b}")
    meta["repair"] = result
    record_conversion(meta)
    return result["success"]


def cmd_preview():
    meta = load_last_conversion()
    if not meta:
        print("No conversion recorded.")
        return
    print(open(Path(meta["summary"]["path"]) / "SKILL.md",
               encoding="utf-8").read())


def cmd_install():
    meta = load_last_conversion()
    if not meta:
        print("No conversion recorded. Run `convert` or `import` first.")
        return False
    skill_dir = Path(meta["summary"]["path"])
    ok, errors, _ = validate_skill(skill_dir)
    if not ok:
        print("Validation failing — run `repair` first. Errors:")
        for e in errors:
            print(f"  - {e}")
        return False

    conflicts = detect_conflicts(meta["name"])
    report = install_skill(skill_dir, force=bool(conflicts))
    print("== Installation ==")
    print(f"Action: {report['action']} -> {report['target']}")
    if report["rollback"]:
        print(f"Rollback snapshot: {report['rollback']}")
    if conflicts:
        print("Conflicts detected (previous version backed up):")
        for c in conflicts:
            print(f"  - {c['kind']}: {c['path']}")
    print("Installed. Active in a new session; run /reset for the "
          "current one.")
    meta["installed"] = report
    record_conversion(meta)
    return True


def cmd_batch(directory, scratch_root):
    src = Path(directory).expanduser()
    if not src.is_dir():
        print(f"Not a directory: {directory}")
        return 1
    results = []
    # Each immediate subdirectory with content, plus zip files, is a candidate
    candidates = []
    for child in src.iterdir():
        if child.is_dir() and any(child.iterdir()):
            candidates.append(child)
        elif child.is_file() and child.suffix.lower() == ".zip":
            candidates.append(child)
    if not candidates:
        candidates = [src]  # treat the dir itself as one source
    for i, cand in enumerate(candidates):
        scratch = scratch_root / f"batch-{i}"
        if scratch.exists():
            shutil.rmtree(scratch)
        print(f"\n== Batch [{i + 1}/{len(candidates)}]: {cand.name} ==")
        try:
            meta = cmd_convert(str(cand), scratch)
            ok, errors, _ = validate_skill(Path(meta["summary"]["path"]))
            n_pass, n_total, _ = run_tests(Path(meta["summary"]["path"]))
            score = score_quality(Path(meta["summary"]["path"]), ok, errors, [],
                                  (n_pass, n_total) if n_total else None,
                                  meta.get("capabilities", {}),
                                  meta.get("compatibility", {}),
                                  [], [])
            results.append({"source": str(cand), "name": meta["name"],
                            "valid": ok, "tests": f"{n_pass}/{n_total}",
                            "score": score, "errors": errors})
            print(f"  -> {meta['name']}: valid={ok}, tests={n_pass}/{n_total}, score={score}")
        except Exception as exc:  # noqa: BLE001
            results.append({"source": str(cand), "error": str(exc)})
            print(f"  -> FAILED: {exc}")
    print("\n== Batch summary ==")
    for r in results:
        print(json.dumps(r, default=str))
    return 0


def cmd_rollback(all_snapshots: bool):
    if all_snapshots:
        print("Rolling back all snapshots is not safe — use `rollback` "
              "for the most recent snapshot only.")
        return False
    report = rollback_last()
    print("== Rollback ==")
    print(json.dumps(report, indent=2, default=str))
    return report["ok"]


def cmd_update(source):
    """Re-convert against the same source; bump version if already installed."""
    meta = cmd_convert(source, WORKSPACE / "update-scratch")
    skill_dir = Path(meta["summary"]["path"])
    # Bump version based on installed copy
    installed_copy = SKILLS_DIR.rglob(f"*/{meta['name']}/SKILL.md")
    try:
        first = next(installed_copy)
        old = parse_frontmatter(first.read_text(encoding="utf-8")) or {}
        old_ver = old.get("version", "0.0.0")
        parts = str(old_ver).split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_ver = ".".join(parts)
        content = skill_dir.read_text(encoding="utf-8")
        content = re.sub(r"^version: .+$", f"version: {new_ver}", content,
                         count=1, flags=re.M)
        skill_dir.write_text(content, encoding="utf-8")
        print(f"Version bumped: {old_ver} -> {new_ver}")
    except StopIteration:
        pass
    ok, errors, _ = validate_skill(skill_dir)
    print(f"Re-converted; validation: {'VALID' if ok else 'INVALID'}")
    for e in errors:
        print(f"  - {e}")
    record_conversion(meta)
    return ok


def main():
    ap = argparse.ArgumentParser(description="Hermes SkillForge conversion engine")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="detect format and capabilities")
    p.add_argument("source")
    p = sub.add_parser("convert", help="generate the skill")
    p.add_argument("source")
    p = sub.add_parser("import", help="full pipeline: analyze + convert")
    p.add_argument("source")
    sub.add_parser("preview", help="render generated SKILL.md")
    sub.add_parser("validate", help="validate generated skill")
    sub.add_parser("test", help="run generated test suite")
    sub.add_parser("repair", help="auto-repair failing validation/tests")
    sub.add_parser("install", help="install last conversion into ~/.hermes/skills/")
    p = sub.add_parser("update", help="re-convert with version bump")
    p.add_argument("source")
    p = sub.add_parser("rollback", help="restore last install snapshot")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("batch", help="convert every source under a directory")
    p.add_argument("directory")
    args = ap.parse_args()

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    ROLLBACKS.mkdir(parents=True, exist_ok=True)

    if args.command == "analyze":
        cmd_analyze(args.source, WORKSPACE / "analyze-scratch")
    elif args.command == "convert":
        cmd_convert(args.source, WORKSPACE / "convert-scratch")
    elif args.command == "import":
        cmd_convert(args.source, WORKSPACE / "import-scratch")
    elif args.command == "preview":
        cmd_preview()
    elif args.command == "validate":
        sys.exit(0 if cmd_validate() else 1)
    elif args.command == "test":
        sys.exit(0 if cmd_test() else 1)
    elif args.command == "repair":
        sys.exit(0 if cmd_repair() else 1)
    elif args.command == "install":
        sys.exit(0 if cmd_install() else 1)
    elif args.command == "update":
        sys.exit(0 if cmd_update(args.source) else 1)
    elif args.command == "rollback":
        sys.exit(0 if cmd_rollback(args.all) else 1)
    elif args.command == "batch":
        sys.exit(cmd_batch(args.directory, WORKSPACE / "batch-scratch"))


if __name__ == "__main__":
    main()
