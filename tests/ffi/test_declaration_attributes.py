"""Declaration validation, ELF metadata, weak linking and image literals."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]
COMPILER = semantics.COMPILER
SOURCE = """
@section(".boot.header")
@used
static boot: [u32; 3] = [464367618u32, 0u32, 3830599678u32];
@weak
@section(".text.hook")
fn kernel_hook() -> u32 { return 7u32; }
fn call_hook() -> u32 { return kernel_hook(); }
@used
@section(".text.retained")
fn unused_fn() -> u32 { return 23u32; }
"""


class DeclarationTests(unittest.TestCase):
    def command(self, args, root, **kwargs):
        return subprocess.run([str(a) for a in args], cwd=root, text=True,
                              capture_output=True, timeout=60, **kwargs)

    def generated(self, source=SOURCE):
        stderr, generated = semantics.KernelSemanticsTests().generated(source, "x86_64-unknown-none-elf")
        self.assertIsNotNone(generated, stderr)
        return generated

    def test_invalid_attributes_are_rejected(self):
        cases = [
            '@section("") fn f() {}', '@section(.bad) fn f() {}',
            '@section(123) fn f() {}', '@section("x\\ntext") fn f() {}',
            '@section("x\\\"text") fn f() {}', '@section("x,aw") fn f() {}',
            '@section("' + 'x' * 128 + '") fn f() {}',
            '@section(".a") @section(".b") fn f() {}',
            '@used @used fn f() {}', '@weak @weak fn f() {}',
            '@used(1) fn f() {}', '@used() fn f() {}', '@weak("yes") fn f() {}',
            '@weak static x: u32;', '@section(".x") struct S { value: u32 }',
            '@used let x = 1;', '@section(".x") extern { fn f(); }',
            '@used fn f<T>(x: T) -> T { return x; }',
            'fn f() { @section(".x") static local: u32; }',
        ]
        with tempfile.TemporaryDirectory(prefix="reo attribute errors ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            for i, source in enumerate(cases):
                with self.subTest(source=source):
                    path = root / f"invalid{i}.reo"
                    path.write_text(source, encoding="utf-8")
                    result = self.command([COMPILER, "check", path], root)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_backend_does_not_ignore_attributes(self):
        with tempfile.TemporaryDirectory(prefix="reo native attributes ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.reo"
            path.write_text('@used fn main() {}', encoding="utf-8")
            for flags in (["--backend", "native", "--emit", "obj"], ["--target", "reo"]):
                result = self.command([COMPILER, "build", path, *flags, "-o", root / "probe.out"], root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("attributes are not supported", result.stderr)

    def test_kernel_dynamic_initializer_fails_explicitly(self):
        stderr, generated = semantics.KernelSemanticsTests().generated(
            'fn value() -> i64 { return 9; } static x: i64 = value(); fn probe() {}')
        self.assertIn("initialize this object explicitly at startup", stderr)
        self.assertIsNone(generated)

    def test_definition_metadata_and_static_literals_survive_codegen(self):
        generated = self.generated()
        self.assertIn('__REO_SECTION(".boot.header", "__DATA", "boot_header"), used', generated)
        self.assertIn('__REO_SECTION(".text.hook", "__TEXT", "text_hook"), weak', generated)
        self.assertNotIn('__reo_globals_ctor', generated)
        self.assertIn('.data = {', generated)

    @unittest.skipUnless(shutil.which("clang") and shutil.which("llvm-objdump") and shutil.which("llvm-nm"), "ELF verification requires LLVM tools")
    def test_sections_and_weak_bindings_on_four_targets(self):
        with tempfile.TemporaryDirectory(prefix="reo ELF attributes ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.c"
            path.write_text(self.generated(), encoding="utf-8")
            for target in ("i686-unknown-none-elf", "x86_64-unknown-none-elf", "aarch64-unknown-none-elf", "armv7-unknown-none-eabi"):
                with self.subTest(target=target):
                    obj = root / (target + ".o")
                    result = self.command([shutil.which("clang"), "--target=" + target, "-ffreestanding", "-O2", "-Werror", "-fno-builtin", "-c", path, "-o", obj], root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = self.command([shutil.which("llvm-objdump"), "-h", obj], root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    for section in (".boot.header", ".text.hook", ".text.retained"):
                        self.assertIn(section, result.stdout)
                    result = self.command([shutil.which("llvm-nm"), obj], root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertRegex(result.stdout, r"\bW kernel_hook\b")
                    self.assertIn("unused_fn", result.stdout)

    @unittest.skipUnless(shutil.which("clang"), "weak override test requires a host C compiler")
    def test_strong_definition_overrides_weak_and_literals_are_initialized(self):
        with tempfile.TemporaryDirectory(prefix="reo weak override ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.c"
            source = SOURCE + """
            struct Packet { tag: u8, values: [u16; 2] }
            static packet: Packet = Packet { tag: 5u8, values: [11u16, 19u16] };
            """
            path.write_text(self.generated(source) +
                'int main(void) { return call_hook() == 91 && boot.data[0] == 464367618u && packet.tag == 5 && packet.values.data[1] == 19 ? 0 : 1; }', encoding="utf-8")
            strong = root / "strong.c"
            strong.write_text('unsigned kernel_hook(void) { return 91; }', encoding="utf-8")
            output = root / ("probe.exe" if os.name == "nt" else "probe")
            result = self.command([shutil.which("clang"), "-O2", "-fno-builtin", "-Werror", path, strong, "-o", output], root)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.command([output], root)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("clang") and shutil.which("ld.lld") and shutil.which("llvm-nm"), "KEEP verification requires LLVM ELF tools")
    def test_used_emission_does_not_replace_linker_keep(self):
        with tempfile.TemporaryDirectory(prefix="reo section KEEP ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.c"
            path.write_text(self.generated(), encoding="utf-8")
            obj = root / "probe.o"
            result = self.command([shutil.which("clang"), "--target=x86_64-unknown-none-elf", "-O2", "-ffreestanding", "-fno-builtin", "-fno-pic", "-ffunction-sections", "-fdata-sections", "-c", path, "-o", obj], root)
            self.assertEqual(result.returncode, 0, result.stderr)
            for keep in (False, True):
                script = root / "probe.ld"
                retained = '.retained : { KEEP(*(.text.retained)) } .header : { KEEP(*(.boot.header)) }' if keep else ''
                script.write_text('ENTRY(call_hook) SECTIONS { . = 0x100000; ' + retained + ' .text : { *(.text*) } .data : { *(.boot.header) *(.data*) } .bss : { *(.bss*) } }', encoding="utf-8")
                output = root / "probe.elf"
                result = self.command([shutil.which("ld.lld"), "--gc-sections", "-T", script, obj, "-o", output], root)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = self.command([shutil.which("llvm-nm"), output], root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual("unused_fn" in result.stdout, keep, result.stdout)
                self.assertEqual(" boot\n" in result.stdout, keep, result.stdout)


if __name__ == "__main__":
    unittest.main()
