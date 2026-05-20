@echo off
REM ============================================================
REM  Contract Management — stop everything
REM ============================================================
REM  Stops all containers but KEEPS the database + uploaded files.
REM  Re-running start.bat resumes where you left off.
REM
REM  To wipe everything (fresh demo workspace next start), run:
REM      stop.bat --wipe
REM ============================================================

setlocal

if /i "%1"=="--wipe" goto WIPE
if /i "%1"=="/wipe" goto WIPE
if /i "%1"=="-w"    goto WIPE

echo.
echo === Stopping Contract Management stack ===
echo   (data preserved; rerun start.bat to resume)
echo.

docker compose down
if errorlevel 1 (
    echo [ERROR] docker compose down failed.
    exit /b 1
)
echo.
echo Stopped. Run start.bat to resume.
echo To wipe data too: stop.bat --wipe
goto END

:WIPE
echo.
echo === Stopping AND wiping all data ===
echo   This removes the DB volume, MinIO files, and Redis state.
echo   Next start will reseed the demo workspace from scratch.
echo.
choice /M "Continue"
if errorlevel 2 goto END

docker compose down -v
if errorlevel 1 (
    echo [ERROR] docker compose down -v failed.
    exit /b 1
)
echo.
echo Wiped clean. Run start.bat for a fresh demo workspace.

:END
endlocal
