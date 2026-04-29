"""Route `tmp_path` through pyfakefs so all I/O is in-memory."""
from __future__ import annotations

from pathlib import Path

import pytest

# Force pre-import on REAL filesystem before any pyfakefs activation,
# so guessit's bundled regex/yaml data is loaded into memory.
import dedupe_episodes  # noqa: F401


@pytest.fixture
def tmp_path(fs) -> Path:  # type: ignore[override]
    """Override the built-in tmp_path with a fake-filesystem directory."""
    p = Path("/fake_tmp")
    fs.create_dir(p)
    return p
