@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   StudyLoop installer
echo ============================================
echo.

REM ---- 1. Check Python ----
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python was not found.
  echo         Install Python 3.11 or newer and tick "Add python.exe to PATH".
  echo         Download: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [ERROR] Python is too old; 3.11+ is required. Current version:
  python -V
  pause
  exit /b 1
)
echo [OK] Python version:
python -V

REM ---- 2. Write optional preferences ----
echo.
python "core\scripts\setup_config.py"

REM ---- 3. Install into the agent that is running this, nothing else ----
echo.
python "core\scripts\install_adapters.py" --target auto
set INSTALL_RC=%errorlevel%

echo.
echo ============================================
if "%INSTALL_RC%"=="3" (
  echo   Done, but some files were NOT overwritten.
  echo   Read the [conflict] lines above, then re-run with --force if you are sure.
) else (
  echo   Done.
)
echo   Next steps:
echo     1. Create a course folder yourself and add a .study-workspace file
echo        (see README.md, section "Start a course")
echo     2. Open that folder with your agent, or use the CLI directly
echo     3. Restart the agent so the hooks load (if a hook was installed)
echo ============================================
pause
