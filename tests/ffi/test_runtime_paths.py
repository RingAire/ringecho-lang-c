"""Hosted runtime path guards: directory APIs must use the same rules as files."""

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

CASES = {
    "dir_open_absolute": 'fn main() { let d = dir_open("/"); println(dir_next(d)); }',
    "path_isdir_absolute": 'fn main() { println(path_isdir("/")); }',
}


@unittest.skipUnless(CC, "generated-C execution requires a host C compiler")
@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class RuntimePathTests(unittest.TestCase):
    def run_hosted(self, source: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="reo runtime path ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.reo"
            path.write_text(source, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(path), "-o", str(root / "probe.exe")],
                                   cwd=root, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            binary = root / ("probe-bin.exe" if os.name == "nt" else "probe-bin")
            compile_result = subprocess.run([CC, "-O2", "-pthread", str(generated[0]), "-o", str(binary)],
                                            cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            return subprocess.run([str(binary)], cwd=root, capture_output=True, text=True, timeout=60)

    @unittest.skipUnless(os.name == "nt", "alternate data streams are Windows-only")
    def test_windows_alternate_data_stream_is_rejected(self):
        result = self.run_hosted('fn main() { let s = file_read("a:b"); println(str_len(s)); }')
        output = (result.stdout or "") + (result.stderr or "")
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("invalid path", output)

    def test_absolute_paths_abort_in_directory_apis(self):
        for name, source in CASES.items():
            with self.subTest(name=name):
                result = self.run_hosted(source)
                output = (result.stdout or "") + (result.stderr or "")
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("invalid path", output)


if __name__ == "__main__":
    unittest.main()
