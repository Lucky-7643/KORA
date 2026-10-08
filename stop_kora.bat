@echo off
title KORA Stop
cd /d "%~dp0"

echo Stopping KORA...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%p >nul 2>&1
)

ping -n 3 127.0.0.1 >nul

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo Port 3000 still in use by PID %%p
    exit /b 1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo Port 8765 still in use by PID %%p
    exit /b 1
)

echo KORA stopped.
exit /b 0
