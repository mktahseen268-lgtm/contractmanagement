"""Per-dialect SQL for the handful of places this app cannot stay dialect-neutral.

The MMBL deployment profile is on-prem, single-tenant, with "Database preferably Oracle or
MSSQL server". Everything that used to assume PostgreSQL — RLS policies, the tenant GUC, the
audit-chain advisory lock, JSONB/GIN, full-text search — is funnelled through this module so a
new dialect is one place to edit rather than a grep across migrations and services.

DDL helpers return **lists of SQL strings** so both Alembic (`op.execute`) and the runtime
(`Session.execute(text(...))`) can drive them. Runtime helpers that need bind parameters take a
connection/session and execute directly.

Support status:
  postgresql — production target, fully tested.
  mssql      — production target, tested in CI (see tests/conftest.py DB matrix).
  oracle     — production target. DDL is written to spec but exercised only where an Oracle
               container is available; see `docs/25-database-portability.md`.
  sqlite     — local dev only. Isolation degrades to the repository-layer tenant filter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy import text

PG = "postgresql"
MSSQL = "mssql"
ORACLE = "oracle"
SQLITE = "sqlite"

#: PostgreSQL GUC / MSSQL SESSION_CONTEXT key / Oracle application-context attribute.
TENANT_GUC = "app.cm_tenant"
_MSSQL_KEY = "cm_tenant"
_ORACLE_CTX = "CM_CTX"
_ORACLE_ATTR = "TENANT_ID"

_MSSQL_PREDICATE_FN = "dbo.fn_cm_tenant_predicate"
_ORACLE_PREDICATE_FN = "CM_TENANT_PREDICATE"


def _mssql_policy_name(table: str) -> str:
    """One security policy per table — see the note in `enable_row_security`."""
    return f"dbo.cm_tenant_policy_{table}"


def dialect_of(bind) -> str:  # type: ignore[no-untyped-def]
    """Dialect name for a Connection / Engine / Alembic bind."""
    return bind.dialect.name


def quote(dialect: str, ident: str) -> str:
    if dialect == MSSQL:
        return f"[{ident}]"
    if dialect == ORACLE:
        return ident.upper()
    return f'"{ident}"'


# --------------------------------------------------------------------------------------
# Row-level security
# --------------------------------------------------------------------------------------
# Semantics are identical on all three engines and match the original Postgres policy:
# when the tenant context is UNSET the predicate is permissive (so unauthenticated
# /auth/login and /auth/refresh still work); when it is set, rows are filtered to it.


def enable_row_security(dialect: str, tables: Iterable[str]) -> list[str]:
    tables = list(tables)
    if dialect == PG:
        expr = f"coalesce(current_setting('{TENANT_GUC}', true), '') in ('', tenant_id)"
        out: list[str] = []
        for t in tables:
            q = quote(PG, t)
            out += [
                f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY",
                f"CREATE POLICY tenant_isolation ON {q} USING ({expr}) WITH CHECK ({expr})",
            ]
        return out

    if dialect == MSSQL:
        # An inline table-valued function is the only predicate form a Security Policy accepts.
        sess = f"CAST(SESSION_CONTEXT(N'{_MSSQL_KEY}') AS NVARCHAR(64))"
        fn = (
            f"CREATE OR ALTER FUNCTION {_MSSQL_PREDICATE_FN}(@tenant_id NVARCHAR(64))\n"
            "RETURNS TABLE WITH SCHEMABINDING AS RETURN\n"
            "  SELECT 1 AS cm_visible\n"
            f"  WHERE {sess} IS NULL OR {sess} = N'' OR {sess} = @tenant_id"
        )
        # One policy PER TABLE, not one policy listing every table. Migrations add tables
        # incrementally (0002 the core schema, 0016 the PKI, …) and a security policy name can
        # only be created once — a shared policy would make the second migration fail. Separate
        # policies are independently creatable and droppable.
        out = [fn]
        for t in tables:
            tq = f"dbo.{quote(MSSQL, t)}"
            out.append(
                f"CREATE SECURITY POLICY {_mssql_policy_name(t)}\n"
                f"  ADD FILTER PREDICATE {_MSSQL_PREDICATE_FN}(tenant_id) ON {tq},\n"
                f"  ADD BLOCK PREDICATE {_MSSQL_PREDICATE_FN}(tenant_id) ON {tq} AFTER INSERT,\n"
                f"  ADD BLOCK PREDICATE {_MSSQL_PREDICATE_FN}(tenant_id) ON {tq} AFTER UPDATE\n"
                "  WITH (STATE = ON)"
            )
        return out

    if dialect == ORACLE:
        # Application context + VPD policy per table. Returning NULL from the policy function
        # means "no predicate", i.e. permissive — the Postgres unset-GUC behaviour.
        ctx_ref = f"SYS_CONTEXT('{_ORACLE_CTX}', '{_ORACLE_ATTR}')"
        out = [
            f"CREATE OR REPLACE CONTEXT {_ORACLE_CTX} USING CM_CTX_PKG",
            "CREATE OR REPLACE PACKAGE CM_CTX_PKG AS\n"
            "  PROCEDURE SET_TENANT(P_TENANT IN VARCHAR2);\n"
            "END CM_CTX_PKG;",
            "CREATE OR REPLACE PACKAGE BODY CM_CTX_PKG AS\n"
            "  PROCEDURE SET_TENANT(P_TENANT IN VARCHAR2) IS\n"
            "  BEGIN\n"
            f"    DBMS_SESSION.SET_CONTEXT('{_ORACLE_CTX}', '{_ORACLE_ATTR}', P_TENANT);\n"
            "  END;\n"
            "END CM_CTX_PKG;",
            f"CREATE OR REPLACE FUNCTION {_ORACLE_PREDICATE_FN}(P_SCHEMA IN VARCHAR2, P_OBJECT IN VARCHAR2)\n"
            "RETURN VARCHAR2 AS\n"
            "BEGIN\n"
            f"  IF {ctx_ref} IS NULL OR {ctx_ref} = ' ' THEN\n"
            "    RETURN NULL;\n"
            "  END IF;\n"
            # The predicate is returned as *text* that Oracle appends to the query, so the
            # inner quotes have to survive as PL/SQL-escaped doubles.
            f"  RETURN 'tenant_id = SYS_CONTEXT(''{_ORACLE_CTX}'', ''{_ORACLE_ATTR}'')';\n"
            "END;",
        ]
        for t in tables:
            out.append(
                "BEGIN DBMS_RLS.ADD_POLICY("
                "object_schema => USER, "
                f"object_name => '{t.upper()}', "
                f"policy_name => 'CM_TENANT_{t.upper()}', "
                "function_schema => USER, "
                f"policy_function => '{_ORACLE_PREDICATE_FN}', "
                "statement_types => 'SELECT,INSERT,UPDATE,DELETE', "
                "update_check => TRUE); END;"
            )
        return out

    return []  # sqlite


def disable_row_security(dialect: str, tables: Iterable[str]) -> list[str]:
    tables = list(tables)
    if dialect == PG:
        out: list[str] = []
        for t in tables:
            q = quote(PG, t)
            out += [
                f"DROP POLICY IF EXISTS tenant_isolation ON {q}",
                f"ALTER TABLE {q} NO FORCE ROW LEVEL SECURITY",
                f"ALTER TABLE {q} DISABLE ROW LEVEL SECURITY",
            ]
        return out
    if dialect == MSSQL:
        # The predicate function is shared, so it can only be dropped once every policy that
        # references it is gone. Callers drop their own tables; the function is left in place
        # (harmless, and dropping it would break any policy another migration still owns).
        return [f"DROP SECURITY POLICY IF EXISTS {_mssql_policy_name(t)}" for t in tables]
    if dialect == ORACLE:
        return [
            "BEGIN DBMS_RLS.DROP_POLICY(object_schema => USER, "
            f"object_name => '{t.upper()}', policy_name => 'CM_TENANT_{t.upper()}'); "
            "EXCEPTION WHEN OTHERS THEN NULL; END;"
            for t in tables
        ]
    return []


# --------------------------------------------------------------------------------------
# Tenant session context (runtime — called on every transaction from database.py)
# --------------------------------------------------------------------------------------


def set_tenant_context(conn, dialect: str, tenant_id: str | None) -> None:  # type: ignore[no-untyped-def]
    """Bind (or clear) the tenant on the current connection/transaction.

    Clearing matters: MSSQL SESSION_CONTEXT and Oracle application contexts are
    *connection*-scoped, so a pooled connection would otherwise carry the previous request's
    tenant into the next request. Postgres `set_config(..., is_local => true)` is
    transaction-scoped and resets itself, but we write the empty string anyway so all three
    paths behave identically.
    """
    value = tenant_id or ""
    if dialect == PG:
        conn.exec_driver_sql(f"SELECT set_config('{TENANT_GUC}', %s, true)", (value,))
    elif dialect == MSSQL:
        conn.exec_driver_sql(f"EXEC sp_set_session_context @key = N'{_MSSQL_KEY}', @value = ?", (value,))
    elif dialect == ORACLE:
        # A blank (not NULL) value is the "unset" sentinel — DBMS_SESSION.SET_CONTEXT with a
        # NULL value is a no-op on some versions, which would leave the old tenant in place.
        conn.exec_driver_sql("BEGIN CM_CTX_PKG.SET_TENANT(:1); END;", (value or " ",))


# --------------------------------------------------------------------------------------
# Advisory locks (the audit hash chain serialises per-tenant inserts on these)
# --------------------------------------------------------------------------------------


def advisory_lock(db, dialect: str, key: str) -> None:  # type: ignore[no-untyped-def]
    """Take a transaction-scoped exclusive lock named `key`. Released on commit/rollback."""
    if dialect == PG:
        n = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:n)"), {"n": n})
    elif dialect == MSSQL:
        db.execute(
            text("EXEC sp_getapplock @Resource = :r, @LockMode = 'Exclusive', @LockOwner = 'Transaction'"),
            {"r": key[:255]},
        )
    elif dialect == ORACLE:
        # ALLOCATE_UNIQUE maps the name to a numeric handle; REQUEST mode 6 is exclusive, and
        # release_on_commit makes it transaction-scoped like the other two.
        db.execute(
            text(
                "DECLARE v_handle VARCHAR2(128); v_rc INTEGER; BEGIN "
                "DBMS_LOCK.ALLOCATE_UNIQUE(:r, v_handle); "
                "v_rc := DBMS_LOCK.REQUEST(lockhandle => v_handle, lockmode => 6, "
                "timeout => 10, release_on_commit => TRUE); END;"
            ),
            {"r": key[:128]},
        )
    # sqlite: the engine is single-writer, the BEGIN…COMMIT cycle already serialises.


# --------------------------------------------------------------------------------------
# JSON columns
# --------------------------------------------------------------------------------------


def json_column(dialect: str):  # type: ignore[no-untyped-def]
    """Column type for a JSON document. SQLAlchemy's generic JSON already renders
    NVARCHAR(MAX) on MSSQL and CLOB on Oracle; only Postgres needs the JSONB upgrade."""
    if dialect == PG:
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB
    return sa.JSON


def json_check(dialect: str, table: str, column: str) -> list[str]:
    """Constrain a JSON column to actual JSON on the engines that do not type it natively."""
    if dialect == MSSQL:
        col = quote(MSSQL, column)
        return [
            f"ALTER TABLE {quote(MSSQL, table)} ADD CONSTRAINT ck_{table}_{column}_json "
            f"CHECK ({col} IS NULL OR ISJSON({col}) = 1)"
        ]
    if dialect == ORACLE:
        return [
            f"ALTER TABLE {quote(ORACLE, table)} ADD CONSTRAINT ck_{table}_{column}_json "
            f"CHECK ({quote(ORACLE, column)} IS JSON)"
        ]
    return []


def json_index(
    dialect: str, table: str, column: str, *, key: str | None = None, name: str | None = None
) -> list[str]:
    """Index for containment/lookup on a JSON column.

    `key` names the scalar member to index on MSSQL/Oracle, which cannot index a whole
    document the way a GIN index can. When it is None those engines get nothing — say so
    rather than pretending the index exists.
    """
    name = name or f"ix_{table}_{column}_json"
    if dialect == PG:
        return [f"CREATE INDEX IF NOT EXISTS {name} ON {quote(PG, table)} USING GIN ({quote(PG, column)})"]
    if key is None:
        return []
    if dialect == MSSQL:
        col = f"cm_{column}_{key}"
        return [
            f"ALTER TABLE {quote(MSSQL, table)} ADD {col} AS "
            f"CAST(JSON_VALUE({quote(MSSQL, column)}, '$.{key}') AS NVARCHAR(400))",
            f"CREATE INDEX {name} ON {quote(MSSQL, table)} ({col})",
        ]
    if dialect == ORACLE:
        return [
            f"CREATE INDEX {name} ON {quote(ORACLE, table)} "
            f"(JSON_VALUE({quote(ORACLE, column)}, '$.{key}'))"
        ]
    return []


# --------------------------------------------------------------------------------------
# Partial (filtered) unique indexes
# --------------------------------------------------------------------------------------


def partial_unique_index(
    dialect: str, name: str, table: str, columns: list[str], *, where: str
) -> list[str]:
    """A uniqueness constraint that applies only to rows matching `where`.

    The PKI needs this: at most one *active* certificate per signatory, while keeping the
    full history of expired and revoked ones. (RFP: "one certificate per signatory, uniquely
    bound private key, no shared or role certificates".)

    Postgres and MSSQL both support filtered indexes directly. **Oracle does not** — the
    portable trick there is a function-based unique index that evaluates to NULL for rows
    outside the filter, because Oracle does not index all-NULL entries and therefore does not
    enforce uniqueness over them. `where` must be valid SQL on all three; keep it simple
    (a single equality is the intended shape).
    """
    cols = ", ".join(quote(dialect, c) for c in columns)
    if dialect == PG:
        return [f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {quote(PG, table)} ({cols}) WHERE {where}"]
    if dialect == MSSQL:
        return [f"CREATE UNIQUE INDEX {name} ON {quote(MSSQL, table)} ({cols}) WHERE {where}"]
    if dialect == ORACLE:
        expr = ", ".join(
            f"CASE WHEN {where} THEN {quote(ORACLE, c)} END" for c in columns
        )
        return [f"CREATE UNIQUE INDEX {name} ON {quote(ORACLE, table)} ({expr})"]
    if dialect == SQLITE:
        # SQLite has supported partial indexes since 3.8.0 — useful because the dev/test path
        # should catch a duplicate-active-certificate bug too, not only production.
        return [f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON \"{table}\" ({cols}) WHERE {where}"]
    return []


# --------------------------------------------------------------------------------------
# Full-text search  (consumed by Phase 5 — repository search)
# --------------------------------------------------------------------------------------


def fulltext_index(dialect: str, table: str, columns: list[str], *, key_index: str) -> list[str]:
    """DDL creating the search structure. `key_index` is the unique index MSSQL/Oracle
    require to anchor a full-text catalogue."""
    name = f"ix_{table}_fts"
    if dialect == PG:
        vec = " || ' ' || ".join(f"coalesce({quote(PG, c)}, '')" for c in columns)
        return [
            f"CREATE INDEX IF NOT EXISTS {name} ON {quote(PG, table)} "
            f"USING GIN (to_tsvector('english', {vec}))"
        ]
    if dialect == MSSQL:
        cols = ", ".join(quote(MSSQL, c) for c in columns)
        return [
            "IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'cm_ft_catalog') "
            "CREATE FULLTEXT CATALOG cm_ft_catalog AS DEFAULT",
            f"CREATE FULLTEXT INDEX ON {quote(MSSQL, table)} ({cols}) "
            f"KEY INDEX {key_index} ON cm_ft_catalog WITH CHANGE_TRACKING AUTO",
        ]
    if dialect == ORACLE:
        # Oracle Text needs a datastore preference to span more than one column.
        pref = f"cm_ds_{table}"
        cols = ",".join(c.upper() for c in columns)
        return [
            f"BEGIN CTX_DDL.DROP_PREFERENCE('{pref}'); EXCEPTION WHEN OTHERS THEN NULL; END;",
            f"BEGIN CTX_DDL.CREATE_PREFERENCE('{pref}', 'MULTI_COLUMN_DATASTORE'); "
            f"CTX_DDL.SET_ATTRIBUTE('{pref}', 'COLUMNS', '{cols}'); END;",
            f"CREATE INDEX {name} ON {quote(ORACLE, table)} ({quote(ORACLE, columns[0])}) "
            f"INDEXTYPE IS CTXSYS.CONTEXT PARAMETERS ('DATASTORE {pref} SYNC (ON COMMIT)')",
        ]
    return []


def fulltext_search(dialect: str, columns: list[str], param: str = "q") -> str:
    """A boolean SQL expression matching `columns` against the bound parameter `:param`.

    On SQLite (dev only) this degrades to a LIKE scan — correct, just not fast. Callers on
    that path must bind `:{param}_like` with the surrounding wildcards.
    """
    if dialect == PG:
        vec = " || ' ' || ".join(f"coalesce({quote(PG, c)}, '')" for c in columns)
        return f"to_tsvector('english', {vec}) @@ websearch_to_tsquery('english', :{param})"
    if dialect == MSSQL:
        cols = ", ".join(quote(MSSQL, c) for c in columns)
        return f"CONTAINS(({cols}), :{param})"
    if dialect == ORACLE:
        return f"CONTAINS({quote(ORACLE, columns[0])}, :{param}) > 0"
    likes = " OR ".join(f"lower(coalesce({quote(dialect, c)}, '')) LIKE :{param}_like" for c in columns)
    return f"({likes})"
