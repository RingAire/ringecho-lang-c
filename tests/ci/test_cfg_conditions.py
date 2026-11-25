"""@cfg conditions: host OS, kernel/hosted, target architecture."""

import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()


def host_arch() -> str:
    target = os.environ.get("TARGET_ARCH", "").lower()
    if target in ("x64", "x86_64"):
        return "x86_64"
    if target == "x86":
        return "x86"
    if target == "arm64":
        return "aarch64"
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    if machine in ("x86", "i386", "i686"):
        return "x86"
    return "arm"


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class CfgConditionTests(unittest.TestCase):
    def test_hosted_and_kernel_are_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="reo cfg hosted ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(
                "@cfg(hosted)\nfn mode() -> i64 { return 1; }\n"
                "@cfg(kernel)\nfn mode() -> i64 { return 2; }\n"
                "fn main() { assert(mode() == 1i64); println(\"ok\"); }\n",
                encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary, "TMPDIR": temporary}
            result = subprocess.run([str(COMPILER), "run", str(source)],
                                    env=env, cwd=root, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ok", result.stdout)

    def test_kernel_build_keeps_kernel_and_x86_arch(self):
        with tempfile.TemporaryDirectory(prefix="reo cfg kernel ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(
                "@cfg(kernel)\nfn kernel_mode() -> i64 { return 2; }\n"
                "@cfg(hosted)\nfn hosted_mode() -> i64 { return 1; }\n"
                "@cfg(target_arch = \"x86\")\nfn arch_x86() -> i64 { return 32; }\n"
                "@cfg(target_arch = \"aarch64\")\nfn arch_arm() -> i64 { return 64; }\n"
                "fn main() {}\n",
                encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            subprocess.run([str(COMPILER), "build", str(source), "--kernel",
                            "--kernel-cc", str(root / "missing-compiler"),
                            "-o", str(root / "probe.elf")],
                           env=env, cwd=root, capture_output=True, text=True, timeout=120)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            self.assertIn("kernel_mode", text)
            self.assertIn("arch_x86", text)
            self.assertNotIn("hosted_mode", text)
            self.assertNotIn("arch_arm", text)

    def test_hosted_target_arch_matches_the_host(self):
        arch = host_arch()
        other = "aarch64" if arch != "aarch64" else "x86_64"
        with tempfile.TemporaryDirectory(prefix="reo cfg arch ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            source = root / "probe.reo"
            source.write_text(
                f"@cfg(target_arch = \"{arch}\")\nfn host_probe() -> i64 {{ return 1; }}\n"
                f"@cfg(target_arch = \"{other}\")\nfn other_probe() -> i64 {{ return 2; }}\n"
                "fn main() {}\n", encoding="utf-8")
            env = {**os.environ, "TMP": temporary, "TEMP": temporary,
                   "TMPDIR": temporary, "REO_KEEP_C": "1"}
            subprocess.run([str(COMPILER), "build", str(source),
                            "-o", str(root / "probe.exe")],
                           env=env, cwd=root, capture_output=True, text=True, timeout=120)
            generated = list(root.rglob("re0_codegen_*.c"))
            self.assertTrue(generated, "compiler kept no generated C")
            text = generated[0].read_text(encoding="utf-8")
            self.assertIn("host_probe", text)
            self.assertNotIn("other_probe", text)


if __name__ == "__main__":
    unittest.main()
