"""Hosted GC regressions: root registration must not corrupt object memory.

`gc_add_root` stores an arbitrary object pointer. The generated runtime used to
reinterpret that pointer as a GC node while marking, touching memory at the
node-field offset (a heap overflow for small allocations). This test generates
the hosted C, compiles it with AddressSanitizer and runs it.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = Path(os.environ.get(
    "REO_TEST_COMPILER", ROOT / "target" / "Release" / ("rev.exe" if os.name == "nt" else "rev")
)).resolve()
CC = os.environ.get("REO_TEST_CC") or shutil.which("clang") or shutil.which("gcc")

SOURCE = """
@gc(auto)
fn main() {
    let raw: ptr = alloc(3usize);
    gc_add_root(raw);
    gc_collect();
    free(raw);
    let text: str = str_concat("a", "b");
    gc_add_root(text as ptr);
    gc_collect();
    println(str_len(text));
    gc_release(text as ptr);
}
"""


@unittest.skipUnless(CC, "generated-C execution requires a host C compiler")
class GcRootTests(unittest.TestCase):
    def sanitizer_available(self, root: Path) -> bool:
        probe = root / "asan-probe.c"
        probe.write_text("int main(void) { return 0; }\n", encoding="utf-8")
        result = subprocess.run([CC, "-fsanitize=address", str(probe), "-o", str(root / "asan-probe")],
                                cwd=root, capture_output=True, text=True, timeout=90)
        return result.returncode == 0

    def test_gc_add_root_does_not_corrupt_small_allocations(self):
        with tempfile.TemporaryDirectory(prefix="reo gc roots ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            if not self.sanitizer_available(root):
                self.skipTest("host compiler cannot build with AddressSanitizer")

            source = root / "probe.reo"
            source.write_text(SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            build = subprocess.run([str(COMPILER), "build", str(source), "-o", str(root / "probe.exe")],
                                   env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)

            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            binary = root / ("probe-asan.exe" if os.name == "nt" else "probe-asan")
            compile_result = subprocess.run(
                [CC, "-fsanitize=address", "-g", "-pthread",
                 str(generated[0]), "-o", str(binary)],
                cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)

            run = subprocess.run([str(binary)], cwd=root, capture_output=True, text=True, timeout=60)
            output = (run.stdout or "") + (run.stderr or "")
            self.assertEqual(run.returncode, 0, output)
            self.assertNotIn("AddressSanitizer", output)
            self.assertIn("2", run.stdout)


if __name__ == "__main__":
    unittest.main()
