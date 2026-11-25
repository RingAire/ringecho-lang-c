"""Windows must not resolve toolchain programs through the current directory.

A cloned project can ship `gcc.exe`/`clang.exe`; the compiler used to launch the
bare name with CreateProcessA, which searches the working directory first.
The test drops a fake compiler next to the source and requires the build to use
the real one from PATH.
"""

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
CC = shutil.which("gcc") or shutil.which("clang")


@unittest.skipUnless(os.name == "nt", "current-directory search only applies on Windows")
@unittest.skipUnless(CC, "no host C compiler on PATH")
@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class ProcessSearchPathTests(unittest.TestCase):
    def test_working_directory_compiler_is_ignored(self):
        with tempfile.TemporaryDirectory(prefix="reo process path ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            name = Path(CC).name
            fake = root / name
            if not name.lower().endswith(".exe"):
                fake = root / (name + ".exe")
            shutil.copyfile(COMPILER, fake)

            source = root / "hello.reo"
            source.write_text('fn main() { println("ok"); }\n', encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary,
                   "REO_CC": Path(name).stem, "REO_KEEP_C": "0"}
            build = subprocess.run(
                [str(COMPILER), "build", str(source), "-o", str(root / "out.exe")],
                cwd=root, env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertTrue((root / "out.exe").is_file())

            run = subprocess.run([str(root / "out.exe")], cwd=root,
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
