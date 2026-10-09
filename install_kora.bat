@echo off
rem =====================================================================
rem  KORA Auto-Start installer for Windows.
rem
rem  Run this once (double-click, or in a terminal):
rem      install_kora.bat
rem
rem  It registers a per-user startup entry (HKCU Run key) that silently
rem  launches KORA at every Windows login: dev server + Python desktop
rem  agent boot in the background, then the KORA tab opens.
rem
rem  To remove it later:
rem      install_kora.bat uninstall
rem =====================================================================

title KORA - Auto-Start Installer
cd /d "%~dp0"

set "RUNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "VALUE=Kora"
set "LAUNCHER=%~dp0start-kora-silent.bat"

if /i "%~1"=="uninstall" goto uninstall
if /i "%~1"=="remove"   goto uninstall

echo.
echo   KORA Auto-Start Installer
echo   ============================================
echo.
if not exist "%LAUNCHER%" (
    echo   ERROR: %LAUNCHER% not found.
    echo   Restore start-kora-silent.bat (it lives in the repo root).
    pause
    exit /b 1
)

echo   Registering KORA to start silently at Windows login...
reg add "%RUNKEY%" /v %VALUE% /t REG_SZ /d "\"cmd /c %LAUNCHER%\"" /f
echo.
echo   Verifying...
reg query "%RUNKEY%" /v %VALUE%
echo.
echo   DONE - KORA will launch silently at the next login.
echo.
echo   ONE-TIME setup in the app (per browser), so "Hey Kora" wakes her:
echo     1. Open KORA  (http://localhost:3000)
echo     2. Settings -^> switch ON  [x] Start with Windows
echo     3. Settings -^> switch ON  [x] Wake word   (phrase: "hey kora")
echo.
echo   Then just say  "Hey Kora"  and she opens and replies.
echo.
echo   To uninstall later:  install_kora.bat uninstall
echo.
pause
exit /b 0

:uninstall
echo   Removing KORA auto-start entry...
reg delete "%RUNKEY%" /v %VALUE% /f
echo.
echo   Auto-start removed. KORA still starts when you run start_kora.bat.
echo.
pause
exit /b 0