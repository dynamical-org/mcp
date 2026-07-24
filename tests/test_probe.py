import importlib
import pathlib
import sys
from types import ModuleType

import pytest

# probe.py is a top-level Modal script at the repo root, not part of the
# installed `server` package, so add the repo root to the path to import it.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

probe: ModuleType = importlib.import_module("probe")


def test_check_mcp_tools_non_empty() -> None:
    assert probe.check_mcp_tools(["search_catalog", "get_dataset_info"]) == 2


def test_check_mcp_tools_empty() -> None:
    with pytest.raises(AssertionError, match="no tools"):
        probe.check_mcp_tools([])
