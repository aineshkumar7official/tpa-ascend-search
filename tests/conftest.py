import os
import sys
from pathlib import Path

import pytest

os.environ["FARE_OPTIONS"] = "off"  # tests never open a browser or reach Google
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_conn  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()
