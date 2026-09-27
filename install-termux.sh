#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update -y
pkg install -y python ffmpeg

python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "fastapi==0.103.2" "pydantic<2" "uvicorn>=0.23,<0.30" "yt-dlp>=2024" "python-multipart>=0.0.6"

echo "Installed. Start with: source .venv/bin/activate && python run.py"