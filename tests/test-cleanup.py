import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "cleanup-run.ps1"


class CleanupRunTests(unittest.TestCase):
    def run_cleanup(self, run_dir: Path):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-RunDirectory", str(run_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_removes_known_intermediates_and_keeps_deliverables(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "run.json").write_text("{}", encoding="utf-8")
            for name in ["score.mscz", "score-proof.pdf", "score.mid", "score.mxl", "report.md", "user-note.txt"]:
                (run / name).write_bytes(b"keep")
            for name in ["score-imported.mscz", "score-layout.mscz", "verify-playback-abc.mid", "verification.stdout.log"]:
                (run / name).write_bytes(b"remove")
            for name in ["audiveris", "runtime-data", "source-thumbnails", "candidate-original", "structure-verify-abc"]:
                folder = run / name
                folder.mkdir()
                (folder / "data.bin").write_bytes(b"remove")

            result = self.run_cleanup(run)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["performed"])
            for name in ["score.mscz", "score-proof.pdf", "score.mid", "score.mxl", "report.md", "user-note.txt"]:
                self.assertTrue((run / name).exists(), name)
            for name in ["score-imported.mscz", "score-layout.mscz", "verify-playback-abc.mid", "verification.stdout.log", "audiveris", "runtime-data", "source-thumbnails", "candidate-original", "structure-verify-abc"]:
                self.assertFalse((run / name).exists(), name)

    def test_deletes_only_selected_pdf_inside_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            run = Path(tmp)
            inside_pdf = run / "selected-source.pdf"
            outside_pdf = Path(outside_tmp) / "original.pdf"
            inside_pdf.write_bytes(b"inside")
            outside_pdf.write_bytes(b"outside")
            (run / "run.json").write_text("{}", encoding="utf-8")
            (run / "selection.json").write_text(json.dumps({"selectedPdf": str(inside_pdf)}), encoding="utf-8")
            result = self.run_cleanup(run)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(inside_pdf.exists())
            self.assertTrue(outside_pdf.exists())
            selection = json.loads((run / "selection.json").read_text(encoding="utf-8-sig"))
            self.assertIsNone(selection["selectedPdf"])
            self.assertTrue(selection["selectedPdfRemovedAfterValidation"])

            (run / "selection.json").write_text(json.dumps({"selectedPdf": str(outside_pdf)}), encoding="utf-8")
            result = self.run_cleanup(run)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(outside_pdf.exists())

    def test_refuses_directory_without_run_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "score-imported.mscz").write_bytes(b"keep")
            result = self.run_cleanup(run)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((run / "score-imported.mscz").exists())


if __name__ == "__main__":
    unittest.main()
