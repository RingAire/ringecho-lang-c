"""GC mode behavior on the host platform (Windows, Linux, macOS)."""

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
class GcModeTests(unittest.TestCase):
    def run_source(self, source: str) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="reo gc mode ", dir=ROOT / "target") as temporary:
            path = Path(temporary) / "probe.reo"
            path.write_text(source, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary}
            result = subprocess.run([str(COMPILER), "run", str(path)],
                                    env=env, cwd=temporary, capture_output=True,
                                    text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def test_manual_release_reclaims_the_string(self):
        output = self.run_source("""
@gc(manual)
fn main() {
    let s = str_concat("a", "b");
    println(gc_stats());
    gc_release(s as ptr);
    println(gc_stats());
}
""")
        self.assertEqual(output[-2:], ["1", "0"])

    def test_none_mode_does_not_track_strings(self):
        output = self.run_source("""
fn main() {
    let s = str_concat("a", "b");
    println(gc_stats());
    println(str_len(s));
}
""")
        self.assertEqual(output[-2:], ["0", "2"])


if __name__ == "__main__":
    unittest.main()
