@echo off
REM ============================================================
REM  Contract Management — start everything (Docker Compose)
REM ============================================================
REM  Brings up: postgres + redis + minio + api + worker + web.
REM  First run takes ~3-5 minutes (image pulls + builds).
REM  Subsequent runs are ~10-20 seconds.
REM
REM  When ready, open: http://localhost:3000
REM  Login:            demo@acme.io   /   demo1234
REM ============================================================

setlocal

where docker >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker is not installed or not on PATH.
    echo         Install Docker Desktop from https://docker.com/products/docker-desktop
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker daemon is not running.
    echo.
    echo   Two ways to fix this:
    echo     1^) Start Docker Desktop, wait for it to say "Engine running", then rerun start.bat
    echo     2^) Skip Docker entirely — run start-local.bat instead
    echo        ^(SQLite + local storage, no Postgres/Redis/MinIO needed^)
    echo.
    choice /M "Launch the no-Docker version (start-local.bat) now"
    if errorlevel 2 exit /b 1
    call "%~dp0start-local.bat"
    exit /b 0
)

echo.
echo === Starting Contract Management stack ===
echo.
echo   Web UI    : http://localhost:3000
echo   API       : http://localhost:8000
echo   API docs  : http://localhost:8000/docs
echo   MinIO UI  : http://localhost:9001  (login: minioadmin / minioadmin)
echo   Postgres  : localhost:5432  (cm / cm)
echo   Redis     : localhost:6379
echo.
echo   Login     : demo@acme.io / demo1234   (auto-seeded on first start)
echo   Other users (same password): manager@acme.io, approver@acme.io, author@acme.io
echo.
echo   To stop : run stop.bat
echo   To tail : docker compose logs -f
echo.

docker compose up --build -d
if errorlevel 1 (
    echo.
    echo [ERROR] docker compose up failed.
    exit /b 1
)

echo.
echo === Stack is starting in the background ===
echo Run "docker compose logs -f api" to watch the API boot (migrations + seed).
echo Web UI will be ready at http://localhost:3000 in ~30 seconds.
echo.

endlocal
