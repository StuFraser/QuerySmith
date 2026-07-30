import pathlib

import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent.parent.parent / "fixtures" / "sqlserver"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load
