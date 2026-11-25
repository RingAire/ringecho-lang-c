"""Untagged unions: target layout, image literals, active members and FFI."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_arithmetic as arithmetic
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]
DECLARATIONS = '''
struct Payload { tag: u8, count: u64 }
union Word { integer: u64, bytes: [u8; 8], payload: Payload }
@repr(packed)
union Packed { bytes: [u8; 3], integer: u32 }
@align(32)
union Aligned { integer: u64, bytes: [u8; 8] }
union Nested { word: Word, wide: [u32; 8] }
'''


class UnionTests(unittest.TestCase):
    def generated(self, source, target='x86_64-unknown-none-elf'):
        stderr, generated = semantics.KernelSemanticsTests().generated(source, target)
        self.assertIsNotNone(generated, stderr)
        return generated

    def test_invalid_declarations_and_initializers_fail(self):
        cases = ['union Empty {} fn probe() {}', 'union Bad { x: u32, x: u64 } fn probe() {}',
                 '@repr(transparent) union Bad { x: u32 } fn probe() {}',
                 'union Bad<T> { x: T } fn probe() {}', 'union Bad { x: Bad } fn probe() {}',
                 'union Bad { x: Missing } fn probe() {}',
                 'union Word { x: u32, y: u64 } fn probe() { let w = Word {}; }',
                 'union Word { x: u32, y: u64 } fn probe() { let w = Word { x: 1u32, y: 2u64 }; }',
                 'union Word { x: u32, y: u64 } type Alias = Word; fn probe() { let w = Alias { x: 1u32, y: 2u64 }; }',
                 'union Word { x: u32 } fn probe() { let w = Word { bad: 1u32 }; }',
                 'union Word { x: u32 } fn probe() { let w = Word { x: true }; }']
        with tempfile.TemporaryDirectory(prefix='reo invalid union ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            for source in cases:
                with self.subTest(source=source):
                    path = root / 'probe.reo'
                    path.write_text(source, encoding='utf-8')
                    result = subprocess.run([str(semantics.COMPILER), 'check', str(path)], cwd=root,
                        text=True, capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(arithmetic.CC, 'active member execution requires a C compiler')
    def test_active_members_nested_values_and_static_literals(self):
        source = DECLARATIONS + '''
        static image: Word = Word { integer: 91u64 };
        fn probe() -> i32 {
            let word = Word { integer: 7u64 };
            assert(word.integer == 7u64);
            word.integer += 3u64;
            assert(word.integer == 10u64);
            word = Word { bytes: [1u8,2u8,3u8,4u8,5u8,6u8,7u8,8u8] };
            assert(word.bytes[7] == 8u8);
            word = Word { payload: Payload { tag: 5u8, count: 77u64 } };
            assert(word.payload.count == 77u64);
            let nested = Nested { word: word };
            assert(nested.word.payload.tag == 5u8);
            assert(image.integer == 91u64);
            return 0i32;
        }
        '''
        generated = self.generated(source)
        self.assertIn('typedef union Word Word;', generated)
        self.assertNotIn('__reo_globals_ctor', generated)
        arithmetic.KernelArithmeticTests().compile_run(generated, 'int main(void) { return probe(); }', sanitizer=True)

    @unittest.skipUnless(arithmetic.CC, 'FFI execution requires a C compiler')
    def test_c_and_reo_exchange_union_arguments_and_returns(self):
        source = DECLARATIONS + '''
        union Scalar { real: f64, integer: u64 }
        extern { fn c_word(value: Word) -> Word; fn c_scalar(value: Scalar) -> Scalar; }
        fn reo_word(value: Word) -> Word { return Word { integer: value.integer + 3u64 }; }
        fn reo_scalar(value: Scalar) -> Scalar { return Scalar { real: value.real + 2.0 }; }
        fn probe() -> i32 {
            let input = Word { integer: 91u64 };
            let output = c_word(input);
            assert(output.integer == 98u64);
            let real_input = Scalar { real: 3.5 };
            let real_output = c_scalar(real_input);
            assert(real_output.real == 4.5);
            return 0i32;
        }
        '''
        harness = '''
        #include <stdint.h>
        #include <stdlib.h>
        typedef struct Payload { uint8_t tag; uint64_t count; } Payload;
        typedef union Word { uint64_t integer; uint8_t bytes[8]; Payload payload; } Word;
        typedef union Scalar { double real; uint64_t integer; } Scalar;
        extern Word reo_word(Word);
        extern Scalar reo_scalar(Scalar);
        extern int32_t probe(void);
        _Noreturn void __reo_kernel_abort(void) { _Exit(86); }
        Word c_word(Word value) { return (Word){ .integer = value.integer + 7 }; }
        Scalar c_scalar(Scalar value) { return (Scalar){ .real = value.real + 1.0 }; }
        int main(void) {
            Word input = { .integer = 11 }, output = reo_word(input);
            Scalar scalar = { .real = 4.5 }, result = reo_scalar(scalar);
            return output.integer != 14 || result.real != 6.5 || probe();
        }
        '''
        # Separate translation units, no LTO: neither side can fold away the
        # actual cross-language parameter/return ABI at call sites.
        with tempfile.TemporaryDirectory(prefix='reo union FFI ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path, foreign = root / 'probe.c', root / 'foreign.c'
            path.write_text(self.generated(source), encoding='utf-8')
            foreign.write_text(harness, encoding='utf-8')
            output = root / ('probe.exe' if os.name == 'nt' else 'probe')
            result = subprocess.run([arithmetic.CC, '-O2', '-fno-builtin', '-Werror', '-Wno-unused-value',
                '-Wno-parentheses-equality', str(path), str(foreign), '-o', str(output)], cwd=root,
                text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(output)], cwd=root, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('clang'), 'layout verification requires clang')
    def test_layout_queries_match_target_c_on_five_targets(self):
        queries = []
        for name, members in [('Word', ['integer', 'bytes', 'payload']), ('Packed', ['bytes', 'integer']),
                              ('Aligned', ['integer', 'bytes']), ('Nested', ['word', 'wide'])]:
            queries += [(f'sizeof<{name}>()', f'sizeof({name})'), (f'alignof<{name}>()', f'_Alignof({name})')]
            queries += [(f'offsetof<{name}>("{member}")', f'offsetof({name}, {member})') for member in members]
        for target in ('i386-unknown-none-elf', 'i686-unknown-none-elf', 'x86_64-unknown-none-elf',
                       'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='reo union layout ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                # Queries precede declarations, so the global semantic model
                # must preserve union/packed/alignment metadata before checking.
                source = '\n'.join(f'fn query_{i}() -> usize {{ return {reo}; }}' for i, (reo, _) in enumerate(queries)) + DECLARATIONS
                generated = self.generated(source, target)
                checks = []
                for i, (_, c) in enumerate(queries):
                    match = re.search(r'uintptr_t query_' + str(i) + r'\(void\)\s*\{.*?return\s+\(\(uintptr_t\)(\d+)LL\)', generated, re.S)
                    self.assertIsNotNone(match)
                    checks.append(f'_Static_assert({c} == {match.group(1)}, "union query {i}");')
                path = root / 'probe.c'
                path.write_text(generated + '\n' + '\n'.join(checks), encoding='utf-8')
                result = subprocess.run([shutil.which('clang'), '--target=' + target, '-O2', '-ffreestanding',
                    '-fno-builtin', '-Werror', '-c', str(path), '-o', str(root / 'probe.o')], cwd=root,
                    text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_backends_do_not_ignore_union(self):
        with tempfile.TemporaryDirectory(prefix='reo union backend ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path = root / 'probe.reo'
            path.write_text('union Word { x: u32 } fn main() {}', encoding='utf-8')
            for flags in (['--backend', 'native', '--emit', 'obj'], ['--target', 'reo']):
                result = subprocess.run([str(semantics.COMPILER), 'build', str(path), *flags, '-o', str(root / 'probe.out')],
                    cwd=root, text=True, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('union declarations are not supported', result.stderr)


if __name__ == '__main__':
    unittest.main()
