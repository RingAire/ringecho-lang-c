"""Workspace limits: oversized entry files and import graphs beyond the table."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ".exe" if os.name == "nt" else ""
COMPILER = Path(os.environ.get("REO_TEST_COMPILER",
                               ROOT / "target" / "Release" / f"rev{EXE}")).resolve()
LIMIT_FILES = 64


@unittest.skipUnless(COMPILER.is_file(), "compiler binary not built")
class WorkspaceLimitTests(unittest.TestCase):
    def test_oversized_entry_file_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="reo size ", dir=ROOT / "target") as temporary:
            path = Path(temporary) / "big.reo"
            with path.open("wb") as handle:
                handle.write(b"fn main() {}\n")
                handle.seek(17 * 1024 * 1024 - 1)
                handle.write(b"\n")
            result = subprocess.run([str(COMPILER), "check", str(path)],
                                    capture_output=True, text=True, timeout=60)
            output = (result.stdout or "") + (result.stderr or "")
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("cannot read", output)

    def test_import_cycle_beyond_the_file_table_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="reo imports ", dir=ROOT / "target") as temporary:
            root = Path(temporary)
            entry = ["fn main() {}"]
            entry += [f'import "d{i}"' for i in range(LIMIT_FILES - 1)]
            entry.append('import "a"')
            (root / "main.reo").write_text("\n".join(entry) + "\n", encoding="utf-8")
            for i in range(LIMIT_FILES - 1):
                body = f'import "d{i + 1}"\n' if i < LIMIT_FILES - 2 else ""
                (root / f"d{i}.reo").write_text(body, encoding="utf-8")
            # Both files are beyond the table, so this cycle used to recurse.
            (root / "a.reo").write_text('import "b"\n', encoding="utf-8")
            (root / "b.reo").write_text('import "a"\n', encoding="utf-8")

            result = subprocess.run(
                [str(COMPILER), "build", str(root / "main.reo"), "-o", str(root / "out.exe")],
                cwd=root, capture_output=True, text=True, timeout=120)
            output = (result.stdout or "") + (result.stderr or "")
            self.assertEqual(result.returncode, 1,
                             "expected a limit error, got "
                             + str(result.returncode) + "\n" + output[:500])
            self.assertIn("too many imported files", output)


if __name__ == "__main__":
    unittest.main()
