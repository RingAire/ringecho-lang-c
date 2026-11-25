"""Host capabilities for self-hosting: files, environment and argv spawn."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()

PROGRAM = "cmd.exe" if os.name == "nt" else "/bin/sh"
C_FLAG = "/c" if os.name == "nt" else "-c"

SOURCE = f"""
fn main() {{
    file_write("a.txt", "x");
    assert(file_exists("a.txt"));
    assert(file_rename("a.txt", "b.txt"));
    assert(file_exists("b.txt"));
    assert(file_remove("b.txt"));
    assert(!file_exists("b.txt"));
    assert(dir_create("d"));
    assert(getenv("PATH") != "");

    let args = svec_new();
    svec_push(args, "{C_FLAG}");
    svec_push(args, "exit 7");
    let rc = proc_spawn("{PROGRAM}", args);
    svec_free(args);
    assert(rc == 7i32);
    println("ok");
}}
"""


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class HostCapabilityTests(unittest.TestCase):
    def test_files_environment_and_spawn(self):
        with tempfile.TemporaryDirectory(prefix="reo host caps ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary}
            result = subprocess.run([str(COMPILER), "run", str(source)],
                                    env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
