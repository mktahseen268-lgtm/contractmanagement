# 25 · Database — PostgreSQL First, MSSQL-Ready

**Preferred database: PostgreSQL.** Reasons:

- Native **JSONB** for OCR/AI metadata (`OcrJob.result`, `Contract.tags`,
  `BackgroundJob.label`, `SignatureEvent.meta`, `Notification`, …) — indexable, queryable,
  GIN-friendly.
- Native **`tsvector` full-text search** for the contract-search v2 work item
  (today's search is `ILIKE` only; FTS is the upgrade path).
- **Row-Level Security** for multi-tenant isolation — the policy we already use is enforced
  inside the database engine itself.
- **Free, open source**, no per-core licensing.
- Mature cloud offerings: Amazon RDS / Aurora PostgreSQL, Azure Database for PostgreSQL,
  Google Cloud SQL — all support automatic Multi-AZ + PITR.
- Good OSS replication options (Patroni, pgBouncer) when self-managed.
- Strong tooling around partitioning (audit log + signature_events grow forever).

We are sticking with Postgres. **However**, some customers (defence/govt clients) standardise
on Microsoft SQL Server. The codebase is structured so that switching to MSSQL is a
deployment-time decision, not a code rewrite.

## 1. What makes the switch easy

### 1.1 SQLAlchemy ORM, not raw SQL

Every query in the codebase is built via SQLAlchemy Core / ORM constructs. There is zero
string-concatenated SQL. The dialect-specific binding is determined at connect time from
`DATABASE_URL`.

```
postgresql+psycopg2://…   → PostgreSQL
mssql+pyodbc://…          → SQL Server
sqlite:///./cm.db         → SQLite (dev fallback)
```

### 1.2 JSON column type

We use SQLAlchemy's portable `JSON` type, **not** the Postgres-specific `JSONB`. SQLAlchemy
maps `JSON` to:

- PostgreSQL → `JSONB` automatically (the right thing for us anyway);
- MSSQL → `NVARCHAR(MAX) CHECK (ISJSON(...) = 1)` (MSSQL 2016+ has native JSON queries);
- SQLite → text column.

If a customer hits a query that needs MSSQL-flavoured JSON path (`JSON_VALUE`,
`OPENJSON`), use SQLAlchemy's `cast(col, JSON())` + dialect-specific extension — see §3.

### 1.3 Migration strategy

Alembic supports MSSQL out of the box. The few Postgres-specific DDL bits in our migrations
are **conditionally executed** with `bind.dialect.name == "postgresql"` guards (RLS, GIN
indexes). On MSSQL the same migration just skips those steps and the schema still ends up
correct.

```python
# already a pattern in our migrations
if bind.dialect.name == "postgresql":
    op.execute("ALTER TABLE … ENABLE ROW LEVEL SECURITY")
```

### 1.4 The dialect helper

`apps/api/app/config.py` exposes the existing `is_postgres` property; this PR adds
`is_mssql`, `is_sqlite`, and `db_dialect` for code that needs to branch.

## 2. What gets replaced when running on MSSQL

| Concern | Postgres | MSSQL equivalent | Action |
|---|---|---|---|
| **Multi-tenant isolation** | Row-Level Security policies | **Security predicates** (Row-Level Security in SQL Server 2016+) | Mirror migration; the per-table `tenant_isolation` predicate maps 1:1 |
| **JSON storage** | JSONB | `NVARCHAR(MAX)` + CHECK ISJSON | Auto via SQLAlchemy |
| **JSON querying** | `data->>'k'` | `JSON_VALUE(data, '$.k')` | Wrap in a small `json_path()` helper in the (rare) callsites |
| **Full-text search** | `tsvector` / GIN | **Full-Text Index** (Catalog) | Choose at index-creation time — DDL only, no app change |
| **UUID PKs** | `text(32)` (our format) | `nvarchar(32)` | Auto |
| **Booleans** | `boolean` | `bit` | Auto |
| **CTEs / window funcs** | identical | identical | None |
| **Connection pool** | `psycopg2` | `pyodbc` (+ ODBC Driver 18) | Add to `requirements.txt` only if MSSQL build |
| **Timestamps** | `timestamp without time zone` (naive UTC convention) | `datetime2(7)` | Auto |
| **GUC for RLS** (`current_setting('app.cm_tenant')`) | SET LOCAL ... | **SESSION_CONTEXT('cm_tenant')** | The engine `"begin"` listener calls one of these depending on dialect — see §4 |

## 3. The portability seam

Two files:

1. **`apps/api/app/database.py`** — engine setup + the `set_request_tenant` ContextVar +
   the `"begin"` event listener. On MSSQL the listener uses
   `EXEC sys.sp_set_session_context @key=N'cm_tenant', @value=N'<tid>'` instead of
   `SELECT set_config('app.cm_tenant', %s, true)`.

2. **`apps/api/app/db_json.py`** (new helper) — exposes:
   - `json_get(col, path)` → `col["a"]["b"]` on Postgres, `JSON_VALUE(col, '$.a.b')` on MSSQL.
   - `json_path_exists(col, path)` likewise.

   These are only needed by code that queries inside JSON columns — today that's the audit log
   meta-search and a couple of report aggregates. The rest of the app treats JSON columns as
   opaque blobs via the ORM.

## 4. RLS portability — the only non-trivial piece

PostgreSQL implementation (today):

```sql
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON contracts
  USING (coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id))
  WITH CHECK (coalesce(current_setting('app.cm_tenant', true), '') in ('', tenant_id));
```

MSSQL equivalent:

```sql
CREATE FUNCTION dbo.fn_tenant_predicate(@tenant_id NVARCHAR(32))
    RETURNS TABLE WITH SCHEMABINDING
AS RETURN
    SELECT 1 AS allowed
    WHERE CAST(SESSION_CONTEXT(N'cm_tenant') AS NVARCHAR(32)) IS NULL
       OR CAST(SESSION_CONTEXT(N'cm_tenant') AS NVARCHAR(32)) = ''
       OR CAST(SESSION_CONTEXT(N'cm_tenant') AS NVARCHAR(32)) = @tenant_id;

CREATE SECURITY POLICY TenantIsolation
    ADD FILTER PREDICATE dbo.fn_tenant_predicate(tenant_id) ON dbo.contracts,
    ADD BLOCK PREDICATE  dbo.fn_tenant_predicate(tenant_id) ON dbo.contracts
        WITH (STATE = ON);
```

Both behave the same way: rows are filtered to the current session's tenant, and an attempt
to insert into the wrong tenant fails.

The Alembic migration `0002_rls` would gain an `elif bind.dialect.name == "mssql":` branch
that issues the MSSQL DDL. The application code is unchanged.

## 5. Implementation plan (when first MSSQL customer arrives)

| Step | Effort | Notes |
|---|---|---|
| Add `pyodbc + msodbcsql18` build path | 0.5 d | optional Docker build arg |
| Mirror RLS DDL in migrations 0002, 0003, 0004, 0005, 0006, 0008, 0009, 0010, 0011 | 1 d | small per-migration patches |
| Add the MSSQL branch in `database.py::_session_set_tenant` | 0.5 d | one engine event |
| Port the two JSON-path callsites to `db_json.py` helper | 0.5 d | trivial |
| CI matrix: add MSSQL job to the test pipeline | 0.5 d | uses `mcr.microsoft.com/mssql/server` container |
| Customer-side: provide TDE keys, FT-search catalog policy, backup strategy | varies | document |

**Total: ~3 dev-days** for the first MSSQL deployment, mostly DDL + CI. Subsequent customer
deployments are a config switch.

## 6. Not portable (won't try)

- **Listen / NOTIFY** (we don't use it).
- **Materialised views** (we don't use them; if we add them, we'll build MSSQL-equivalent
  indexed views).
- **`pg_crypto` column-level encryption** — if a customer mandates app-layer encryption, the
  `secrets_box` module already provides it; no DB-side counterpart needed.
