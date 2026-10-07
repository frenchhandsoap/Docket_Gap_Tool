#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -f "docket_gap_tool/docx_import.py" ]; then
  echo "ERROR: This package is missing docket_gap_tool/docx_import.py."
  echo "Delete this folder, unzip the fixed package fresh, and run again."
  exit 1
fi
echo "Docket Gap Tool - one-click run"
echo "Working folder: $(pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3, then run this again."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m docket_gap_tool.easy_run
echo ""
echo "Finished. Check the output folder."
read -n 1 -s -r -p "Press any key to close..."
