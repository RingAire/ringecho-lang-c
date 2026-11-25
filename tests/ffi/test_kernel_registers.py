"""General-register policy must prevent optimizer-introduced FP/SIMD copies."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'), 'register policy verification requires LLVM')
class KernelRegisterTests(unittest.TestCase):
    def build_object(self, source, target, policy, root):
        path, obj = root / 'probe.reo', root / 'probe.o'
        path.write_text(source, encoding='utf-8')
        env = {**os.environ, 'TMP': str(root), 'TEMP': str(root), 'TMPDIR': str(root), 'REO_KEEP_C': '0'}
        if policy is None:
            env.pop('REO_KERNEL_REGISTER_POLICY', None)
        else:
            env['REO_KERNEL_REGISTER_POLICY'] = policy
        result = subprocess.run([str(semantics.COMPILER), 'build', str(path), '--kernel', '--kernel-target', target,
            '--kernel-cc', shutil.which('clang'), '--emit', 'obj', '-o', str(obj)], env=env, cwd=root,
            text=True, capture_output=True, timeout=60)
        return result, obj

    def test_integer_union_copy_uses_no_fp_simd_by_default(self):
        source = 'union Word { integer: u64, bytes: [u8; 8] } extern { fn transform(value: Word) -> Word; } fn probe(value: Word) -> u64 { let result = transform(value); return result.integer; }'
        for target in ('i686-unknown-none-elf', 'x86_64-unknown-none-elf', 'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='reo general registers ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                result, obj = self.build_object(source, target, None, root)
                self.assertEqual(result.returncode, 0, result.stderr)
                dumped = subprocess.run([shutil.which('llvm-objdump'), '-d', str(obj)], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertEqual(dumped.returncode, 0, dumped.stderr)
                instructions = '\n'.join(line.split('\t', 1)[1] for line in dumped.stdout.splitlines() if '\t' in line)
                if target.startswith(('i686', 'x86_64')):
                    self.assertNotRegex(instructions, r'%(?:xmm|ymm|zmm|mm)[0-9]|\bst\([0-7]\)')
                elif target.startswith('aarch64'):
                    self.assertNotRegex(instructions, r'\b(?:v|q|d|s)[0-9]+\b')
                else:
                    self.assertNotRegex(instructions, r'\b(?:q|d|s)[0-9]+\b')

    def test_full_policy_preserves_explicit_float_support(self):
        with tempfile.TemporaryDirectory(prefix='reo full registers ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            source = 'fn probe(value: f64) -> f64 { return value + 1.0; }'
            result, obj = self.build_object(source, 'x86_64-unknown-none-elf', 'full', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            dumped = subprocess.run([shutil.which('llvm-objdump'), '-d', str(obj)], cwd=root, text=True, capture_output=True, timeout=30)
            self.assertEqual(dumped.returncode, 0, dumped.stderr)
            self.assertIn('xmm', dumped.stdout)

    @unittest.skipUnless(shutil.which('llvm-nm'), 'undefined-symbol verification requires llvm-nm')
    def test_large_union_copy_needs_no_host_memory_helpers(self):
        source = 'union Large { integer: u64, bytes: [u8; 257] } extern { fn transform(value: Large) -> Large; } fn probe(value: Large) -> u64 { let result = transform(value); return result.integer; }'
        for target in ('i686-unknown-none-elf', 'x86_64-unknown-none-elf', 'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='reo large union copy ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                result, obj = self.build_object(source, target, None, root)
                self.assertEqual(result.returncode, 0, result.stderr)
                dumped = subprocess.run([shutil.which('llvm-nm'), '--undefined-only', str(obj)], cwd=root,
                    text=True, capture_output=True, timeout=30)
                self.assertEqual(dumped.returncode, 0, dumped.stderr)
                allowed = {'transform', '__reo_kernel_abort', '__reo_kernel_diagnostic',
                           '__reo_kernel_depth_enter', '__reo_kernel_depth_leave'}
                self.assertEqual([line for line in dumped.stdout.splitlines() if line.split()[-1] not in allowed], [], dumped.stdout)

    def test_invalid_policy_warns_and_falls_back(self):
        with tempfile.TemporaryDirectory(prefix='reo invalid register policy ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            result, _ = self.build_object('fn probe(value: u64) -> u64 { return value + 1u64; }',
                'i686-unknown-none-elf', 'invalid-policy', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('invalid REO_KERNEL_REGISTER_POLICY; using default general', result.stderr)


if __name__ == '__main__':
    unittest.main()
