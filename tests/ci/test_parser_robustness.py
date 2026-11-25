"""Regression guard: malformed source must be rejected, never crash the parser.

These inputs used to read the token union's numeric fields as string pointers
(`fn a'x'`, `fn a(1)`, ...), which segfaulted the compiler. A crash also exits
non-zero, so the `rev check` expected-failure loop in the Makefile cannot tell
the difference; this test requires a clean syntax error (exit code 1).
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""


def find_compiler() -> Path | None:
    env = os.environ.get("REO_TEST_COMPILER")
    candidates = [Path(env)] if env else []
    candidates += [ROOT / "target" / cfg / f"rev{EXE}" for cfg in ("Release", "Debug", "Alpha")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


CASES = {
    "fn_param_char": "fn a'x'\n",
    "fn_param_number": "fn a(1) {}\n",
    "lambda_param_char": "fn main() { let f = |'x'| 0; }\n",
    "type_annotation_char": "fn main() { let x: 'a' = 1; }\n",
    "impl_param_char": "impl A { fn m('x') {} }\n",
    "static_token": "fn main() { let y = 1 + static; }\n",
}


class ParserRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        if cls.compiler is None:
            raise unittest.SkipTest("REO compiler binary not built")

    def run_check(self, source: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="reo-parser-") as directory:
            path = Path(directory) / "probe.reo"
            path.write_text(source, encoding="utf-8")
            return subprocess.run([str(self.compiler), "check", str(path)],
                                  capture_output=True, text=True, timeout=120)

    def test_many_hash_comments_do_not_overflow_the_stack(self):
        result = self.run_check(("#" + chr(10)) * 6000 + "fn main() {}" + chr(10))
        output = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("check passed", output)

    def test_deep_else_if_reports_an_error_instead_of_crashing(self):
        source = ("fn main() { let x = if true {} " + "else if true {} " * 20000
                  + "else {}; }" + chr(10))
        result = self.run_check(source)
        output = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 1,
                         "expected a syntax error, got "
                         + str(result.returncode) + chr(10) + output[:500])
        self.assertIn("error:", output)

    def test_unterminated_block_comment_is_rejected(self):
        result = self.run_check('fn main() {}\n/* unterminated\n')
        output = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("unterminated block comment", output)

    def test_embedded_nul_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="reo-parser-") as directory:
            path = Path(directory) / "nul.reo"
            path.write_bytes(b"fn main() {}\n" + bytes([0]) + b"println(1);\n")
            result = subprocess.run([str(self.compiler), "check", str(path)],
                                    capture_output=True, text=True, timeout=60)
            output = (result.stdout or "") + (result.stderr or "")
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("NUL byte", output)

    def test_overlong_identifier_is_rejected(self):
        result = self.run_check("fn main() { let " + "a" * 300 + ": i64 = 1; }\n")
        output = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("longer than", output)

    def test_malformed_names_are_rejected_without_crashing(self):
        with tempfile.TemporaryDirectory(prefix="reo-parser-") as directory:
            for name, source in CASES.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.reo"
                    path.write_text(source, encoding="utf-8")
                    result = subprocess.run(
                        [str(self.compiler), "check", str(path)],
                        capture_output=True, text=True, timeout=60)
                    output = (result.stdout or "") + (result.stderr or "")
                    self.assertEqual(result.returncode, 1,
                                     f"{name}: expected a syntax error, got {result.returncode}\n{output}")
                    self.assertIn("error:", output, f"{name}: no diagnostic\n{output}")


if __name__ == "__main__":
    unittest.main()
