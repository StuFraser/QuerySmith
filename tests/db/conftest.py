import pytest


class FakeCursor:
    """Minimal pyodbc-cursor-shaped double. `result_sets` is a list of
    (description, rows) pairs walked in order via execute()+nextset(),
    mirroring how SQL Server returns one result set per statement in a
    batch (SET STATISTICS ON/OFF produce none; SELECT-shaped statements
    produce one)."""

    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self._index = -1
        self._rows_iter = iter(())
        self.description = None
        self.executed_statements = []
        self.raise_on_execute = None

    def execute(self, statement, *params):
        self.executed_statements.append(statement)
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        self._index = -1
        self._advance()

    def _advance(self):
        self._index += 1
        if self._index < len(self._result_sets):
            description, rows = self._result_sets[self._index]
            self.description = description
            self._rows_iter = iter(rows)
        else:
            self.description = None
            self._rows_iter = iter(())

    def fetchone(self):
        return next(self._rows_iter, None)

    def nextset(self):
        if self._index + 1 < len(self._result_sets):
            self._advance()
            return True
        self.description = None
        return False


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.timeout = None

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture
def fake_cursor_factory():
    return FakeCursor


@pytest.fixture
def fake_connection_factory():
    return FakeConnection
