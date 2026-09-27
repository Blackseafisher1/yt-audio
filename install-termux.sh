#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update -y
pkg install -y python ffmpeg

python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

echo "Installed. Start with: source .venv/bin/activate && python run.py"