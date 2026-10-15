import sys
from pathlib import Path

# Prevent incompatible C-extensions in /usr/lib/python3/dist-packages (compiled for numpy 1.x)
# from breaking pandas when user has numpy 2.x installed.
sys.modules["bottleneck"] = None
sys.modules["numexpr"] = None

# Add analysis directory to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "analysis"))
sys.path.insert(0, str(repo_root))
