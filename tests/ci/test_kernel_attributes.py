"""Kernel-facing declaration attributes: alignment, exported symbols, noreturn."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()
CC = os.environ.get("REO_TEST_CC") or shutil.which("clang") or shutil.which("gcc")


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
@unittest.skipUnless(CC, "host C compiler required")
class KernelAttributeTests(unittest.TestCase):
    def test_alignment_export_names_and_noreturn_reach_generated_c(self):
        with tempfile.TemporaryDirectory(prefix="reo kernel attrs ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = ROOT / "tests" / "kernel_attributes.reo"
            output = root / ("probe.exe" if os.name == "nt" else "probe")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(source), "-o", str(output)],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            self.assertIn("aligned(64)", text)
            self.assertIn("aligned(16)", text)
            self.assertIn("noreturn", text)
            self.assertIn("reo_alias", text)
            self.assertGreaterEqual(text.count("reo_alias("), 2)
            self.assertGreaterEqual(text.count("exported("), 2)

            probe = root / "align_probe.c"
            probe.write_text(text + "\n_Static_assert(__alignof__(table) == 64, \"table alignment\");\n",
                             encoding="utf-8")
            compile_result = subprocess.run([CC, "-O2", "-pthread", "-Wno-unused-value",
                                             str(probe), "-o", str(root / "align-probe")],
                                            cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            run = subprocess.run([str(root / "align-probe")], cwd=root,
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
