# Tesseract OCR backup

The tool first tries to extract selectable text from each PDF. If that extracted text is empty or very short, it can fall back to Tesseract OCR.

Tesseract is an OS-level program. The Python package includes OCR support and installer helpers, but it does **not** bundle the Tesseract binary itself because the binary is different for macOS, Windows, and Linux.

## macOS

Double-click:

`scripts/INSTALL_TESSERACT_MAC.command`

This uses Homebrew. If Homebrew is not installed, install it first, then rerun the script.

Manual command:

```bash
brew install tesseract
```

## Windows

Double-click:

`scripts\INSTALL_TESSERACT_WINDOWS.bat`

This uses `winget` to install the common UB Mannheim Tesseract build. After install, close and reopen the terminal/window so PATH refreshes.

## Linux / Ubuntu

Run:

```bash
bash scripts/INSTALL_TESSERACT_LINUX.sh
```

Manual command:

```bash
sudo apt-get install tesseract-ocr
```

## Check

Run:

```bash
tesseract --version
```

If that works, the one-click runner will detect Tesseract automatically.
