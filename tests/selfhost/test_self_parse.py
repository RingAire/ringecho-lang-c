"""The REO frontend parses every compiler-reo module (syntax self-consumption)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" /
                               ("rev.exe" if os.name == "nt" else "rev"))).resolve()


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class SelfParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="reo self parse ", dir=ROOT / "target")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.executable = cls.root / ("frontend.exe" if os.name == "nt" else "frontend")
        env = {**os.environ, "TMP": str(cls.root), "TEMP": str(cls.root),
               "TMPDIR": str(cls.root), "REO_KEEP_C": "1"}
        result = subprocess.run([str(COMPILER), "build", str(ROOT / "compiler-reo/frontend.reo"),
                                 "-o", str(cls.executable)], env=env, cwd=ROOT,
                                text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def test_every_frontend_module_parses(self):
        modules = sorted((ROOT / "compiler-reo").glob("*.reo"))
        self.assertTrue(modules)
        for module in modules:
            result = subprocess.run([str(self.executable), "--parse", os.path.relpath(module, ROOT)],
                                    cwd=ROOT, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0,
                             f"{module.name}: {result.stdout}{result.stderr}")
            self.assertIn("ok", result.stdout)

    def test_at_does_not_match_string_contents(self):
        """`at(")")` must look at the token kind, not the string's contents."""
        source = self.root / "probe.reo"
        source.write_text('fn f() {\n    if at(")") { return; }\n}\n', encoding="utf-8")
        result = subprocess.run([str(self.executable), "--parse", os.path.relpath(source, ROOT)],
                                cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
