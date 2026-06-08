@echo off
setlocal enabledelayedexpansion
title MoneyPrinterTurbo Launcher

set "CURRENT_DIR=%CD%"

rem =============================================================================
rem 1. Detect runtime: .venv > uv > system Python
rem =============================================================================
set "LAUNCHER="

if exist "%CURRENT_DIR%\.venv\Scripts\python.exe" (
    set "LAUNCHER=venv"
    set "PYTHON=%CURRENT_DIR%\.venv\Scripts\python.exe"
    goto :detect_done
)

where uv >nul 2>nul
if not errorlevel 1 (
    if exist "%CURRENT_DIR%\uv.lock" (
        set "LAUNCHER=uv"
        goto :detect_done
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    echo ***** Warning: using system Python. Run "uv sync" first. *****
    set "LAUNCHER=system"
    set "PYTHON=python"
    goto :detect_done
)

echo ***** ERROR: No Python environment found. *****
echo ***** Install uv: https://docs.astral.sh/uv/ *****
echo ***** Then run: uv sync *****
pause
exit /b 1

:detect_done
echo ======================================
echo   MoneyPrinterTurbo v1.2.9
echo   Launcher: !LAUNCHER!
echo ======================================

rem =============================================================================
rem 2. Port configuration
rem =============================================================================
set "API_PORT=8080"
if not defined MPT_WEBUI_HOST set "MPT_WEBUI_HOST=127.0.0.1"
if not defined MPT_WEBUI_PORT set "MPT_WEBUI_PORT=8501"

rem =============================================================================
rem 3. Check API port (via start_helper.py)
rem =============================================================================
set "API_PORT_STATUS=free"
!PYTHON! "%CURRENT_DIR%\start_helper.py" check 127.0.0.1 !API_PORT!
if not errorlevel 1 set "API_PORT_STATUS=taken"

rem =============================================================================
rem 4. Find free WebUI port (via start_helper.py)
rem =============================================================================
set "SELECTED_WEBUI_PORT="
for /f "usebackq delims=" %%P in (`!PYTHON! "%CURRENT_DIR%\start_helper.py" find !MPT_WEBUI_HOST! !MPT_WEBUI_PORT! 8599`) do set "SELECTED_WEBUI_PORT=%%P"

if not defined SELECTED_WEBUI_PORT (
    echo ***** ERROR: No available WebUI port found. *****
    pause
    exit /b 1
)

if not "!SELECTED_WEBUI_PORT!"=="!MPT_WEBUI_PORT!" (
    echo ***** Port !MPT_WEBUI_PORT! is busy, using !SELECTED_WEBUI_PORT!. *****
)
set "MPT_WEBUI_PORT=!SELECTED_WEBUI_PORT!"

rem =============================================================================
rem 5. Start API (background window)
rem =============================================================================
if "!API_PORT_STATUS!"=="taken" (
    echo [API] Port !API_PORT! is already in use -- skipping.
) else (
    echo [API] Starting on http://127.0.0.1:!API_PORT! ...
    if "!LAUNCHER!"=="uv" (
        start "MoneyPrinterTurbo-API" /MIN cmd /c "cd /d !CURRENT_DIR! && uv run python main.py"
    ) else (
        start "MoneyPrinterTurbo-API" /MIN cmd /c "cd /d !CURRENT_DIR! && !PYTHON! main.py"
    )
    timeout /t 3 /nobreak >nul
)

rem =============================================================================
rem 6. Start WebUI (foreground)
rem =============================================================================
echo.
echo [WebUI] Starting on http://!MPT_WEBUI_HOST!:!MPT_WEBUI_PORT! ...
echo ======================================
echo   API:    http://127.0.0.1:!API_PORT!
echo   Docs:   http://127.0.0.1:!API_PORT!/docs
echo   WebUI:  http://!MPT_WEBUI_HOST!:!MPT_WEBUI_PORT!
echo ======================================
echo.
echo Press Ctrl+C to stop WebUI. API window can be closed separately.
echo.

set "PYTHONPATH=!CURRENT_DIR!"
if "!LAUNCHER!"=="uv" (
    uv run streamlit run "%CURRENT_DIR%\webui\Main.py" --server.address=!MPT_WEBUI_HOST! --server.port=!MPT_WEBUI_PORT! --browser.serverAddress=!MPT_WEBUI_HOST! --browser.gatherUsageStats=False --server.enableCORS=True
) else (
    !PYTHON! -m streamlit run "%CURRENT_DIR%\webui\Main.py" --server.address=!MPT_WEBUI_HOST! --server.port=!MPT_WEBUI_PORT! --browser.serverAddress=!MPT_WEBUI_HOST! --browser.gatherUsageStats=False --server.enableCORS=True
)

echo.
echo ***** WebUI stopped. *****
pause
