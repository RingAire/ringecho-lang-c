"""Freestanding hook failure injection and context-local depth validation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_kernel_arithmetic as arithmetic

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(arithmetic.CC, "kernel runtime execution requires a host compiler")
class KernelRuntimeTests(unittest.TestCase):
    def generated(self, source="fn probe() {}"):
        return arithmetic.KernelArithmeticTests().generated(source)

    def run_c(self, harness, source="fn probe() {}", expected=0):
        arithmetic.KernelArithmeticTests().compile_run(self.generated(source),
            "_Noreturn extern void _Exit(int);\n" + harness, expected, hook=False)

    def test_panic_and_assert_deliver_diagnostics(self):
        for source, message in [('fn probe() { panic("specific panic"); }', 'specific panic'),
                                ('fn probe() { assert(false); }', 'assertion failed')]:
            with self.subTest(message=message):
                self.run_c('void __reo_kernel_diagnostic(const char *p, size_t n) { '
                    f'if (n != {len(message)} || memcmp(p, "{message}", n)) _Exit(2); }}\n'
                    'void __reo_kernel_abort(void) { _Exit(86); }\n'
                    'int main(void) { probe(); return 1; }', source, 86)

    def test_diagnostic_length_is_bounded(self):
        self.run_c('void __reo_kernel_diagnostic(const char *p, size_t n) { '
            'if (n != 4096 || p[0] != 65) _Exit(2); }\n'
            'void __reo_kernel_abort(void) { _Exit(86); }\n'
            'int main(void) { char text[4097]; memset(text, 65, sizeof(text)); '
            '__reo_kernel_fail_message(text); }', expected=86)

    def test_missing_and_partial_allocator_hooks_fail_closed(self):
        for hook in ('', 'void *__reo_kernel_alloc(size_t n) { (void)n; _Exit(2); }',
                     'void __reo_kernel_free_impl(void *p) { (void)p; _Exit(2); }'):
            with self.subTest(hook=hook):
                self.run_c(hook + '\nvoid __reo_kernel_abort(void) { _Exit(86); }\n'
                    'int main(void) { (void)malloc(1); return 1; }', expected=86)

    def test_oom_sequence_allocation_terminates(self):
        self.run_c('void *__reo_kernel_alloc(size_t n) { (void)n; return 0; }\n'
            'void __reo_kernel_free_impl(void *p) { (void)p; }\n'
            'void __reo_kernel_abort(void) { _Exit(86); }\n'
            'int main(void) { (void)__reo_sequence_alloc(16); return 1; }', expected=86)

    def test_zero_allocation_and_null_free_need_no_hooks(self):
        self.run_c('int main(void) { free(0); return malloc(0) != 0; }')

    def test_freestanding_memmove_handles_overlap_and_zero_length(self):
        self.run_c('int main(void) { unsigned char data[8] = {0,1,2,3,4,5,6,7}; '
            'if (memmove(0, 0, 0) != 0) return 1; '
            'memmove(data + 1, data, 6); if (data[1] != 0 || data[6] != 5) return 2; '
            'memmove(data, data + 1, 6); if (data[0] != 0 || data[5] != 5) return 3; '
            'return memmove(data, data, 8) != data; }')

    def test_nonnull_free_without_hook_terminates(self):
        self.run_c('void __reo_kernel_abort(void) { _Exit(86); }\n'
            'int main(void) { int object = 0; free(&object); return 1; }', expected=86)

    def test_partial_depth_hooks_fail_closed(self):
        for hook in ('void *__reo_kernel_depth_enter(uint32_t n) { (void)n; _Exit(2); }',
                     'void __reo_kernel_depth_leave(void *p) { (void)p; _Exit(2); }'):
            with self.subTest(hook=hook):
                self.run_c(hook + '\nvoid __reo_kernel_abort(void) { _Exit(86); }\n'
                    'int main(void) { probe(); return 1; }', expected=86)

    def test_depth_tokens_are_balanced_across_normal_returns(self):
        source = 'fn probe(n: u32) -> u32 { if n == 0u32 { return 1u32; } return probe(n - 1u32) + 1u32; }'
        self.run_c('static unsigned depth, entered, left;\n'
            'void *__reo_kernel_depth_enter(uint32_t limit) { '
            'if (++depth > limit) _Exit(2); ++entered; return (void *)(uintptr_t)depth; }\n'
            'void __reo_kernel_depth_leave(void *token) { '
            'if ((uintptr_t)token != depth) _Exit(3); --depth; ++left; }\n'
            'int main(void) { return probe(31) != 32 || depth || entered != 32 || left != 32; }', source)

    def test_depth_hook_can_reject_stack_limit(self):
        source = 'fn probe(n: u32) -> u32 { if n == 0u32 { return 0u32; } return probe(n - 1u32) + 1u32; }'
        self.run_c('static unsigned depth;\n'
            'void *__reo_kernel_depth_enter(uint32_t limit) { '
            '(void)limit; if (++depth > 8) __reo_kernel_fail_message("stack limit"); return 0; }\n'
            'void __reo_kernel_depth_leave(void *token) { (void)token; --depth; }\n'
            'void __reo_kernel_abort(void) { _Exit(86); }\n'
            'int main(void) { (void)probe(31); return 1; }', source, 86)

    def test_returning_abort_hook_still_traps(self):
        self.run_c('void __reo_kernel_abort(void) {}\n'
            'int main(void) { __reo_kernel_fail(); }', expected=None)

    def test_depth_contexts_work_on_concurrent_host_threads(self):
        source = 'fn probe(n: u32) -> u32 { if n == 0u32 { return 1u32; } return probe(n - 1u32) + 1u32; }'
        hooks = '''
        _Noreturn extern void _Exit(int);
        static _Thread_local unsigned depth;
        void *__reo_kernel_depth_enter(uint32_t limit) {
            if (++depth > limit) _Exit(2);
            return (void *)(uintptr_t)depth;
        }
        void __reo_kernel_depth_leave(void *token) {
            if ((uintptr_t)token != depth) _Exit(3);
            --depth;
        }
        int worker(void) {
            for (unsigned i = 0; i < 100; ++i) if (probe(31) != 32 || depth) return 1;
            return 0;
        }
        '''
        if os.name == "nt":
            driver = '''
            #include <windows.h>
            extern int worker(void);
            static DWORD WINAPI start(LPVOID p) { (void)p; return (DWORD)worker(); }
            int main(void) {
                HANDLE threads[2];
                for (int i = 0; i < 2; ++i) {
                    threads[i] = CreateThread(0, 0, start, 0, 0, 0);
                    if (!threads[i]) return 2;
                }
                for (int i = 0; i < 2; ++i) {
                    DWORD code;
                    if (WaitForSingleObject(threads[i], 10000) != WAIT_OBJECT_0 ||
                        !GetExitCodeThread(threads[i], &code) || code) return 3;
                    CloseHandle(threads[i]);
                }
                return 0;
            }
            '''
        else:
            driver = '''
            #include <pthread.h>
            #include <stdint.h>
            extern int worker(void);
            static void *start(void *p) { (void)p; return (void *)(uintptr_t)worker(); }
            int main(void) {
                pthread_t threads[2];
                for (int i = 0; i < 2; ++i) if (pthread_create(&threads[i], 0, start, 0)) return 2;
                for (int i = 0; i < 2; ++i) {
                    void *result;
                    if (pthread_join(threads[i], &result) || result) return 3;
                }
                return 0;
            }
            '''
        with tempfile.TemporaryDirectory(prefix="reo depth contexts ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path, host = root / "probe.c", root / "threads.c"
            path.write_text(self.generated(source) + hooks, encoding="utf-8")
            host.write_text(driver, encoding="utf-8")
            output = root / ("probe.exe" if os.name == "nt" else "probe")
            args = [arithmetic.CC, '-O2', '-fno-builtin', '-Werror', '-Wno-parentheses-equality', str(path), str(host), '-o', str(output)]
            if os.name != "nt":
                args += ['-pthread']
            result = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(output)], cwd=root, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
