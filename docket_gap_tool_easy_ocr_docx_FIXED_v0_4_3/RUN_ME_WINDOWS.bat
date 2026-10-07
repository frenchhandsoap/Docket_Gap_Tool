@echo off
setlocal
cd /d "%~dp0"
echo Docket Gap Tool - one-click run

if not exist "docket_gap_tool\docx_import.py" (
  echo ERROR: This package is missing docket_gap_tool\docx_import.py.
  echo Please delete this folder completely, unzip the fixed package fresh, and run again.
  pause
  exit /b 1
)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
python -m docket_gap_tool.easy_run
echo.
echo Finished. Check the output folder.
pause
