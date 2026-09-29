#!/usr/bin/env python3
"""Check that all model artifacts can be loaded in the current Python environment."""

import argparse
import math
from pathlib import Path
import sys

from train_models import MODELS, ROOT


def main():
    parser = argparse.ArgumentParser(description="Проверка артефактов четырёх моделей")
    parser.add_argument("--model-root", type=Path, default=ROOT / "model/models")
    args = parser.parse_args()
    try:
        import joblib
    except ImportError:
        print("Установите scripts/requirements-training.txt", file=sys.stderr)
        return 1
    failed = False
    for name, (_, _, directory, stems) in MODELS.items():
        try:
            model, threshold, features = (
                joblib.load(args.model_root / directory / f"{stem}.joblib")
                for stem in stems
            )
            if not math.isfinite(float(threshold)) or not 0 <= float(threshold) <= 1:
                raise ValueError("порог должен быть числом от 0 до 1")
            if len(features) == 0 or not all(isinstance(f, str) for f in features):
                raise ValueError("ожидается непустой список имён признаков")
            if not callable(getattr(model, "predict_proba", None)):
                raise ValueError("у модели нет predict_proba")
            if getattr(model, "n_features_in_", len(features)) != len(features):
                raise ValueError("число признаков не совпадает с моделью")
            print(f"OK {name}: {len(features)} признаков, порог {float(threshold):.4f}")
        except Exception as error:
            failed = True
            print(f"ERROR {name}: {error}", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
