@echo off
setlocal EnableDelayedExpansion

rem ======================================================================
rem  Interactive installer wrapper for Azur-Scan Agent.
rem
rem  Run as Administrator. Prompts for the server URL, then calls msiexec.
rem  The MSI's CustomAction writes the URL into config.yaml, the service
rem  starts, and the agent auto-enrolls on first iteration.
rem ======================================================================

title Azur-Scan Agent installer

echo.
echo  ==================================================
echo   Azur-Scan Agent - Installer
echo  ==================================================
echo.

rem -- Admin check
net session >nul 2>&1
if errorlevel 1 (
    echo  ERROR: this installer must be run as Administrator.
    echo         Right-click install-azurscan.cmd and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

rem -- Locate MSI alongside this script
set "MSI=%~dp0azur-scan-agent-0.1.0.msi"
if not exist "%MSI%" (
    rem fall back: look for any *.msi in the same directory
    for %%F in ("%~dp0azur-scan-agent-*.msi") do set "MSI=%%F"
)
if not exist "%MSI%" (
    echo  ERROR: cannot find azur-scan-agent-*.msi next to this script.
    echo  Make sure you extracted the full ZIP and run install-azurscan.cmd from inside it.
    echo.
    pause
    exit /b 1
)

echo  MSI: "%MSI%"
echo.

rem -- Prompt for server URL
set "SERVER_URL="
:ask_url
set /p "SERVER_URL=  Enter Azur-Scan server URL (example: http://10.0.20.143:8000): "
if "!SERVER_URL!"=="" (
    echo  URL cannot be empty. Try again.
    goto ask_url
)

rem -- Strip trailing slash
if "!SERVER_URL:~-1!"=="/" set "SERVER_URL=!SERVER_URL:~0,-1!"

echo.
echo  Installing Azur-Scan Agent ...
echo  Server URL: !SERVER_URL!
echo.

rem -- Run msiexec quietly (with progress bar). /qb shows a basic progress UI;
rem    /qn would be fully silent. /norestart so the system isn't rebooted.
msiexec /i "%MSI%" SERVER_URL="!SERVER_URL!" /qb /norestart
set "RC=%ERRORLEVEL%"

echo.
if "!RC!"=="0" (
    echo  ==================================================
    echo   Installation completed successfully.
    echo  ==================================================
    echo.
    echo   Service:  AzurScanAgent  ^(starts automatically^)
    echo   Files:    C:\Program Files\AzurScan\
    echo   Logs:     C:\ProgramData\AzurScan\logs\
    echo.
    echo   The device will appear in the Azur-Scan admin UI within ~30 seconds.
) else if "!RC!"=="1625" (
    echo  ==================================================
    echo   Installation BLOCKED by Group Policy ^(error 1625^).
    echo  ==================================================
    echo   Your IT department restricts arbitrary MSI installs.
    echo   Use the portable install instead:
    echo       pwsh -ExecutionPolicy Bypass -File install.ps1
) else (
    echo  ==================================================
    echo   Installation FAILED. msiexec exit code: !RC!
    echo  ==================================================
    echo   Check the Windows Installer log:
    echo       %TEMP%\MSI*.LOG
)
echo.
pause
exit /b !RC!
