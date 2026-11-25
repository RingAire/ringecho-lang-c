"""LSP framing: malformed frames must fail loudly, clean EOF must exit 0."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class LspFramingTests(unittest.TestCase):
    def run_lsp(self, payload: bytes) -> subprocess.CompletedProcess:
        return subprocess.run([str(COMPILER), "lsp"], input=payload,
                              capture_output=True, timeout=30)

    def test_invalid_content_length_exits_nonzero(self):
        result = self.run_lsp(b"Content-Length: 999999999\r\n\r\n")
        output = (result.stdout or b"") + (result.stderr or b"")
        self.assertEqual(result.returncode, 1, output)
        self.assertIn(b"invalid Content-Length", output)

    def test_clean_eof_exits_zero(self):
        result = self.run_lsp(b"")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
