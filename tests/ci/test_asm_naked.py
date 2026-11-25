"""unsafe blocks, asm templates and @naked lower to the expected C."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class AsmNakedTests(unittest.TestCase):
    def test_unsafe_asm_and_naked_reach_generated_c(self):
        with tempfile.TemporaryDirectory(prefix="reo asm naked ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = ROOT / "tests" / "unsafe_asm.reo"
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(source), "-o", str(root / "probe.exe")],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            self.assertIn("__attribute__((naked))", text)
            self.assertIn('__asm__ __volatile__("ret")', text)
            self.assertIn('__asm__ __volatile__("")', text)
            naked_body = text.split("void naked_stub", 1)[1].split("}", 1)[0]
            self.assertNotIn("__REO_DEPTH_GUARD", naked_body)


if __name__ == "__main__":
    unittest.main()
