"""Kernel build cleanup on success, compilation/assembly/link failures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('clang') and shutil.which('ld.lld'), 'kernel build verification requires clang/lld')
class KernelBuildTests(unittest.TestCase):
    def test_option_and_response_file_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='reo build input rejection ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path = root / 'probe.reo'
            path.write_text('fn probe() {}', encoding='utf-8')
            for option, value in [('--object', '@options'), ('--object', '-Tscript'), ('--asm', '@options')]:
                result = subprocess.run([str(semantics.COMPILER), 'build', str(path), '--kernel', option, value, '-o', str(root / 'probe.elf')], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing value for --object' if value.startswith('-') else 'invalid kernel input path', result.stderr)

    def test_invalid_optimization_reports_fallback(self):
        with tempfile.TemporaryDirectory(prefix='reo opt fallback ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path, script = root / 'probe.reo', root / 'probe.ld'
            path.write_text('fn probe() {}', encoding='utf-8')
            script.write_text('ENTRY(probe) SECTIONS { . = 0x100000; .text : { *(.text*) } }', encoding='utf-8')
            env = {**os.environ, 'TMP': temporary, 'TEMP': temporary, 'TMPDIR': temporary,
                   'REO_KEEP_C': '0', 'REO_KERNEL_OPT': '-fplugin=untrusted', 'REO_KERNEL_LD': shutil.which('ld.lld')}
            result = subprocess.run([str(semantics.COMPILER), 'build', str(path), '--kernel', '--kernel-target', 'i686-unknown-none-elf', '--kernel-cc', shutil.which('clang'), '--linker-script', str(script), '-o', str(root / 'probe.elf')], env=env, cwd=root, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('invalid REO_KERNEL_OPT; using default -O2', result.stderr)

    def test_temporary_objects_are_cleaned_on_every_exit(self):
        for stage in ('success', 'compile', 'assembly', 'link'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix='reo build cleanup ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                path = root / 'probe.reo'
                path.write_text('fn probe() { println(1); }' if stage == 'compile' else 'fn probe() {}', encoding='utf-8')
                script = root / 'probe.ld'
                script.write_text('invalid linker script' if stage == 'link' else 'ENTRY(probe) SECTIONS { . = 0x100000; .text : { *(.text*) } .data : { *(.data*) } .bss : { *(.bss*) } }', encoding='utf-8')
                env = {**os.environ, 'TMP': temporary, 'TEMP': temporary, 'TMPDIR': temporary,
                       'REO_KERNEL_TARGET': 'i686-unknown-none-elf', 'REO_KERNEL_CC': shutil.which('clang'),
                       'REO_KERNEL_LD': shutil.which('ld.lld')}
                env['REO_KEEP_C'] = '0'
                args = [str(semantics.COMPILER), 'build', str(path), '--kernel', '--linker-script', str(script), '-o', str(root / 'probe.elf')]
                if stage == 'assembly':
                    args += ['--asm', str(root / 'missing.S')]
                result = subprocess.run(args, cwd=root, env=env, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode == 0, stage == 'success', result.stdout + result.stderr)
                self.assertEqual(list(root.rglob('*.o')), [], str(list(root.rglob('*'))))
                self.assertEqual(list(root.rglob('*.c')), [], str(list(root.rglob('*'))))

    def test_keep_c_preserves_requested_intermediates(self):
        with tempfile.TemporaryDirectory(prefix='reo keep build ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path = root / 'probe.reo'
            path.write_text('fn probe() {}', encoding='utf-8')
            env = {**os.environ, 'TMP': temporary, 'TEMP': temporary, 'TMPDIR': temporary,
                   'REO_KEEP_C': '1', 'REO_KERNEL_TARGET': 'i686-unknown-none-elf',
                   'REO_KERNEL_LD': 'reo-nonexistent-linker', 'REO_KERNEL_OPT': '-O2'}
            result = subprocess.run([str(semantics.COMPILER), 'build', str(path), '--kernel', '--kernel-cc', shutil.which('clang'), '-o', str(root / 'probe.elf')], cwd=root, env=env, text=True, capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(list(root.rglob('*.c')), result.stderr)
            self.assertTrue(list(root.rglob('*.o')), result.stderr)


if __name__ == '__main__':
    unittest.main()
