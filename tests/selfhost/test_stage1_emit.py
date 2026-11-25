"""REO's own frontend emits C that a host compiler can build and run."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" /
                               ("rev.exe" if os.name == "nt" else "rev"))).resolve()
CC = os.environ.get("REO_TEST_CC") or shutil.which("clang") or shutil.which("gcc")


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
@unittest.skipUnless(CC, "host C compiler required")
class Stage1EmitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="reo stage1 ", dir=ROOT / "target")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.frontend = cls.root / ("frontend.exe" if os.name == "nt" else "frontend")
        env = {**os.environ, "TMP": str(cls.root), "TEMP": str(cls.root),
               "TMPDIR": str(cls.root), "REO_KEEP_C": "1"}
        result = subprocess.run([str(COMPILER), "build", str(ROOT / "compiler-reo/frontend.reo"),
                                 "-o", str(cls.frontend)], env=env, cwd=ROOT,
                                text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def emit_and_run(self, source_name: str, output_name: str, expected: str):
        c_file = self.root / f"{output_name}.c"
        binary = self.root / output_name
        relative_c = os.path.relpath(c_file, ROOT)
        result = subprocess.run([str(self.frontend), "--emit-c",
                                 f"tests/stage1/{source_name}", relative_c],
                                cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        compiled = subprocess.run([CC, str(c_file), "-o", str(binary)],
                                  cwd=ROOT, text=True, capture_output=True, timeout=120)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        run = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(run.stdout.strip(), expected)

    def test_functions_and_arithmetic(self):
        self.emit_and_run("simple.reo", "simple-stage1", "5")

    def test_while_and_compound_assignment(self):
        self.emit_and_run("loop.reo", "loop-stage1", "6")


if __name__ == "__main__":
    unittest.main()
