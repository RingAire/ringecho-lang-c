"""Privileged x86 register builtins and stderr output."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()

KERNEL_SOURCE = """
fn main() {
    let c = read_cr3();
    write_cr3(c);
    let c0 = read_cr0();
    write_cr0(c0);
    let m = rdmsr(0x1B0u32);
    wrmsr(0x1B0u32, m);
    let x: u32 = 0u32;
    invlpg((&x) as ptr);
    let t = read_tsc();
    t = t + 1u64;
    int3();
    pause();
    eprintln("kernel");
}
"""

STDERR_SOURCE = """
fn main() {
    eprintln("err-line");
    eprint("tail");
    println("out");
}
"""


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class PrivilegedBuiltinTests(unittest.TestCase):
    def test_privileged_builtins_reach_kernel_c(self):
        with tempfile.TemporaryDirectory(prefix="reo priv ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(KERNEL_SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            subprocess.run([str(COMPILER), "build", str(source), "--kernel",
                            "--kernel-cc", str(root / "missing-compiler"),
                            "-o", str(root / "probe.elf")],
                           env=env, cwd=root, capture_output=True, text=True, timeout=120)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            for symbol in ("__reo_read_cr0", "__reo_read_cr2", "__reo_read_cr3",
                           "__reo_write_cr0", "__reo_write_cr3",
                           "__reo_rdmsr", "__reo_wrmsr", "__reo_invlpg",
                           "__reo_read_tsc", "__reo_int3", "__reo_pause"):
                self.assertIn(symbol, text)
            self.assertIn('__asm__ __volatile__("rdmsr"', text)
            self.assertIn("__reo_kernel_diagnostic", text)

    def test_stderr_builtins_write_to_stderr(self):
        with tempfile.TemporaryDirectory(prefix="reo stderr ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(STDERR_SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary}
            result = subprocess.run([str(COMPILER), "run", str(source)],
                                    env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("err-line", result.stderr)
            self.assertIn("tail", result.stderr)
            self.assertIn("out", result.stdout)
            self.assertNotIn("err-line", result.stdout)


if __name__ == "__main__":
    unittest.main()
