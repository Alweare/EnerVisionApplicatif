"""
Versioning du jeu d'entraînement avec DVC (EN-44).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

DVC_ROOT = Path(os.environ.get("DVC_ROOT", Path(__file__).resolve().parents[3]))


class DatasetVersioningError(RuntimeError):
    """Échec de l'export CSV, du `dvc add` ou du `dvc push`."""


def _run_dvc(*args: str) -> None:
    """Lance `dvc <args>` dans le dépôt DVC, en remontant l'erreur exploitable.

    Invoqué via `python -m dvc` (interpréteur courant) plutôt que `dvc` tout
    court : indépendant du PATH, que le venv soit activé ou non.
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "dvc", *args],
            cwd=DVC_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:  # module `dvc` absent de l'environnement
        raise DatasetVersioningError("module `dvc` introuvable") from exc
    except subprocess.CalledProcessError as exc:
        raise DatasetVersioningError(
            f"`dvc {' '.join(args)}` a échoué (code {exc.returncode}) :\n{exc.stderr}"
        ) from exc


def version_dataset(
    df, output_path: str = "data/training_dataset.csv", push: bool = True
) -> str:
    """
    Exporte le jeu de données vers un fichier, le versionne avec DVC,
    et retourne le hash correspondant à cette version exacte.

    `push=False` : versionne en local sans contacter le remote SSH (tests,
    machine hors réseau).
    """
    target = (DVC_ROOT / output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)

    _run_dvc("add", str(target))
    if push:
        _run_dvc("push", str(target))

    meta = yaml.safe_load(Path(f"{target}.dvc").read_text())
    return meta["outs"][0]["md5"]
