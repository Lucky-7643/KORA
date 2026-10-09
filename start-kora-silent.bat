@echo off
rem =====================================================================
rem  KORA silent launcher - used by the Windows auto-start entry so KORA
rem  boots its servers and opens the UI automatically at login, with no
rem  lingering console window.
rem
rem  Behavior:
rem    - If the server is already responding on :3000 -> just open the UI.
rem    - Otherwise start `npm run dev` hidden (the server auto-spawns the
rem      Python desktop agent), wait until :3000 responds, then open the UI.
rem
rem  Windows launches this via: cmd /c "...\start-kora-silent.bat"
rem  (registered by install_kora.bat or KORA Settings > Start with Windows)
rem =====================================================================

cd /d "%~dp0"

rem Already running? Just open the tab. (curl.exe ships with Windows 10+.)
for /f %%s in ('curl.exe -s -o nul -w "%%{http_code}" http://localhost:3000') do set HTTP=%%s
if "%HTTP%"=="200" (
    start "" "http://localhost:3000"
    exit /b 0
)

rem Start the dev server hidden, then hand the wait + browser-open to a
rem hidden PowerShell so this console exits immediately (no flash at login).
rem `npm.cmd` is used so Windows resolves npm correctly, and the server
rem auto-spawns the Python desktop agent on boot.
start "" /B powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm.cmd run dev > logs_node_out.txt 2> logs_node_err.txt' -WorkingDirectory '%~dp0.' -WindowStyle Hidden; $ok=$false; for($i=0;$i -lt 60;$i++){ curl.exe -s -o nul http://localhost:3000 2>$null; if($LASTEXITCODE -eq 0){ $ok=$true; break }; Start-Sleep -Seconds 2 }; if($ok){ Start-Process 'http://localhost:3000' }"

exit /b 0