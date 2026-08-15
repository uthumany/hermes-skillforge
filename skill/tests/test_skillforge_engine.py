"""Tests for the SkillForge conversion engine itself.

Run: python3 -m pytest tests/ -q
Stdlib + pytest only; no network required.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ENGINE = SKILL_DIR / "scripts" / "skillforge.py"


def run_engine(args, env_extra=None):
    env = os.environ.copy()
    env.setdefault("HERMES_HOME", str(SKILL_DIR.parent / "_hermes_home"))
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(ENGINE)] + args, capture_output=True,
        text=True, timeout=120, env=env)


def _load_engine():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sf", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestEngineCLI(unittest.TestCase):
    """The engine script must be invocable with every documented subcommand."""

    def test_help_lists_subcommands(self):
        result = run_engine(["--help"])
        self.assertEqual(result.returncode, 0)
        for cmd in ("analyze", "convert", "import", "preview", "validate",
                    "test", "repair", "install", "update", "rollback", "batch"):
            self.assertIn(cmd, result.stdout, f"subcommand missing: {cmd}")


class TestNameSanitization(unittest.TestCase):
    def test_sanitizes_names(self):
        mod = _load_engine()
        cases = {
            "My Cool Skill!": "my-cool-skill",
            "UPPER_case": "upper-case",
            "a---b": "a-b",
            "-leading": "leading",
            "trailing-": "trailing",
            "tool (v2)": "tool-v2",
            "": "converted-skill",
        }
        for raw, expected in cases.items():
            self.assertEqual(mod.sanitize_skill_name(raw), expected)

    def test_description_shortening(self):
        mod = _load_engine()
        long_desc = "This is a very long description that definitely exceeds sixty characters easily"
        short = mod.shorten_description(long_desc)
        self.assertLessEqual(len(short), 60)
        self.assertTrue(short.endswith("."))
        # In-budget descriptions pass through with a period
        self.assertEqual(mod.shorten_description("Short desc"), "Short desc.")


class TestFormatDetection(unittest.TestCase):
    def test_detects_agent_skill(self):
        mod = _load_engine()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: \"An example skill.\"\n---\n# Example\n",
                encoding="utf-8")
            (src / "scripts").mkdir()
            (src / "scripts" / "do_thing.sh").write_text("#!/bin/sh\necho hi\n",
                                                         encoding="utf-8")
            det = mod.detect_format(src)
            self.assertEqual(det["format"], "agent_skills")

    def test_detects_plugin_repo(self):
        mod = _load_engine()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)
            (src / "plugin.yaml").write_text("name: x\n", encoding="utf-8")
            det = mod.detect_format(src)
            self.assertEqual(det["format"], "plugin_repo")

    def test_detects_hermes_skill(self):
        mod = _load_engine()
        det = mod.detect_format(SKILL_DIR)
        self.assertEqual(det["format"], "hermes_skill")


class TestSecretRedaction(unittest.TestCase):
    def test_redacts_api_key(self):
        mod = _load_engine()
        text = 'api_key = "SK_TEST_FIXTURE_KEY_REDACT_ME_0123456789AB"'
        redacted = mod.strip_secrets_from_text(text)
        self.assertNotIn("SK_TEST_FIXTURE_KEY_REDACT_ME", redacted)
        self.assertIn("REDACTED", redacted)


class TestValidatorOnSelf(unittest.TestCase):
    """The engine's validator must pass on its own SKILL.md."""

    def test_self_validates(self):
        mod = _load_engine()
        ok, errors, warnings = mod.validate_skill(SKILL_DIR)
        self.assertTrue(ok, errors)


class TestEndToEndPipeline(unittest.TestCase):
    """Full pipeline on a tiny synthetic source must validate and test green."""

    def test_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            scratch = Path(d)
            src = scratch / "src"
            src.mkdir()
            (src / "README.md").write_text(
                "# Deploy Helper\n\n## Procedure\n1. Build with npm run build.\n"
                "2. Copy dist/ to the server with rsync.\n3. Verify healthcheck.\n",
                encoding="utf-8")
            (src / "deploy.sh").write_text(
                "#!/bin/sh\nset -e\nnpm run build\nrsync -a dist/ server:/var/www/\n",
                encoding="utf-8")
            result = run_engine(["convert", str(src)],
                                env_extra={"HERMES_HOME": str(scratch)})
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = (scratch / "skillforge" / "last_conversion" / "conversion.json")
            self.assertTrue(meta.exists())
            ok_result = run_engine(["validate"], env_extra={"HERMES_HOME": str(scratch)})
            self.assertIn("VALID", ok_result.stdout, ok_result.stdout)
            t_result = run_engine(["test"], env_extra={"HERMES_HOME": str(scratch)})
            self.assertIn("passed", t_result.stdout, t_result.stdout)
            r_result = run_engine(["repair"], env_extra={"HERMES_HOME": str(scratch)})
            self.assertIn("clean=YES", r_result.stdout, r_result.stdout)


class TestSecurityQuarantine(unittest.TestCase):
    def test_secret_file_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            scratch = Path(d)
            src = scratch / "src"
            src.mkdir()
            (src / "config.json").write_text(
                '{"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}\n',
                encoding="utf-8")
            (src / "README.md").write_text("# Secret tool\n", encoding="utf-8")
            result = run_engine(["analyze", str(src)],
                                env_extra={"HERMES_HOME": str(scratch)})
            self.assertEqual(result.returncode, 0)
            self.assertIn("SECRET", result.stdout)


if __name__ == "__main__":
    pytest.main([str(__file__), "-q"])


class TestBanner(unittest.TestCase):
    """Responsive banner: tier selection, color fallbacks, CLI flags."""

    def setUp(self):
        self.script = str(SKILL_DIR / "scripts" / "banner.py")
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("TERM", "COLORTERM", "TERM_PROGRAM", "NO_COLOR")}
        self.env["TERM"] = "xterm-256color"
        self.env["COLORTERM"] = "truecolor"

    def _meta(self, width, color_env=None):
        env = dict(self.env)
        if color_env:
            env.update(color_env)
        out = subprocess.run([sys.executable, self.script, "--json", "--width", str(width)],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, msg=(out.stdout + out.stderr))
        return json.loads(out.stdout)

    def test_full_block_tier(self):
        meta = self._meta(100)
        self.assertEqual(meta["tier"], "block")
        self.assertEqual(meta["line_count"], 15)

    def test_compact_block_tier(self):
        meta = self._meta(70)
        self.assertEqual(meta["tier"], "block4")

    def test_thin_tier(self):
        meta = self._meta(45)
        self.assertEqual(meta["tier"], "thin")

    def test_minimal_tier(self):
        meta = self._meta(30)
        self.assertEqual(meta["tier"], "minimal")
        self.assertEqual(meta["line_count"], 1)

    def test_truecolor_mode(self):
        meta = self._meta(80)
        self.assertEqual(meta["color_mode"], "truecolor")

    def test_256color_fallback(self):
        meta = self._meta(80, color_env={"COLORTERM": "", "TERM": "vt100"})
        self.assertEqual(meta["color_mode"], "ansi256")

    def test_mono_no_color(self):
        meta = self._meta(80, color_env={"NO_COLOR": "1"})
        self.assertEqual(meta["color_mode"], "mono")

    def test_rendered_width_within_limit(self):
        meta = self._meta(120)
        self.assertLessEqual(meta["rendered_width"], meta["width"])

    def test_cli_via_skillforge(self):
        engine = str(SKILL_DIR / "scripts" / "skillforge.py")
        out = subprocess.run([sys.executable, engine, "banner", "--json", "--width", "90"],
                             capture_output=True, text=True, env=self.env,
                             cwd=str(SKILL_DIR / "scripts"))
        self.assertEqual(out.returncode, 0, msg=out.stderr)
        meta = json.loads(out.stdout)
        self.assertIn(meta["tier"], ("block", "block4"))

    def test_gradient_uses_green_and_blue(self):
        out = subprocess.run([sys.executable, self.script, "--width", "100"],
                             capture_output=True, text=True, env=self.env)
        text = out.stdout
        colors = [tuple(int(x) for x in c.split(";"))
                  for c in re.findall(r"38;2;(\d{1,3};\d{1,3};\d{1,3})m", text)]
        self.assertGreater(len(colors), 2)
        r0, g0, b0 = colors[0]
        self.assertGreater(g0, r0 + 100)  # greenish start
        rb, gb, bb = colors[-1]
        self.assertGreater(bb, rb + 150)  # blueish end
        self.assertLess(abs(rb - 56), 6)
        self.assertLess(abs(bb - 248), 10)
