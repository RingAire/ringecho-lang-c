"""Compare REO-folded layout queries against target C compile-time assertions."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]
DECLARATIONS = '''
struct Mixed { byte: u8, integer: u64, real: f64, pointer: ptr }
@repr(packed)
struct Packed { byte: u8, integer: u64, pointer: ptr }
@align(16)
struct Aligned { byte: u8, integer: u64 }
struct Nested { first: u8, values: [Mixed; 2], end: u16 }
enum Event { Empty, Value(u64) }
'''


@unittest.skipUnless(shutil.which("clang"), "target layout comparison requires clang")
class KernelLayoutTests(unittest.TestCase):
    def test_scalar_and_aggregate_queries_match_target_c(self):
        queries = []
        for reo, c in [('u64', 'uint64_t'), ('i64', 'int64_t'), ('f64', 'double'),
                       ('usize', 'uintptr_t'), ('isize', 'intptr_t'), ('ptr', 'void *'),
                       ('Mixed', 'Mixed'), ('Packed', 'Packed'), ('Aligned', 'Aligned'),
                       ('Nested', 'Nested'), ('Event', 'Event')]:
            queries += [(f'sizeof<{reo}>()', f'sizeof({c})'), (f'alignof<{reo}>()', f'_Alignof({c})')]
        for record, fields in [('Mixed', ['integer', 'real', 'pointer']), ('Packed', ['integer', 'pointer']),
                               ('Nested', ['values', 'end'])]:
            queries += [(f'offsetof<{record}>("{field}")', f'offsetof({record}, {field})') for field in fields]
        for target in ('i386-unknown-none-elf', 'i686-unknown-none-elf', 'x86_64-unknown-none-elf',
                       'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix="reo target layout ", dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                source = DECLARATIONS + '\n'.join(f'fn query_{i}() -> usize {{ return {reo}; }}' for i, (reo, _) in enumerate(queries))
                stderr, generated = semantics.KernelSemanticsTests().generated(source, target)
                self.assertIsNotNone(generated, stderr)
                assertions = []
                for i, (_, c) in enumerate(queries):
                    match = re.search(r'uintptr_t query_' + str(i) + r'\(void\)\s*\{.*?return\s+\(\(uintptr_t\)(\d+)LL\)', generated, re.S)
                    self.assertIsNotNone(match, f'folded query_{i} missing: {generated[-5000:]}')
                    assertions.append(f'_Static_assert({c} == {match.group(1)}, "query {i}: {c}");')
                path = root / 'probe.c'
                path.write_text(generated + '\n' + '\n'.join(assertions), encoding='utf-8')
                result = subprocess.run([shutil.which('clang'), '--target=' + target, '-O2', '-ffreestanding',
                    '-fno-builtin', '-Werror', '-c', str(path), '-o', str(root / 'probe.o')],
                    cwd=root, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
