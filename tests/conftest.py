"""Make `main` importable; route `tmp_path` through pyfakefs so all I/O is in-memory."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force pre-import of `main` (and its deps) on REAL filesystem, before any
# pyfakefs activation, so guessit's bundled regex/yaml data is loaded.
import main  # noqa: E402,F401


@pytest.fixture
def tmp_path(fs) -> Path:  # type: ignore[override]
    """Override the built-in tmp_path with a fake-filesystem directory."""
    p = Path("/fake_tmp")
    fs.create_dir(p)
    return p
