"""Runtime path configuration shared by local and hosted read-only services."""

from __future__ import annotations

import os
import json
from pathlib import Path


def project_root() -> Path:
    """Return the application root, including when the package is installed."""
    configured = os.environ.get("STOCK_RANKER_PROJECT_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]


PROJECT_ROOT = project_root()
VALIDATED_RELEASE_STATE = PROJECT_ROOT / "release/validated_state_20260920.json"


def data_root() -> Path:
    """Return the explicit evidence root, defaulting to the repository data tree."""
    configured = os.environ.get("STOCK_RANKER_DATA_ROOT")
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "data"


def research_root() -> Path:
    """Return the explicit research-artifact root, defaulting to the repository tree."""
    configured = os.environ.get("STOCK_RANKER_RESEARCH_ROOT")
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "research"


def validated_release() -> dict:
    """Load the immutable release identity committed with the application."""
    return json.loads(VALIDATED_RELEASE_STATE.read_text(encoding="utf-8"))
