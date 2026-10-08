@echo off
title KORA Launcher
cd /d "%~dp0"

REM If the server is already running, skip straight to the browser.
for /f %%s in ('curl.exe -s -o nul -w "%%{http_code}" http://localhost:3000') do set HTTP=%%s
if "%HTTP%"=="200" (
    echo KORA is already running.
    start http://localhost:3000
    exit /b 0
)

echo Starting KORA... first launch takes ~20 seconds for type-checking.

REM Start the Node server fully hidden and detached.
REM The server auto-spawns the Python desktop agent on boot (venv interpreter
REM from ELYSIA_PYTHON in .env), so no extra agent process or window is needed.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm.cmd run dev > logs_node_out.txt 2> logs_node_err.txt' -WorkingDirectory '%~dp0.' -WindowStyle Hidden" 2>nul

set /a TRIES=0
:wait
ping -n 3 127.0.0.1 >nul
set /a TRIES+=1
for /f %%s in ('curl.exe -s -o nul -w "%%{http_code}" http://localhost:3000') do set HTTP=%%s
if "%HTTP%"=="200" goto serverup
if %TRIES% geq 40 goto failed
goto wait

:serverup
echo Server is up. Waiting for the desktop agent...
set /a ATRIES=0
:waitagent
for /f %%s in ('curl.exe -s -o nul -w "%%{http_code}" http://localhost:8765/health') do set AHTTP=%%s
if "%AHTTP%"=="200" goto ready
set /a ATRIES+=1
if %ATRIES% geq 15 goto degraded
ping -n 3 127.0.0.1 >nul
goto waitagent

:ready
echo.
echo KORA is ready: http://localhost:3000
start http://localhost:3000
exit /b 0

:degraded
echo.
echo KORA is up, but the desktop agent did not start within ~30s.
echo Desktop control may be unavailable. Check logs_node_err.txt
start http://localhost:3000
exit /b 0

:failed
echo.
echo KORA failed to start. See logs_node_err.txt
pause
exit /b 1