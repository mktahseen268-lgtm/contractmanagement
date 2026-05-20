@echo off
REM ============================================================
REM  Contract Management — start WITHOUT Docker
REM ============================================================
REM  Runs the API on SQLite + local-file storage + inline Celery
REM  (no Postgres, no Redis, no MinIO needed). Opens two windows:
REM     1) API   -> http://localhost:8000   (uvicorn, auto-reload)
REM     2) Web   -> http://localhost:3000   (next dev)
REM
REM  Login:  demo@acme.io / demo1234   (auto-seeded on first start)
REM
REM  Requires: the Python venv at apps\api\.venv and apps\web\node_modules
REM  (both already present in this checkout). To recreate them, see README.
REM ============================================================

setlocal
set "ROOT=%~dp0"

REM --- sanity checks -----------------------------------------------------
if not exist "%ROOT%apps\api\.venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found at apps\api\.venv
    echo         Create it:  cd apps\api ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist "%ROOT%apps\web\node_modules\.bin\next.cmd" (
    if not exist "%ROOT%apps\web\node_modules\.bin\next" (
        echo [ERROR] Web dependencies not installed.
        echo         Install them:  cd apps\web ^&^& npm install
        pause
        exit /b 1
    )
)

echo.
echo === Starting Contract Management (no Docker) ===
echo.
echo   API      : http://localhost:8000      (docs at /docs)
echo   Web UI   : http://localhost:3000
echo   Storage  : local filesystem (apps\api\storage)
echo   Database : SQLite (apps\api\cm.db)
echo.
echo   Login    : demo@acme.io / demo1234
echo   Others   : manager@acme.io, approver@acme.io, author@acme.io  (same password)
echo.
echo   Two windows will open (API + Web). Close them to stop, or run stop-local.bat.
echo.

REM --- API window -------------------------------------------------------
REM SQLite + local storage + eager Celery = zero external services.
start "CM API (8000)" cmd /k "cd /d "%ROOT%apps\api" && set "DATABASE_URL=sqlite:///./cm.db" && set "ENV=dev" && set "AUTO_SEED=true" && set "RUN_MIGRATIONS_ON_STARTUP=true" && set "CELERY_TASK_ALWAYS_EAGER=true" && set "RATE_LIMIT_STORE=memory" && set "EMAIL_BACKEND=console" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

REM --- Web window -------------------------------------------------------
start "CM Web (3000)" cmd /k "cd /d "%ROOT%apps\web" && set "NEXT_PUBLIC_API_URL=http://localhost:8000" && npm run dev"

echo Both windows launched. The Web UI will be ready at http://localhost:3000 in ~15-30 seconds.
echo (The API seeds the demo workspace on its first start — watch the API window for "Seeded demo workspace".)
echo.

endlocal
