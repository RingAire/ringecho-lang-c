"""Execute the REO-written structural type parser as a compiled host program."""
import os
import random
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPILER = Path(os.environ.get('REO_TEST_COMPILER', ROOT / 'target/Release' /
                              ('rev.exe' if os.name == 'nt' else 'rev'))).resolve()


class SelfhostTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='reo selfhost types ', dir=ROOT / 'target')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.program = cls.root / ('frontend.exe' if os.name == 'nt' else 'frontend')
        env = {**os.environ, 'TMP': str(cls.root), 'TEMP': str(cls.root), 'TMPDIR': str(cls.root), 'REO_KEEP_C': '1'}
        result = subprocess.run([str(COMPILER), 'build', str(ROOT / 'compiler-reo/frontend.reo'),
                                 '-o', str(cls.program)], env=env, cwd=ROOT,
                                text=True, capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.generated = list(cls.root.rglob('*.c'))

    def run_type(self, text):
        return subprocess.run([str(self.program), '--type', text], cwd=ROOT,
                              text=True, capture_output=True, timeout=15)

    def test_existing_frontend_and_structural_type_self_checks(self):
        result = subprocess.run([str(self.program)], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_types_roundtrip_without_erasing_qualifiers_or_shapes(self):
        cases = {
            '*volatile const u128': '*const volatile u128',
            '&mut [fn(*const u8, usize) -> u128; 4]': '&mut [fn(*const u8, usize) -> u128; 4]',
            'Result<(u8, [u32; 2]), Vec<*mut volatile u64>>': 'Result<(u8, [u32; 2]), Vec<*mut volatile u64>>',
            '(u128,)': '(u128,)', '(u128)': 'u128', 'fn()': 'fn() -> unit',
            '\r\n[ u8 ; 8 ]\r\n': '[u8; 8]',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                result = self.run_type(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), expected)
                again = self.run_type(expected)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertEqual(again.stdout.strip(), expected)

    def test_malformed_types_fail_without_crashing_or_accepting_prefixes(self):
        cases = ['', '*', '&mut', '[u8; -1]', '[u8; 18446744073709551616]',
                 '*mut const u8', '*mut mut u8', '*volatile volatile u8',
                 'fn(u8, -> u8', 'Vec<>', 'Vec<u8', 'u32<u8>', '(u8 u32)',
                 'u8 u16', '/*', '"unterminated', "'x", '*mut ' * 100 + 'u8',
                 '(' + ','.join(['u8'] * 66) + ')']
        for text in cases:
            with self.subTest(text=text):
                result = self.run_type(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('type:', result.stdout)

    def test_seeded_type_grammar_and_hostile_token_fuzz(self):
        rng = random.Random(20261015)

        def grammar(depth):
            if depth == 0:
                return rng.choice(['u8', 'u128', 'usize', 'bool', 'Node'])
            inner = grammar(depth - 1)
            return rng.choice([f'*const volatile {inner}', f'&mut {inner}', f'[{inner}; 3]',
                               f'[{inner}]', f'({inner}, u8)', f'fn({inner}) -> u128', f'Vec<{inner}>'])

        for _ in range(32):
            text = grammar(3)
            result = self.run_type(text)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            again = self.run_type(result.stdout.strip())
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertEqual(again.stdout, result.stdout)
        tokens = ['*', '&', 'mut', 'const', 'volatile', '[', ']', '(', ')', '<', '>', ',', ';', 'u8', 'fn', '->']
        for _ in range(64):
            text = ' '.join(rng.choices(tokens, k=rng.randrange(1, 24)))
            result = self.run_type(text)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('clang'), 'generated frontend UBSan requires clang')
    def test_generated_frontend_and_error_paths_under_ubsan(self):
        self.assertEqual(len(self.generated), 1)
        sanitized = self.root / ('frontend-ubsan.exe' if os.name == 'nt' else 'frontend-ubsan')
        result = subprocess.run([shutil.which('clang'), '-std=gnu11', '-O1', '-g',
                                 '-fsanitize=undefined', '-fno-sanitize-recover=all',
                                 str(self.generated[0]), '-pthread', '-lm', '-o', str(sanitized)],
                                cwd=self.root, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for args, expected in [([], 0), (['--type', '*mut ' * 100 + 'u8'], 1),
                               (['--type', '[u8; 9223372036854775808]'], 1)]:
            result = subprocess.run([str(sanitized), *args], cwd=ROOT,
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            self.assertNotIn('runtime error:', result.stderr)


if __name__ == '__main__':
    unittest.main()
