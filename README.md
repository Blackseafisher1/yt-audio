# YouTube Audio/Video Batch Downloader

FastAPI + yt-dlp web UI for downloading YouTube audio/video in batch. No re-encoding.

## Dependencies

- **Python** ≥ 3.10
- **ffmpeg** (required by yt-dlp for merging/remuxing)
- Python packages (installed automatically)

## Install

### Linux

```bash
# Ubuntu/Debian
sudo apt install python3 python3-pip ffmpeg

# Arch
sudo pacman -S python python-pip ffmpeg

# Fedora
sudo dnf install python3 python3-pip ffmpeg
```

### macOS

```bash
brew install python ffmpeg
```

### Windows

```powershell
winget install ffmpeg
```

### Python deps (all platforms)

```bash
pip install -e .
```

Or with uv:

```bash
pip install uv
uv sync
```

## Run

```bash
python run.py
```

Open `http://localhost:8000`.

For custom host/port:

```bash
APP_PORT=8080 python run.py
```

## Features

- **Audio mode** — best native Opus/AAC, no re-encode. Choose container: `.opus`, `.webm`, `.m4a`
- **Video mode** — selectable quality (best/4K/1080p/720p/480p/360p)
- **Batch** — multiple URLs or full playlists
- **Background downloads** — non-blocking, status polling
- **File management** — delete single files, clear all, download all as ZIP
- **Dark/light theme**
- **URL history** (localStorage)
- **Auto-cleanup** — files deleted after 30s (on download) / 5min (auto)

## Run on Android (Termux)

```bash
pkg install python ffmpeg
pip install fastapi uvicorn yt-dlp
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in browser.

## Run on server

```bash
git clone <repo>
cd yt-audio
pip install fastapi uvicorn yt-dlp
uvicorn main:app --host 0.0.0.0 --port 8000
```

For background process:

```bash
nohup python run.py &
```


## Configuration (via `.env` file)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_PORT` | `8000` | Port |
| `APP_RELOAD` | `false` | Auto-reload on file changes |
| `DOWNLOAD_DIR` | `downloads` | Download directory |
| `CLEANUP_5MIN` | `300` | Auto-delete after seconds |
| `CLEANUP_30SEC` | `30` | Delete after download |
| `WARP_PROXY` | `socks5://127.0.0.1:40000` | Warp SOCKS5 proxy |

## Notes

- Audio is never re-encoded. `bestaudio` picks YouTube's native stream.
- iPhone: use web UI only. No native iOS support.
- For datacenter IPs (DigitalOcean, AWS): YouTube may block. Use Cloudflare Tunnel or residential proxy.
