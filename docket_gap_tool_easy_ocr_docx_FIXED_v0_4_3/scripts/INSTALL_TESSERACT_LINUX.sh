#!/bin/bash
set -e
echo "Installing Tesseract OCR with apt..."
sudo apt-get update
sudo apt-get install -y tesseract-ocr
