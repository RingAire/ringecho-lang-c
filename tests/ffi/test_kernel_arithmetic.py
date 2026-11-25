"""Optimized execution and differential tests for freestanding integer helpers."""
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

import test_kernel_semantics as semantics

ROOT = Path(__file__).resolve().parents[2]
CC = os.environ.get("REO_TEST_CC") or shutil.which("clang") or shutil.which("gcc")
FAIL_EXIT = 86
HOOK = f"extern void _Exit(int); void __reo_kernel_abort(void) {{ _Exit({FAIL_EXIT}); }}\n"


def expected(a, b, bits, signed, op):
    mask = (1 << bits) - 1
    a &= mask
    b &= mask
    if op == 0:
        return (a + b) & mask
    if op == 1:
        return (a - b) & mask
    if op == 2:
        return (a * b) & mask
    if op == 5:
        return (a << (b & (bits - 1))) & mask
    if op == 6:
        value = a - (1 << bits) if signed and a >> (bits - 1) else a
        return (value >> (b & (bits - 1))) & mask
    left = a - (1 << bits) if signed and a >> (bits - 1) else a
    right = b - (1 << bits) if signed and b >> (bits - 1) else b
    if not right or (signed and left == -(1 << (bits - 1)) and right == -1):
        return None
    quotient = abs(left) // abs(right)
    if (left < 0) != (right < 0):
        quotient = -quotient
    return (quotient if op == 3 else left - quotient * right) & mask


@unittest.skipUnless(CC, "optimized kernel helper tests require a host C compiler")
class KernelArithmeticTests(unittest.TestCase):
    def compile_run(self, generated, harness, expected_exit=0, sanitizer=False, hook=True):
        with tempfile.TemporaryDirectory(prefix="reo integer tests ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.c"
            source.write_text(generated + (HOOK if hook else "") + harness, encoding="utf-8")
            output = root / ("probe.exe" if os.name == "nt" else "probe")
            args = [CC, "-O2", "-fno-builtin", "-Werror", "-Wno-unused-value",
                    "-Wno-parentheses-equality", str(source), "-o", str(output)]
            if sanitizer:
                args += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
                # Only missing sanitizer/toolchain support may skip; generated
                # source compile errors must remain real test failures.
                capability = root / "sanitizer.c"
                capability.write_text("int main(void) { return 0; }", encoding="utf-8")
                checked = subprocess.run([CC, "-fsanitize=undefined", str(capability), "-o", str(root / "sanitizer.exe")],
                    cwd=root, text=True, capture_output=True, timeout=90)
                if checked.returncode:
                    self.skipTest("host toolchain cannot build UBSan: " + checked.stderr[-500:])
            result = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(output)], cwd=root, text=True, capture_output=True, timeout=30)
            if expected_exit is None:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertEqual(result.returncode, expected_exit, result.stdout + result.stderr)

    def generated(self, source, target="x86_64-unknown-none-elf"):
        stderr, generated = semantics.KernelSemanticsTests().generated(source, target)
        self.assertIsNotNone(generated, stderr)
        return generated

    def test_reo_boundaries_compound_assignment_and_single_evaluation(self):
        source = """
        struct Counter { value: i8 }
        static calls: i64;
        fn operand() -> i64 { calls += 1; return 9223372036854775807i64; }
        fn probe() -> i32 {
            let a: i8 = 127i8;
            let min8: i8 = -128i8;
            assert(a + 1i8 == -128i8);
            assert(-min8 == min8);
            assert(-128i8 - 1i8 == 127i8);
            assert(-128i8 * -1i8 == -128i8);
            let b: u16 = 65535u16;
            b += 1u16;
            assert(b == 0u16);
            b -= 1u16;
            assert(b == 65535u16);
            let counter = Counter { value: 127i8 };
            counter.value += 1i8;
            assert(counter.value == -128i8);
            let items: [i8; 2] = [127i8, 0i8];
            items[0] += 1i8;
            assert(items[0] == -128i8);
            let pointer: *mut volatile u16 = (&mut b) as *mut volatile u16;
            *pointer += 1u16;
            assert(*pointer == 0u16);
            let min: i64 = -9223372036854775808i64;
            assert(-min == min);
            assert(operand() + 1i64 == min);
            assert(calls == 1);
            assert(1u32 << 32u32 == 1u32);
            assert(1i32 << -1i32 == -2147483648i32);
            assert(-2i64 >> 65i64 == -1i64);
            assert(-7i64 / 3i64 == -2i64);
            assert(-7i64 % 3i64 == -1i64);
            assert(7i64 / -3i64 == -2i64);
            assert(7i64 % -3i64 == 1i64);
            assert((65535u16 as i8) == -1i8);
            assert((-1i8 as u64) == 18446744073709551615u64);
            assert((18446744073709551615u64 as i64) == -1i64);
            return 0i32;
        }
        """
        self.compile_run(self.generated(source), "int main(void) { return probe(); }\n")

    def test_division_failures_call_abort_hook(self):
        for expression in ("1u64 / 0u64", "1i64 % 0i64",
                           "-9223372036854775808i64 / -1i64",
                           "-9223372036854775808i64 % -1i64",
                           "-170141183460469231731687303715884105728i128 / -1i128",
                           "-170141183460469231731687303715884105728i128 % -1i128"):
            with self.subTest(expression=expression):
                source = f"fn probe() -> i32 {{ assert({expression} == 0); return 0i32; }}"
                self.compile_run(self.generated(source), "int main(void) { return probe(); }\n", FAIL_EXIT)

    def test_missing_abort_hook_traps_instead_of_continuing(self):
        source = "fn probe() -> i32 { assert(1u64 / 0u64 == 0); return 0i32; }"
        self.compile_run(self.generated(source), "int main(void) { return probe(); }\n", None, hook=False)

    def test_malformed_helper_parameters_fail_closed(self):
        for bits, op in ((0, 0), (7, 0), (65, 0), (64, 99)):
            with self.subTest(bits=bits, op=op):
                harness = f"int main(void) {{ (void)__reo_kernel_binary64(1, 1, {bits}, false, {op}); return 0; }}\n"
                self.compile_run(self.generated("fn probe() {}"), harness, FAIL_EXIT)

    def differential_harness(self, widths):
        rng = random.Random(0x524E55)
        statements = []
        for bits in widths:
            mask = (1 << bits) - 1
            sign = 1 << (bits - 1)
            values = [0, 1, 2, mask, mask - 1, sign, sign - 1, sign + 1]
            pairs = [(a, b) for a in values for b in values]
            pairs += [(rng.getrandbits(bits), rng.getrandbits(bits)) for _ in range(40)]
            for signed in (False, True):
                for op in range(7):
                    for a, b in pairs:
                        answer = expected(a, b, bits, signed, op)
                        if answer is None:
                            continue
                        suffix = "128" if bits == 128 else "64"

                        def literal(value):
                            if bits == 128:
                                return f"(((__reo_u128)0x{value >> 64:x}ULL << 64) | 0x{value & ((1 << 64) - 1):x}ULL)"
                            return f"0x{value:x}ULL"

                        statements.append(
                            f"{{ volatile __reo_kernel_u{suffix} a = {literal(a)}, b = {literal(b)};\n"
                            f"if (__reo_kernel_binary{suffix}(a, b, {bits}, "
                            f"{'true' if signed else 'false'}, {op}) != {literal(answer)}) return 1;\n")
                        if signed:
                            # Test decoding without implementation-defined casts.
                            signed_answer = answer - (1 << bits) if answer & sign else answer
                            if signed_answer >= 0:
                                decoded = f"(__reo_kernel_s{suffix})({literal(signed_answer)})"
                            else:
                                decoded = f"(-1 - (__reo_kernel_s{suffix})({literal(-1 - signed_answer)}))"
                            statements.append(
                                f"volatile __reo_kernel_u{suffix} value = {literal(answer)};\n"
                                f"if (__reo_kernel_signed{suffix}(value, {bits}) != {decoded}) return 2;\n")
                        statements.append("}\n")
        return "int main(void) {\n" + "".join(statements) + "return 0; }\n"

    def test_unsigned_and_signed_helpers_match_integer_reference(self):
        self.compile_run(self.generated("fn probe() {}"), self.differential_harness((8, 16, 32, 64)))

    def test_128_bit_helpers_match_integer_reference(self):
        self.compile_run(self.generated("fn probe() {}"), self.differential_harness((128,)))

    def test_integer_helpers_with_undefined_behavior_sanitizer(self):
        self.compile_run(self.generated("fn probe() {}"), self.differential_harness((8, 16, 32, 64, 128)), sanitizer=True)

    @unittest.skipUnless(shutil.which("llvm-nm") and shutil.which("clang"), "cross-object test requires clang and llvm-nm")
    def test_cross_objects_need_no_integer_division_runtime(self):
        source = """
        fn probe(a: u64, b: u64) -> u64 {
            let quotient: u64 = a / b;
            let remainder: u64 = a % b;
            let negated: i64 = -(a as i64);
            return (quotient + remainder + (negated as u64) + (a * b)) << b;
        }
        """
        cases = [(target, 64) for target in ("i686-unknown-none-elf", "x86_64-unknown-none-elf",
                                           "aarch64-unknown-none-elf", "armv7-unknown-none-eabi")]
        cases += [(target, 128) for target in ("x86_64-unknown-none-elf", "aarch64-unknown-none-elf")]
        for target, width in cases:
            with self.subTest(target=target, width=width), tempfile.TemporaryDirectory(prefix="reo integer object ", dir=ROOT / "target") as temporary:
                root = Path(temporary)
                path = root / "probe.c"
                program = source if width == 64 else source.replace("u64", "u128").replace("i64", "i128")
                path.write_text(self.generated(program, target), encoding="utf-8")
                output = root / "probe.o"
                result = subprocess.run([shutil.which("clang"), "--target=" + target,
                    "-O2", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-stack-protector",
                    "-Werror", "-Wno-unused-value", "-c", str(path), "-o", str(output)],
                    text=True, capture_output=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run([shutil.which("llvm-nm"), "--undefined-only", str(output)],
                    text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                allowed = {"__reo_kernel_abort", "__reo_kernel_diagnostic", "__reo_kernel_depth_enter", "__reo_kernel_depth_leave"}
                unresolved = [line for line in result.stdout.splitlines() if line.split()[-1] not in allowed]
                self.assertEqual(unresolved, [], result.stdout)


if __name__ == "__main__":
    unittest.main()
