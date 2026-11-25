"""@thread_local statics lower to C11 _Thread_local; the kernel rejects them."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()
SOURCE = ROOT / "tests" / "thread_local.reo"


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class ThreadLocalTests(unittest.TestCase):
    def test_hosted_static_emits_thread_local(self):
        with tempfile.TemporaryDirectory(prefix="reo tls ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(SOURCE),
                                    "-o", str(root / "probe.exe")],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            text = next(root.rglob("re0_codegen_*.c")).read_text(encoding="utf-8")
            self.assertIn("static _Thread_local int64_t counter", text)

    def test_kernel_profile_rejects_thread_local(self):
        with tempfile.TemporaryDirectory(prefix="reo tls kernel ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary}
            build = subprocess.run([str(COMPILER), "build", str(SOURCE), "--kernel",
                                    "--kernel-cc", str(root / "missing-compiler"),
                                    "-o", str(root / "probe.elf")],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            output = build.stdout + build.stderr
            self.assertNotEqual(build.returncode, 0, output)
            self.assertIn("kernel profile has no TLS setup", output)


if __name__ == "__main__":
    unittest.main()
