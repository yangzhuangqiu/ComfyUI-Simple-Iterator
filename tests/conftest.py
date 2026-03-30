import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("SIMPLE_ITERATOR_SKIP_NODE_IMPORT", "1")


def pytest_ignore_collect(collection_path, config):
    """Ignore project root __init__.py to avoid importing runtime deps in core tests."""
    try:
        path = Path(str(collection_path)).resolve()
    except OSError:
        return False
    return path == (PROJECT_ROOT / "__init__.py").resolve()
