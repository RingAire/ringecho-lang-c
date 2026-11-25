"""Kernel port I/O, privileged instructions and @interrupt reach generated C."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()

SOURCE = """
@interrupt
fn timer_isr(frame: *mut u8) {
    let p = frame;
    outb(0x20u16, 0x20u8);
    p = p;
}

fn main() {
    let idt: [u32; 2] = [0u32; 2];
    load_idt(0u16, (&idt[0]) as ptr);
    outb(0x3F8u16, 0x41u8);
    outw(0x3F8u16, 0x4142u16);
    outl(0x3F8u16, 0x41424344u32);
    let a = inb(0x3F8u16);
    let b = inw(0x3F8u16);
    let c = inl(0x3F8u16);
    a = a + 1u8;
    b = b + 1u16;
    c = c + 1u32;
    cli();
    sti();
    hlt();
    halt_forever();
}
"""


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class KernelIoTests(unittest.TestCase):
    def test_io_and_interrupt_attributes_reach_generated_c(self):
        with tempfile.TemporaryDirectory(prefix="reo kernel io ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(SOURCE, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            subprocess.run([str(COMPILER), "build", str(source), "--kernel",
                            "--kernel-cc", str(root / "missing-compiler"),
                            "-o", str(root / "probe.elf")],
                           env=env, cwd=root, capture_output=True, text=True, timeout=120)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            for symbol in ("__reo_inb", "__reo_inw", "__reo_inl",
                           "__reo_outb", "__reo_outw", "__reo_outl",
                           "__reo_cli", "__reo_sti", "__reo_hlt", "__reo_halt_forever",
                           "__reo_load_idt"):
                self.assertIn(symbol, text)
            self.assertIn("__attribute__((interrupt))", text)
            self.assertIn('__asm__ __volatile__("inb %1, %0"', text)


if __name__ == "__main__":
    unittest.main()
