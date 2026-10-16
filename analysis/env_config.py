"""Environment and path configuration for Matrix Factory Twin analysis scripts.

Resolution order for paths:
1. Local uncommitted overrides from ``analysis/local_config.py`` (git-ignored).
2. Environment variables (``OMNETPP_ROOT``, ``INET_ROOT``, ``OMNETPP_ENV``).
3. Colocated ``inet-workspace`` discovery, then ``~/omnetpp-6.4.0`` fallback.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 1. Project root is ALWAYS auto-detected relative to this file (zero-config)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = PROJECT_ROOT / "simulations"

# 2. Defaults: colocated opp_env workspace when present, otherwise ~/omnetpp-6.4.0
_workspace_omnetpp = PROJECT_ROOT.parent.parent / "inet-workspace" / "omnetpp-6.4.0"
DEFAULT_OMNETPP = _workspace_omnetpp if _workspace_omnetpp.exists() else Path.home() / "omnetpp-6.4.0"
DEFAULT_INET = DEFAULT_OMNETPP / "samples" / "inet-4.7.0"
if (_workspace_omnetpp.parent / "inet-4.7.0").exists():
    DEFAULT_INET = _workspace_omnetpp.parent / "inet-4.7.0"
DEFAULT_ENV = DEFAULT_OMNETPP / "setenv"

# 3. Read environment variables first, falling back to home defaults
OMNETPP_ROOT = Path(os.environ.get("OMNETPP_ROOT") or os.environ.get("OMNETPP_DIR") or DEFAULT_OMNETPP)
INET_ROOT = Path(os.environ.get("INET_ROOT") or DEFAULT_INET)
OMNETPP_ENV = Path(os.environ.get("OMNETPP_ENV") or OMNETPP_ROOT / "setenv")

# 4. Optional local overrides from git-ignored local_config.py (if it exists)
_local_cfg = None
try:
    from . import local_config as _local_cfg  # type: ignore
except (ImportError, ValueError):
    try:
        import local_config as _local_cfg  # type: ignore
    except ImportError:
        pass

if _local_cfg is not None:
    if hasattr(_local_cfg, "PROJECT_ROOT"):
        PROJECT_ROOT = Path(_local_cfg.PROJECT_ROOT)
        SIM_DIR = PROJECT_ROOT / "simulations"
    if hasattr(_local_cfg, "OMNETPP_ROOT"):
        OMNETPP_ROOT = Path(_local_cfg.OMNETPP_ROOT)
    if hasattr(_local_cfg, "INET_ROOT"):
        INET_ROOT = Path(_local_cfg.INET_ROOT)
    if hasattr(_local_cfg, "OMNETPP_ENV"):
        OMNETPP_ENV = Path(_local_cfg.OMNETPP_ENV)

# String representations for shell commands and legacy path operations
PROJECT_ROOT_STR = str(PROJECT_ROOT)
SIM_DIR_STR = str(SIM_DIR)
OMNETPP_ROOT_STR = str(OMNETPP_ROOT)
INET_ROOT_STR = str(INET_ROOT)
OMNETPP_ENV_STR = str(OMNETPP_ENV)
MATRIXFACTORY_LIB = Path(os.environ.get("MATRIXFACTORY_LIB") or PROJECT_ROOT / "matrixfactory")
if _local_cfg is not None and hasattr(_local_cfg, "MATRIXFACTORY_LIB"):
    MATRIXFACTORY_LIB = Path(_local_cfg.MATRIXFACTORY_LIB)
MATRIXFACTORY_LIB_STR = str(MATRIXFACTORY_LIB)
