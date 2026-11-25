"""Atomic typing/order validation, optimized execution and freestanding objects."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_arithmetic as arithmetic
import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '''
fn probe() -> i32 {
    let x: u32 = 3u32;
    let p: *mut u32 = (&mut x) as *mut u32;
    assert(atomic_load(p, "relaxed") == 3u32);
    atomic_store(p, 5u32, "release");
    assert(atomic_exchange(p, 9u32, "acq_rel") == 5u32);
    assert(atomic_fetch_add(p, 1u32, "relaxed") == 9u32);
    assert(atomic_fetch_sub(p, 2u32, "seq_cst") == 10u32);
    assert(atomic_fetch_and(p, 3u32, "acquire") == 8u32);
    assert(atomic_fetch_or(p, 7u32, "release") == 0u32);
    assert(atomic_fetch_xor(p, 1u32, "acq_rel") == 7u32);
    let expected: u32 = 99u32;
    let pe: *mut u32 = (&mut expected) as *mut u32;
    assert(!atomic_compare_exchange(p, pe, 11u32, "acq_rel", "acquire"));
    assert(expected == 6u32);
    assert(atomic_compare_exchange(p, pe, 11u32, "seq_cst", "seq_cst"));
    assert(expected == 6u32);
    assert(atomic_load(p, "acquire") == 11u32);
    let signed_value: i32 = 2147483647i32;
    let ps: *mut i32 = (&mut signed_value) as *mut i32;
    assert(atomic_fetch_add(ps, 1i32, "relaxed") == 2147483647i32);
    assert(atomic_load(ps, "relaxed") == -2147483648i32);
    let flag: bool = false;
    let pb: *mut bool = (&mut flag) as *mut bool;
    atomic_store(pb, true, "seq_cst");
    assert(atomic_load(pb, "seq_cst"));
    atomic_fence("acquire"); atomic_fence("release");
    atomic_fence("acq_rel"); atomic_fence("seq_cst");
    return 0i32;
}
'''


class AtomicTests(unittest.TestCase):
    def test_unsupported_backends_reject_atomic_calls(self):
        with tempfile.TemporaryDirectory(prefix='reo atomic backend errors ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path = root / 'probe.reo'
            path.write_text('fn main() { atomic_fence("seq_cst"); }', encoding='utf-8')
            for flags in (['--backend', 'native', '--emit', 'obj'], ['--target', 'reo']):
                result = subprocess.run([str(semantics.COMPILER), 'build', str(path), *flags, '-o', str(root / 'probe.out')], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('atomic operations are not supported', result.stderr)
    def generated(self, source=SOURCE, target="x86_64-unknown-none-elf"):
        stderr, generated = semantics.KernelSemanticsTests().generated(source, target)
        self.assertIsNotNone(generated, stderr)
        return generated

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_operations_and_strong_cas(self):
        arithmetic.KernelArithmeticTests().compile_run(self.generated(), 'int main(void) { return probe(); }')

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_operations_have_no_undefined_behavior(self):
        arithmetic.KernelArithmeticTests().compile_run(self.generated(), 'int main(void) { return probe(); }', sanitizer=True)

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_pointer_values_and_single_operand_evaluation(self):
        source = '''
        static target_value: u32;
        static calls: u32;
        fn address() -> *mut u32 { calls += 1u32; return (&mut target_value) as *mut u32; }
        fn value() -> u32 { calls += 1u32; return 3u32; }
        fn probe() -> i32 {
            assert(atomic_exchange(address(), value(), "seq_cst") == 0u32);
            assert(calls == 2u32);
            let stored: *mut u32 = address();
            let pp: *mut *mut u32 = (&mut stored) as *mut *mut u32;
            let nil: *mut u32 = 0usize as *mut u32;
            assert(atomic_exchange(pp, nil, "acq_rel") == address());
            assert(atomic_load(pp, "acquire") == nil);
            return 0i32;
        }
        '''
        arithmetic.KernelArithmeticTests().compile_run(self.generated(source), 'int main(void) { return probe(); }')

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_all_legal_cas_order_pairs(self):
        calls = []
        orders = ['relaxed', 'acquire', 'release', 'acq_rel', 'seq_cst']
        for success in orders:
            for failure in orders:
                if failure == 'relaxed' or (failure == 'acquire' and success in ('acquire', 'acq_rel', 'seq_cst')) or success == failure == 'seq_cst':
                    calls.append(f'expected = 0u32; atomic_store(p, 0u32, "relaxed"); assert(atomic_compare_exchange(p, pe, 1u32, "{success}", "{failure}"));')
        source = 'fn probe() -> i32 { let x: u32 = 0u32; let expected: u32 = 0u32; let p: *mut u32 = (&mut x) as *mut u32; let pe: *mut u32 = (&mut expected) as *mut u32; ' + ''.join(calls) + ' return 0i32; }'
        arithmetic.KernelArithmeticTests().compile_run(self.generated(source), 'int main(void) { return probe(); }')

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_concurrent_cas_lock_and_atomic_counter(self):
        source = '''
        static lock_value: u32;
        static count: u32;
        static protected_count: u32;
        fn worker() -> i32 {
            let p: *mut u32 = (&mut lock_value) as *mut u32;
            let pc: *mut u32 = (&mut count) as *mut u32;
            let expected: u32 = 0u32;
            let pe: *mut u32 = (&mut expected) as *mut u32;
            let i: u32 = 0u32;
            while i < 1000u32 {
                expected = 0u32;
                let attempts: u32 = 0u32;
                while !atomic_compare_exchange(p, pe, 1u32, "acquire", "relaxed") {
                    expected = 0u32;
                    attempts += 1u32;
                    if attempts == 10000000u32 { return 2i32; }
                }
                protected_count += 1u32;
                atomic_store(p, 0u32, "release");
                atomic_fetch_add(pc, 1u32, "relaxed");
                i += 1u32;
            }
            return 0i32;
        }
        fn verify() -> i32 {
            let pc: *const u32 = (&count) as *const u32;
            if atomic_load(pc, "seq_cst") != 2000u32 { return 3i32; }
            if protected_count != 2000u32 { return 4i32; }
            return 0i32;
        }
        '''
        if os.name == 'nt':
            driver = '''
            #include <windows.h>
            extern int worker(void); extern int verify(void);
            static DWORD WINAPI start(LPVOID p) { (void)p; return (DWORD)worker(); }
            int main(void) {
                HANDLE handles[2];
                for (int i = 0; i < 2; ++i) { handles[i] = CreateThread(0, 0, start, 0, 0, 0); if (!handles[i]) return 2; }
                for (int i = 0; i < 2; ++i) { DWORD code; if (WaitForSingleObject(handles[i], 15000) != WAIT_OBJECT_0 || !GetExitCodeThread(handles[i], &code) || code) return 3; CloseHandle(handles[i]); }
                return verify();
            }
            '''
        else:
            driver = '''
            #include <pthread.h>
            #include <stdint.h>
            extern int worker(void); extern int verify(void);
            static void *start(void *p) { (void)p; return (void *)(uintptr_t)worker(); }
            int main(void) {
                pthread_t threads[2];
                for (int i = 0; i < 2; ++i) if (pthread_create(&threads[i], 0, start, 0)) return 2;
                for (int i = 0; i < 2; ++i) { void *result; if (pthread_join(threads[i], &result) || result) return 3; }
                return verify();
            }
            '''
        with tempfile.TemporaryDirectory(prefix='reo atomic threads ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            path, host, output = root / 'probe.c', root / 'threads.c', root / ('probe.exe' if os.name == 'nt' else 'probe')
            path.write_text(self.generated(source), encoding='utf-8')
            host.write_text(driver, encoding='utf-8')
            args = [arithmetic.CC, '-O2', '-fno-builtin', '-Werror', '-Wno-unused-value', '-Wno-parentheses-equality', str(path), str(host), '-o', str(output)]
            if os.name != 'nt':
                args += ['-pthread']
            result = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(output)], cwd=root, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_orders_and_types_are_rejected(self):
        calls = ['atomic_load(p, "release")', 'atomic_load(p, "acq_rel")',
                 'atomic_store(p, 1u32, "acquire")', 'atomic_store(p, 1u32, "acq_rel")',
                 'atomic_fence("relaxed")', 'atomic_fence("consume")',
                 'atomic_load(p, order)', 'atomic_store(p, 1u64, "relaxed")',
                 'atomic_load(x, "relaxed")', 'atomic_load(p)',
                 'atomic_fetch_add(p, true, "relaxed")']
        orders = ['relaxed', 'acquire', 'release', 'acq_rel', 'seq_cst']
        for success in orders:
            for failure in orders:
                legal = failure == 'relaxed' or (failure == 'acquire' and success in ('acquire', 'acq_rel', 'seq_cst')) or success == failure == 'seq_cst'
                if not legal:
                    calls.append(f'atomic_compare_exchange(p, pe, 1u32, "{success}", "{failure}")')
        with tempfile.TemporaryDirectory(prefix='reo invalid atomic ', dir=ROOT / 'target') as temporary:
            root = Path(temporary)
            for call in calls:
                with self.subTest(call=call):
                    source = 'fn probe() { let x: u32 = 0u32; let expected: u32 = 0u32; let p: *mut u32 = (&mut x) as *mut u32; let pe: *mut u32 = (&mut expected) as *mut u32; let order = "acquire"; ' + call + '; }'
                    path = root / 'probe.reo'
                    path.write_text(source, encoding='utf-8')
                    result = subprocess.run([str(semantics.COMPILER), 'check', str(path)], cwd=root, text=True, capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertIn('atomic operation:', result.stderr)

    def test_wide_atomic_is_rejected_on_32_bit_target(self):
        stderr, generated = semantics.KernelSemanticsTests().generated('fn probe(p: *mut u64) -> u64 { return atomic_load(p, "relaxed"); }', 'i686-unknown-none-elf')
        self.assertIsNone(generated)
        self.assertIn('lock-free atomic', stderr)

    @unittest.skipUnless(arithmetic.CC, "execution requires a host compiler")
    def test_null_and_misaligned_addresses_fail_closed(self):
        source = 'fn probe(p: *mut u32) -> u32 { return atomic_load(p, "relaxed"); }'
        for harness in ['int main(void) { (void)probe(0); return 1; }',
                        'int main(void) { _Alignas(4) unsigned char bytes[8]; (void)probe((uint32_t *)(bytes + 1)); return 1; }']:
            arithmetic.KernelArithmeticTests().compile_run(self.generated(source), harness, 86)

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-nm'), "object verification requires LLVM")
    def test_four_target_objects_have_no_libatomic_dependency(self):
        for target in ('i686-unknown-none-elf', 'x86_64-unknown-none-elf', 'aarch64-unknown-none-elf', 'armv7-unknown-none-eabi'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='reo atomic object ', dir=ROOT / 'target') as temporary:
                root = Path(temporary)
                source = 'fn probe(p: *mut u32, expected: *mut u32) -> bool { atomic_fetch_add(p, 1u32, "relaxed"); atomic_fence("seq_cst"); return atomic_compare_exchange(p, expected, 3u32, "acq_rel", "acquire"); }'
                path, obj = root / 'probe.c', root / 'probe.o'
                path.write_text(self.generated(source, target), encoding='utf-8')
                result = subprocess.run([shutil.which('clang'), '--target=' + target, '-O2', '-ffreestanding', '-fno-builtin', '-Werror', '-Wno-unused-value', '-c', str(path), '-o', str(obj)], cwd=root, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([shutil.which('llvm-nm'), '--undefined-only', str(obj)], cwd=root, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                allowed = {'__reo_kernel_abort', '__reo_kernel_diagnostic', '__reo_kernel_depth_enter', '__reo_kernel_depth_leave'}
                self.assertEqual([line for line in result.stdout.splitlines() if line.split()[-1] not in allowed], [], result.stdout)
                if shutil.which('llvm-objdump'):
                    result = subprocess.run([shutil.which('llvm-objdump'), '-d', str(obj)], cwd=root, text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if target.startswith(('i686', 'x86_64')):
                        # Some LLVM versions print the lock prefix as a separate
                        # addressed instruction; compare mnemonic order instead.
                        mnemonics = re.findall(r'\t([a-z][a-z0-9]*)', result.stdout)
                        self.assertRegex(' '.join(mnemonics), r'\block cmpxchg')
                    elif target.startswith('aarch64'):
                        self.assertIn('ldaxr', result.stdout)
                        self.assertIn('stlxr', result.stdout)
                    else:
                        self.assertIn('ldrex', result.stdout)
                        self.assertIn('strex', result.stdout)


if __name__ == '__main__':
    unittest.main()
