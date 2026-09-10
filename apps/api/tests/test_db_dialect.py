"""The dialect seam (`app/db_dialect.py`) generates the DDL that enforces tenant isolation on
each supported engine. These are pure string tests — no database needed — because the property
that matters is *semantic equivalence across dialects*, and getting that wrong on an engine we
cannot spin up locally is exactly the failure mode this module exists to prevent.

The live behaviour on each engine is covered by the isolation tests that run under the
`postgres` / `mssql` / `oracle` markers in the CI matrix.

Requirements: TEC-04.
"""

from __future__ import annotations

import pytest

from app import db_dialect as dd

TABLES = ["users", "contracts", "audit_log"]
ENGINES = [dd.PG, dd.MSSQL, dd.ORACLE]


@pytest.mark.parametrize("dialect", ENGINES)
def test_row_security_covers_every_table(dialect):
    sql = " ".join(dd.enable_row_security(dialect, TABLES))
    for t in TABLES:
        assert t.lower() in sql.lower(), f"{dialect}: {t} has no row-security DDL"


@pytest.mark.parametrize("dialect", ENGINES)
def test_row_security_is_permissive_when_tenant_unset(dialect):
    """The single invariant all three must share: with no tenant bound, rows are visible.
    `/auth/login` and `/auth/refresh` run before a tenant is known and would break otherwise."""
    sql = " ".join(dd.enable_row_security(dialect, TABLES))
    if dialect == dd.PG:
        # coalesce(current_setting(...), '') in ('', tenant_id) — '' matches everything.
        assert "coalesce(current_setting" in sql and "in ('', tenant_id)" in sql
    elif dialect == dd.MSSQL:
        assert "IS NULL" in sql and "= N''" in sql
    else:
        assert "RETURN NULL;" in sql  # no predicate == permissive


@pytest.mark.parametrize("dialect", ENGINES)
def test_row_security_blocks_writes_not_just_reads(dialect):
    """A filter-only policy lets a tenant *write* rows tagged with someone else's id. All
    three engines must also constrain INSERT/UPDATE."""
    sql = " ".join(dd.enable_row_security(dialect, TABLES))
    if dialect == dd.PG:
        assert "WITH CHECK" in sql
    elif dialect == dd.MSSQL:
        assert "BLOCK PREDICATE" in sql and "AFTER INSERT" in sql and "AFTER UPDATE" in sql
    else:
        assert "update_check => TRUE" in sql


def test_oracle_predicate_quotes_survive_plsql():
    """The Oracle policy function returns the predicate as *text* Oracle appends to the query,
    so the inner quotes must be PL/SQL-escaped doubles. Getting this wrong yields a function
    that compiles and then fails at query time — the worst possible place to find out."""
    sql = " ".join(dd.enable_row_security(dd.ORACLE, ["users"]))
    assert "RETURN 'tenant_id = SYS_CONTEXT(''CM_CTX'', ''TENANT_ID'')';" in sql


def test_sqlite_gets_no_row_security():
    """SQLite is dev-only; isolation there is the repository-layer filter alone. Emitting DDL
    that silently does nothing would be worse than emitting none."""
    assert dd.enable_row_security(dd.SQLITE, TABLES) == []


@pytest.mark.parametrize("dialect", ENGINES)
def test_disable_row_security_is_the_inverse(dialect):
    assert dd.disable_row_security(dialect, TABLES), f"{dialect}: no teardown DDL"


@pytest.mark.parametrize("dialect", ENGINES + [dd.SQLITE])
def test_json_index_never_lies(dialect):
    """`contracts.tags` is a JSON array. Only Postgres can index it for containment, so the
    other engines must return nothing rather than an index the planner would ignore."""
    stmts = dd.json_index(dialect, "contracts", "tags")
    if dialect == dd.PG:
        assert any("GIN" in s for s in stmts)
    else:
        assert stmts == []


def test_json_index_uses_supplied_name():
    """0013_hardening already shipped `ix_contracts_tags_gin`; a renamed index would create a
    duplicate on every already-migrated database."""
    stmts = dd.json_index(dd.PG, "contracts", "tags", name="ix_contracts_tags_gin")
    assert "ix_contracts_tags_gin" in stmts[0]


@pytest.mark.parametrize("dialect", [dd.MSSQL, dd.ORACLE])
def test_json_check_constrains_untyped_json_columns(dialect):
    """MSSQL/Oracle store JSON in NVARCHAR(MAX)/CLOB, so without a check constraint the column
    accepts arbitrary text that later blows up on read."""
    sql = " ".join(dd.json_check(dialect, "contracts", "tags"))
    assert ("ISJSON" in sql) or ("IS JSON" in sql)


@pytest.mark.parametrize("dialect", ENGINES)
def test_fulltext_search_binds_the_query_parameter(dialect):
    """No string interpolation of user input into the search predicate — Phase 5 consumes this
    directly, and a `%`-formatted query here would be SQL injection in the search box."""
    expr = dd.fulltext_search(dialect, ["title", "body"], param="q")
    assert ":q" in expr


def test_fulltext_search_degrades_to_like_on_sqlite():
    expr = dd.fulltext_search(dd.SQLITE, ["title", "body"], param="q")
    assert "LIKE" in expr and ":q_like" in expr
