"""Implicit numeric conversions use the selected target, never host width."""
import unittest
from pathlib import Path
import subprocess
import tempfile
import test_kernel_semantics as semantics


class TargetConversionTests(unittest.TestCase):
    def check_conversion(self, source, target, accepted):
        stderr, generated = semantics.KernelSemanticsTests().generated(source, target)
        if accepted:
            self.assertIsNotNone(generated, stderr)
            self.assertIn('kernel compilation of generated C failed', stderr)
        else:
            self.assertIsNone(generated, stderr)
            self.assertNotIn('kernel compilation of generated C failed', stderr)
            self.assertIn('error:', stderr)

    def test_integer_width_checks_follow_all_supported_kernel_targets(self):
        for target, narrow in [('i386-unknown-none-elf', True), ('i686-unknown-none-elf', True),
                               ('armv7-unknown-none-eabi', True), ('x86_64-unknown-none-elf', False),
                               ('aarch64-unknown-none-elf', False)]:
            for source, accepted in [
                ('fn probe(value: u64) -> usize { return value; }', not narrow),
                ('fn probe(value: usize) -> u32 { return value; }', narrow),
                ('fn probe(value: u32) -> isize { return value; }', not narrow),
                ('fn probe(value: isize) -> i32 { return value; }', narrow),
                ('fn probe(value: usize) -> f64 { return value; }', narrow),
            ]:
                with self.subTest(target=target, source=source):
                    self.check_conversion(source, target, accepted)

    def test_target_width_enforced_at_assignments_fields_calls_and_statics(self):
        sources = [
            'fn probe(value: u64) { let local: usize = value; }',
            'fn probe(value: u64) { let local: usize = 0; local = value; }',
            'struct S { size: usize } fn probe(value: u64) { let s = S { size: value }; }',
            'fn consume(value: usize) {} fn probe(value: u64) { consume(value); }',
            'static wide: u64 = 1u64; static size: usize = wide; fn probe() {}',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.check_conversion(source, 'i686-unknown-none-elf', False)

    def test_only_full_integer_zero_is_a_null_pointer_constant(self):
        for value, accepted in [('0', True), ('18446744073709551616', False),
                                ('340282366920938463444927863358058659840', False)]:
            with self.subTest(value=value):
                self.check_conversion(f'fn probe() -> *mut u8 {{ return {value}; }}',
                                      'x86_64-unknown-none-elf', accepted)

    def test_native_lowering_agrees_with_target_semantics(self):
        targets = [('i686-unknown-linux-gnu', True), ('i686-pc-windows-msvc', True),
                   ('armv7-unknown-linux-gnueabihf', True), ('x86_64-unknown-linux-gnu', False),
                   ('aarch64-unknown-linux-gnu', False), ('x86_64-pc-windows-msvc', False)]
        with tempfile.TemporaryDirectory(prefix='reo native coercion ', dir=semantics.ROOT / 'target') as temporary:
            root = Path(temporary)
            for target, narrow in targets:
                for source, accepted in [
                    ('fn probe(value: usize) -> u32 { return value; }', narrow),
                    ('fn probe(value: u64) -> usize { return value; }', not narrow),
                ]:
                    with self.subTest(target=target, source=source):
                        path, obj = root / 'probe.reo', root / 'probe.o'
                        path.write_text(source, encoding='utf-8')
                        obj.unlink(missing_ok=True)
                        result = subprocess.run([str(semantics.COMPILER), 'build', str(path), '--backend', 'native',
                            '--target', target, '--emit', 'obj', '-o', str(obj)], cwd=root,
                            text=True, capture_output=True, timeout=30)
                        self.assertEqual(result.returncode == 0, accepted, result.stdout + result.stderr)
                        self.assertEqual(obj.exists(), accepted)


if __name__ == '__main__':
    unittest.main()
