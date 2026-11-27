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

REM ---- 3. Install into a directory you name; with no arguments it only probes ----
echo.
python "core\scripts\install_adapters.py" %*
set INSTALL_RC=%errorlevel%

echo.
echo ============================================
if "%INSTALL_RC%"=="3" (
  echo   Done, but some files were NOT overwritten.
  echo   Read the [conflict] lines above, then re-run with --force if you are sure.
) else (
  echo   Done.
)
echo.
echo   Installed nothing? You probably did not pass a directory.
echo   List the skill folders that exist on this machine:
echo     install.bat --discover
echo   Then install into one of them:
echo     install.bat --skills-dir "%%USERPROFILE%%\.your-agent\skills"
echo.
echo   Next steps:
echo     1. Create a course folder yourself and add a .study-workspace file
echo        (see README.md, section "Start a course")
echo     2. Open that folder with your agent, or use the CLI directly
echo ============================================
pause
