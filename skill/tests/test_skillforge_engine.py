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
