#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

pkg update -y
pkg install -y python ffmpeg

python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "fastapi==0.103.2" "pydantic<2" "uvicorn>=0.23,<0.30" "yt-dlp>=2024" "python-multipart>=0.0.6" "mutagen>=1.47"

if command -v termux-wake-lock >/dev/null 2>&1; then
	termux-wake-lock
fi

echo "Installed. Open http://127.0.0.1:8000 in your browser."
exec python run.py