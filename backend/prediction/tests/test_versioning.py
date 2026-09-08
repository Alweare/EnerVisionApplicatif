"""
Tests du versioning DVC du jeu d'entraînement (EN-44).

`dvc` n'est jamais réellement appelé : `subprocess.run` est monkeypatché. On
vérifie le pilotage de la commande, le parsing du `.dvc` et la remontée d'erreur.
"""

import subprocess

import pandas as pd
import pytest

from prediction.dataset import versioning
from prediction.dataset.versioning import DatasetVersioningError, version_dataset

# Contenu type d'un .dvc généré par DVC 3.x : deux lignes contiennent "md5",
# seule `- md5:` porte le digest.
DVC_FILE = """\
outs:
- md5: e3b0c44298fc1c149afbf4c8996fb924
  size: 20
  hash: md5
  path: training_dataset.csv
"""

EXPECTED_HASH = "e3b0c44298fc1c149afbf4c8996fb924"


def _dvc_subcommand(cmd):
    """De `[python, -m, dvc, add, path]` -> `add`."""
    return cmd[cmd.index("dvc") + 1]


@pytest.fixture
def dvc_root(tmp_path, monkeypatch):
    """Redirige le dépôt DVC vers un dossier temporaire."""
    monkeypatch.setattr(versioning, "DVC_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def fake_df():
    return pd.DataFrame({"a": [1, 2], "b": [3, 4]})


def _fake_dvc(dvc_root, calls, *, add_writes_dvc_file=True):
    """
    Remplaçant de subprocess.run : enregistre les appels et simule l'effet de
    `dvc add` (écriture du fichier .dvc à côté de la cible).
    """
    def run(cmd, **kwargs):
        calls.append(cmd)
        if add_writes_dvc_file and _dvc_subcommand(cmd) == "add":
            (dvc_root / "data").mkdir(parents=True, exist_ok=True)
            (dvc_root / "data" / "training_dataset.csv.dvc").write_text(DVC_FILE)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return run


def test_returns_hash_from_dvc_file(dvc_root, fake_df, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_dvc(dvc_root, calls))

    result = version_dataset(fake_df)

    assert result == EXPECTED_HASH
    assert (dvc_root / "data" / "training_dataset.csv").read_text().startswith("a,b")
    assert [_dvc_subcommand(c) for c in calls] == ["add", "push"]


def test_push_false_skips_remote(dvc_root, fake_df, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_dvc(dvc_root, calls))

    version_dataset(fake_df, push=False)

    assert [_dvc_subcommand(c) for c in calls] == ["add"]


def test_missing_dvc_binary_raises_versioning_error(dvc_root, fake_df, monkeypatch):
    def run(cmd, **kwargs):
        raise FileNotFoundError("dvc")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatasetVersioningError, match="introuvable"):
        version_dataset(fake_df)


def test_dvc_failure_bubbles_up_with_stderr(dvc_root, fake_df, monkeypatch):
    def run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="ERROR: remote unreachable")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatasetVersioningError, match="remote unreachable"):
        version_dataset(fake_df)
