"""Kernel semantics regressions, without requiring a cross compiler or QEMU."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPILER = Path(os.environ.get(
    "REO_TEST_COMPILER", ROOT / "target/Release" / ("rev.exe" if os.name == "nt" else "rev")
)).resolve()


class KernelSemanticsTests(unittest.TestCase):
    def generated(self, source, target=None, environment_target=None):
        with tempfile.TemporaryDirectory(prefix="reo kernel semantics ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            path = root / "probe.reo"
            path.write_text(source, encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            env.pop("REO_KERNEL_TARGET", None)
            if environment_target:
                env["REO_KERNEL_TARGET"] = environment_target
            args = [str(COMPILER), "build", str(path), "--kernel",
                    "--kernel-cc", str(root / "missing-compiler"),
                    "-o", str(root / "probe.elf")]
            if target:
                args += ["--kernel-target", target]
            result = subprocess.run(args, env=env, cwd=root, text=True,
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            files = list(root.rglob("*.c"))
            return result.stderr, files[0].read_text(encoding="utf-8") if files else None

    def test_pointer_width_uses_kernel_target_and_environment(self):
        for target, environment, width in [
            (None, None, 4),
            ("i686-unknown-none-elf", "x86_64-unknown-none-elf", 4),
            (None, "x86_64-unknown-none-elf", 8),
            ("aarch64-unknown-none-elf", None, 8),
            ("armv7-unknown-none-eabi", None, 4),
        ]:
            with self.subTest(target=target, environment=environment):
                stderr, generated = self.generated(
                    f"fn probe() {{ assert(sizeof<ptr>() == {width}); }}",
                    target, environment)
                self.assertIn("kernel compilation of generated C failed", stderr)
                self.assertIsNotNone(generated)
                self.assertIn(f"((uintptr_t){width}LL)", generated)

    def test_unknown_target_fails_before_codegen(self):
        stderr, generated = self.generated("fn probe() {}", "aarch64_be-unknown-none-elf")
        self.assertIn("unsupported kernel target layout", stderr)
        self.assertIsNone(generated)

    def test_assert_and_panic_do_not_call_host_exit(self):
        stderr, generated = self.generated('fn probe() { assert(false); panic("failure"); }')
        self.assertIn("kernel compilation of generated C failed", stderr)
        self.assertIsNotNone(generated)
        self.assertNotIn("exit(1)", generated)
        self.assertIn('? 0 : (__reo_kernel_fail_message("assertion failed"), 0)', generated)
        self.assertIn('_Noreturn static void __reo_kernel_fail', generated)
        self.assertIn('__builtin_trap()', generated)
        self.assertIn('__reo_kernel_fail_message("failure")', generated)


if __name__ == "__main__":
    unittest.main()
