@echo off
REM ============================================================
REM  Contract Management — stop the no-Docker (local) processes
REM ============================================================
REM  Kills the uvicorn (API) and next dev (Web) processes started
REM  by start-local.bat. Your SQLite DB (apps\api\cm.db) and any
REM  uploaded files are preserved.
REM
REM  To wipe the local DB for a fresh demo:  stop-local.bat --wipe
REM ============================================================

setlocal
set "ROOT=%~dp0"

echo Stopping local API + Web processes...

REM Close the named console windows opened by start-local.bat.
taskkill /FI "WINDOWTITLE eq CM API (8000)*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq CM Web (3000)*" /T /F >nul 2>nul

REM Belt-and-suspenders: kill anything still bound to 8000 / 3000.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3000 " ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>nul

echo Stopped.

if /i "%1"=="--wipe" goto WIPE
if /i "%1"=="-w"     goto WIPE
goto END

:WIPE
echo.
echo Wiping local SQLite DB (apps\api\cm.db) for a fresh demo workspace...
del /q "%ROOT%apps\api\cm.db" >nul 2>nul
del /q "%ROOT%apps\api\cm.db-journal" >nul 2>nul
echo Done. Next start-local.bat will reseed the demo workspace.

:END
endlocal
