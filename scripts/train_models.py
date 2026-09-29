#!/usr/bin/env python3
"""Run the repository's training programs with preflight checks and staged output."""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# name: (training program, parquet path, output directory, artifact stems)
MODELS = {
    "fire_risk": (
        "fire_risk/scripts/train_model.py",
        "fire_risk/fire_risk_dataset_v3_equipped.parquet",
        "fire_risk/saved",
        ("fire_risk_model", "fire_risk_threshold", "fire_risk_features"),
    ),
    "nsd_event": (
        "unac/scripts/train_model.py",
        "unac/unac_dataset_v2.parquet",
        "unac/saved",
        ("nsd_model_clean", "nsd_threshold_clean", "nsd_features_clean"),
    ),
    "nsd_risk": (
        "unac/scripts/train_model_risk.py",
        "unac/unac_risk_dataset.parquet",
        "unac/saved",
        ("nsd_risk_model", "nsd_risk_threshold", "nsd_risk_features"),
    ),
    "fault_risk": (
        "fault_risk/scripts/train_model.py",
        "fault_risk/fault_dataset_v2.parquet",
        "fault_risk/saved",
        ("fault_model", "fault_threshold", "fault_features"),
    ),
}


def preflight(names, data_root):
    errors = []
    modules = {"numpy", "pandas", "pyarrow", "joblib", "sklearn"}
    if set(names) & {"fire_risk", "nsd_event", "fault_risk"}:
        modules.add("lightgbm")
    if set(names) & {"fire_risk", "nsd_event"}:
        modules.add("matplotlib")
    if "fault_risk" in names:
        modules.add("catboost")
    for module in sorted(modules):
        if importlib.util.find_spec(module) is None:
            errors.append(f"Не установлен модуль: {module}")
    for name in names:
        dataset = data_root / MODELS[name][1]
        if not dataset.is_file() or dataset.stat().st_size == 0:
            errors.append(f"Отсутствует или пуст датасет: {dataset}")
    return errors


def train(names, data_root, output_root):
    # Do not publish incomplete training results, even if a legacy script exits 0.
    with tempfile.TemporaryDirectory(prefix="sensor-training-") as work:
        staging = Path(work) / "models"
        env = dict(os.environ, TRAIN_DATA_ROOT=str(data_root),
                   TRAIN_OUTPUT_ROOT=str(staging), MPLBACKEND="Agg")
        for name in names:
            script, _, directory, stems = MODELS[name]
            print(f"\n=== Обучение {name} ===", flush=True)
            subprocess.run(
                [sys.executable, "-u", str(ROOT / "model/models" / script)],
                cwd=work, env=env, check=True,
            )
            for stem in stems:
                artifact = staging / directory / f"{stem}.joblib"
                if not artifact.is_file() or artifact.stat().st_size == 0:
                    raise RuntimeError(f"Обучение не создало артефакт: {artifact}")
        # All selected programs finished successfully. Publish artifacts and plots.
        for source in staging.rglob("*"):
            if source.is_file():
                target = output_root / source.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        print(f"\nАртефакты сохранены: {output_root}")


def main():
    parser = argparse.ArgumentParser(description="Обучение четырёх моделей Sensor Predictor")
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS),
                        help="модели для обучения (по умолчанию все)")
    parser.add_argument("--data-root", type=Path, default=ROOT / "model/dataset/parquets",
                        help="каталог с подкаталогами fire_risk, unac, fault_risk")
    parser.add_argument("--output-root", type=Path, default=ROOT / "model/models",
                        help="каталог для моделей; существующие артефакты заменяются после обучения")
    parser.add_argument("--check-only", action="store_true",
                        help="проверить наличие датасетов и Python-модулей без обучения")
    args = parser.parse_args()
    names = list(dict.fromkeys(args.models))
    errors = preflight(names, args.data_root.resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print("Зависимости: python -m pip install -r scripts/requirements-training.txt",
              file=sys.stderr)
        return 1
    if args.check_only:
        print("Датасеты и Python-модули найдены. Содержимое датасетов проверяется при обучении.")
        return 0
    try:
        train(names, args.data_root.resolve(), args.output_root.resolve())
    except (subprocess.CalledProcessError, OSError, RuntimeError) as error:
        print(f"Ошибка обучения: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
