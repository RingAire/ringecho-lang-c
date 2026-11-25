"""Enum @repr and field @align reach the generated C layout."""

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
class LayoutAttributeTests(unittest.TestCase):
    def compile_generated(self, source_path: Path, extra: str = ""):
        temporary = tempfile.TemporaryDirectory(prefix="reo layout attrs ", dir=ROOT / "target")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        env = {**os.environ, "TMP": temporary.name, "TEMP": temporary.name,
               "TMPDIR": temporary.name, "REO_KEEP_C": "1"}
        subprocess.run([str(COMPILER), "build", str(source_path), "-o", str(root / "probe.exe")],
                       env=env, cwd=root, capture_output=True, text=True, timeout=120)
        generated = list(root.rglob("re0_codegen_*.c"))
        self.assertTrue(generated, "compiler kept no generated C")
        text = generated[0].read_text(encoding="utf-8")
        probe = root / "layout_probe.c"
        probe.write_text(text + "\n" + extra, encoding="utf-8")
        binary = root / ("layout-probe.exe" if os.name == "nt" else "layout-probe")
        result = subprocess.run([CC, "-O2", "-pthread", "-Wno-unused-value",
                                 str(probe), "-o", str(binary)],
                                cwd=root, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return text

    def test_enum_repr_is_a_plain_integer_typedef(self):
        text = self.compile_generated(ROOT / "tests" / "enum_repr.reo")
        self.assertIn("typedef uint8_t Small;", text)
        self.assertIn("typedef int Plain;", text)
        self.assertNotIn("payload:Small", text)

    def test_field_alignment_matches_c(self):
        text = self.compile_generated(
            ROOT / "tests" / "field_align.reo",
            '_Static_assert(sizeof(struct Mixed) == 16, "size");\n'
            '_Static_assert(offsetof(struct Mixed, b) == 4, "offset");\n')
        self.assertIn("aligned(16)", text)


if __name__ == "__main__":
    unittest.main()
