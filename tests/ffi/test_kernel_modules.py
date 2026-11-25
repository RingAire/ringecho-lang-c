"""Separate REO kernel objects and cross-module calls through the target C ABI."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('clang') and shutil.which('ld.lld') and shutil.which('llvm-nm'), 'module verification requires LLVM')
class KernelModuleTests(unittest.TestCase):
    def command(self, root, env, *args):
        return subprocess.run([str(semantics.COMPILER), 'build', *map(str, args)], cwd=root, env=env, text=True, capture_output=True, timeout=60)

    def test_separate_modules_link_on_four_targets(self):
        for target in ('i686-unknown-none-elf', 'x86_64-unknown-none-elf', 'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='reo separate modules ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                env = {**os.environ, 'TMP': temporary, 'TEMP': temporary, 'TMPDIR': temporary, 'REO_KEEP_C': '0',
                       'REO_KERNEL_CC': shutil.which('clang'), 'REO_KERNEL_LD': shutil.which('ld.lld')}
                a, b = root / 'arithmetic_module.reo', root / 'entry_module.reo'
                record = 'struct Record { tag: u32, count: u64 } '
                a.write_text(record + 'fn module_add(a: u32, b: u32) -> u32 { return a + b; } fn module_roundtrip(value: Record) -> Record { return Record { tag: value.tag + 1u32, count: value.count + 3u64 }; }', encoding='utf-8')
                b.write_text(record + 'extern { fn module_add(a: u32, b: u32) -> u32; fn module_roundtrip(value: Record) -> Record; } fn probe() -> u32 { let input = Record { tag: 10u32, count: 28u64 }; let result = module_roundtrip(input); return module_add(result.tag, result.count as u32); }', encoding='utf-8')
                obj = root / 'arithmetic_module.o'
                result = self.command(root, env, a, '--kernel', '--kernel-target', target, '--emit', 'obj', '-o', obj)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([shutil.which('llvm-nm'), str(obj)], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertRegex(result.stdout, r'\bT module_add\b')
                script = root / 'module.ld'
                script.write_text('ENTRY(probe) SECTIONS { . = 0x100000; .text : { *(.text*) } .data : { *(.data*) } .bss : { *(.bss*) } }', encoding='utf-8')
                output = root / 'modules.elf'
                result = self.command(root, env, b, '--kernel', '--kernel-target', target, '--object', obj, '--linker-script', script, '-o', output)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([shutil.which('llvm-nm'), str(output)], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                for symbol in ('module_add', 'module_roundtrip', 'probe'):
                    self.assertRegex(result.stdout, r'\bT ' + symbol + r'\b')
                self.assertNotIn(' U module_add', result.stdout)

    def test_object_mode_rejects_final_link_inputs(self):
        with tempfile.TemporaryDirectory(prefix='reo object mode errors ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            source = root / 'probe.reo'
            source.write_text('fn probe() {}', encoding='utf-8')
            for option in ('--asm', '--object', '--linker-script'):
                result = self.command(root, os.environ.copy(), source, '--kernel', '--emit', 'obj', option, 'unused-input', '-o', root / 'probe.o')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('belong to the final link', result.stderr)


if __name__ == '__main__':
    unittest.main()
