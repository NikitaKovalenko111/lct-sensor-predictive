"""Orchestration tests; no ML libraries or real datasets required."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import train_models


class TrainingTests(unittest.TestCase):
    def test_missing_datasets_reported_before_training(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("train_models.importlib.util.find_spec", return_value=object()):
                errors = train_models.preflight(list(train_models.MODELS), Path(directory))
        self.assertEqual(len(errors), 4)
        self.assertTrue(all("датасет" in error for error in errors))

    def test_success_publishes_artifacts(self):
        def fake_run(command, *, cwd, env, check):
            self.assertTrue(Path(command[-1]).is_absolute())
            output = Path(env["TRAIN_OUTPUT_ROOT"]) / "unac/saved"
            output.mkdir(parents=True)
            for stem in train_models.MODELS["nsd_risk"][3]:
                (output / f"{stem}.joblib").write_bytes(b"trained")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("train_models.subprocess.run", side_effect=fake_run):
                train_models.train(["nsd_risk"], root, root / "output")
            self.assertEqual(len(list((root / "output").rglob("*.joblib"))), 3)

    def test_failure_preserves_existing_artifacts(self):
        for failure in (None, subprocess.CalledProcessError(1, "trainer")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / "unac/saved/nsd_risk_model.joblib"
                artifact.parent.mkdir(parents=True)
                artifact.write_bytes(b"original")
                with patch("train_models.subprocess.run", side_effect=failure):
                    with self.assertRaises((RuntimeError, subprocess.CalledProcessError)):
                        train_models.train(["nsd_risk"], root, root)
                self.assertEqual(artifact.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
