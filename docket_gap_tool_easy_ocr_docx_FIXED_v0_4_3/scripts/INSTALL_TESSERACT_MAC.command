#!/bin/bash
set -e
echo "Installing Tesseract OCR with Homebrew..."
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is not installed. Install Homebrew first from https://brew.sh, then rerun this script."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
brew install tesseract
echo "Tesseract installed."
read -n 1 -s -r -p "Press any key to close..."
