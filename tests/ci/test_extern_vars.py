"""External variables (linker symbols) parse, type-check and emit a declaration."""

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

SOURCE = """
extern {
    static linker_symbol: u8;
}

fn main() {
    println("ok");
}
"""


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class ExternVarTests(unittest.TestCase):
    def test_extern_variable_emits_declaration_and_links(self):
        with tempfile.TemporaryDirectory(prefix="reo extern vars ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(source), "-o", str(root / "probe.exe")],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            # The linker cannot resolve the symbol yet; the generated C must exist.
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C: " + build.stderr)
            text = generated[0].read_text(encoding="utf-8")
            self.assertIn("extern uint8_t linker_symbol;", text)

            definition = root / "def.c"
            definition.write_text("#include <stdint.h>\nuint8_t linker_symbol = 0;\n", encoding="utf-8")
            binary = root / ("probe-bin.exe" if os.name == "nt" else "probe-bin")
            compile_result = subprocess.run([CC or "cc", "-O2", "-pthread", str(generated[0]),
                                             str(definition), "-o", str(binary)],
                                            cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            run = subprocess.run([str(binary)], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ok", run.stdout)

    def test_duplicate_extern_variable_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="reo extern dup ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text("extern {\n    static s: u8;\n    static s: u8;\n}\nfn main() {}\n",
                              encoding="utf-8")
            result = subprocess.run([str(COMPILER), "check", str(source)],
                                    cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("duplicate external variable", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
