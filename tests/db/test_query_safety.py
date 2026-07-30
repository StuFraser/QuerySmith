import pytest

from querysmith.db.query_safety import QueryValidationError, validate_select_only


def test_valid_select_passes_unchanged():
    query = "SELECT * FROM dbo.QuerySmith_test1"
    assert validate_select_only(query) == query


def test_trailing_semicolon_passes():
    query = "SELECT 1;"
    assert validate_select_only(query) == query


def test_multi_statement_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("SELECT 1; DROP TABLE x")


def test_double_semicolon_still_single_statement():
    # "SELECT 1;;" parses to [Select, None] -- the None must be filtered,
    # not counted as a second statement.
    query = "SELECT 1;;"
    assert validate_select_only(query) == query


def test_insert_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("INSERT INTO t VALUES (1)")


def test_update_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("UPDATE t SET x = 1")


def test_delete_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("DELETE FROM t")


def test_exec_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("EXEC dbo.SomeProc")


def test_block_comment_obfuscation_not_treated_as_statement_boundary():
    query = "SELECT 1 /* ; DROP TABLE x */"
    assert validate_select_only(query) == query


def test_line_comment_obfuscation_not_treated_as_statement_boundary():
    query = "SELECT 1 -- ; DROP TABLE x"
    assert validate_select_only(query) == query


def test_empty_string_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("")


def test_whitespace_only_rejected():
    with pytest.raises(QueryValidationError):
        validate_select_only("   \n\t  ")


def test_garbage_input_rejected_with_wrapped_error():
    with pytest.raises(QueryValidationError):
        validate_select_only("SELEC * FORM t")


def test_module_contract():
    import querysmith.db.query_safety as module

    assert set(module.__all__) == {"validate_select_only", "QueryValidationError", "DIALECT"}
