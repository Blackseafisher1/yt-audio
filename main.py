import io
import re
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="YouTube Audio/Video Downloader")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

tasks: dict = {}
latest_task_id: str | None = None
 
 
def schedule_delete(path: Path, delay: int):
    if delay > 0:
        threading.Timer(delay, lambda p=path: p.unlink(missing_ok=True)).start()


COOKIES_FILE = DOWNLOAD_DIR / "cookies.txt"
THUMBNAIL_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
WARP_PROXY = "socks5://127.0.0.1:40000"

import socket


def warp_available():
    try:
        s = socket.create_connection(("127.0.0.1", 40000), timeout=1)
        s.close()
        return True
    except:
        return False


def build_args(url_list: list[str], mode: str, quality: str, audio_format: str = "opus", embed_thumbnail: bool = True) -> list[str]:
    args = [
        sys.executable, "-m", "yt_dlp",
        "--force-ipv4",
        "--ignore-errors",
        "--add-metadata",
        "-o", f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
    ]

    if embed_thumbnail and mode == "audio":
        args.extend([
            "--write-thumbnail",
            "--embed-thumbnail",
            "--convert-thumbnails", "jpg",
            "--ppa", "ThumbnailsConvertor+ffmpeg_o:-vf crop=min(iw\\,ih):min(iw\\,ih)",
        ])

    if COOKIES_FILE.exists() and COOKIES_FILE.stat().st_size > 100:
        args.extend(["--cookies", str(COOKIES_FILE)])

    if mode == "audio":
        if audio_format == "opus":
            args.extend(["-f", "bestaudio[ext=webm]/bestaudio", "--remux-video", "opus"])
        elif audio_format == "m4a":
            args.extend(["-f", "bestaudio[ext=m4a]/bestaudio", "--remux-video", "m4a"])
        elif audio_format == "webm":
            args.extend(["-f", "bestaudio[ext=webm]/bestaudio", "--remux-video", "webm"])
        elif audio_format == "ogg":
            args.extend(["-f", "bestaudio[acodec=opus]/bestaudio", "--remux-video", "ogg"])
        elif audio_format in ("mp3", "flac", "wav", "aac"):
            args.extend(["-x", "--audio-format", audio_format, "--audio-quality", "0"])
        else:
            args.extend(["-f", "bestaudio"])
    elif mode == "video":
        if quality and quality != "best":
            args.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/bestvideo[height<={quality}]/best"])
        else:
            args.extend(["-f", "bestvideo+bestaudio/best"])

    args.extend(url_list)
    return args


def collect_files():
    files = []
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and f.name != "cookies.txt":
            files.append({
                "name": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "mtime": f.stat().st_mtime,
            })
    return sorted(files, key=lambda x: x["mtime"])


def remove_thumbnail_sidecars():
    for path in DOWNLOAD_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in THUMBNAIL_SUFFIXES:
            path.unlink(missing_ok=True)


def download_task(task_id: str, url_list: list[str], mode: str, quality: str, audio_format: str = "opus", embed_thumbnail: bool = True, number_files: bool = False, prefix_exclamation: bool = False, number_style: str = "numeric", cleanup_seconds: int = 0):
    tasks[task_id] = {"status": "running", "mode": mode, "quality": quality, "total": len(url_list), "done": 0}
    try:
        args = build_args(url_list, mode, quality, audio_format, embed_thumbnail)

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout or []:
            m = re.search(r"Downloading (?:item|video) (\d+) of (\d+)", line)
            if m:
                tasks[task_id].update({"done": int(m.group(1)), "total": int(m.group(2))})
        process.wait()
        remove_thumbnail_sidecars()
        if process.returncode >= 2:
            raise RuntimeError(f"Exit code {process.returncode}")

        # remove 0-byte files (failed remux)
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file() and f.stat().st_size == 0:
                f.unlink()

        if number_files:
            import string as _str
            for i, f in enumerate(sorted(DOWNLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime), 1):
                if f.is_file() and f.name != COOKIES_FILE.name:
                    prefix = "!" if prefix_exclamation else ""
                    if number_style == "numeric":
                        idx = f"{i}."
                    else:
                        value = i
                        letters = ""
                        while value:
                            value, remainder = divmod(value - 1, 26)
                            letters = _str.ascii_lowercase[remainder] + letters
                        idx = letters
                    new = DOWNLOAD_DIR / f"{prefix}{idx} {f.stem}{f.suffix}"
                    if new != f:
                        f.rename(new)
        files = collect_files()
        tasks[task_id] = {"status": "done", "mode": mode, "quality": quality, "files": files}
        global latest_task_id
        latest_task_id = task_id

        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file() and f.name != COOKIES_FILE.name:
                schedule_delete(f, cleanup_seconds)

    except Exception as e:
        tasks[task_id] = {"status": "error", "mode": mode, "quality": quality, "message": str(e)}


@app.post("/download/")
async def start_download(
    urls: str = Form(...),
    mode: str = Form("audio"),
    quality: str = Form("best"),
    audio_format: str = Form("opus"),
    embed_thumbnail: str = Form("true"),
    number_files: str = Form("false"),
    prefix_exclamation: str = Form("false"),
    number_style: str = Form("numeric"),
    cleanup_seconds: str = Form("0"),
    background_tasks: BackgroundTasks = None,
):
    url_list = [u.strip() for u in urls.replace("\n", ",").split(",") if u.strip()]
    if not url_list:
        raise HTTPException(status_code=400, detail="No URLs provided")
    if mode not in ("audio", "video"):
        raise HTTPException(status_code=400, detail="Mode must be 'audio' or 'video'")
    allowed_audio_formats = {"m4a", "webm", "opus", "ogg", "mp3", "flac", "wav", "aac"}
    if mode == "audio" and audio_format not in allowed_audio_formats:
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    try:
        cleanup_delay = int(cleanup_seconds)
    except ValueError:
        raise HTTPException(status_code=400, detail="Cleanup time must be a number of seconds")
    if cleanup_delay < 0:
        raise HTTPException(status_code=400, detail="Cleanup time cannot be negative")

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"status": "queued", "mode": mode, "quality": quality}
    background_tasks.add_task(download_task, task_id, url_list, mode, quality, audio_format, embed_thumbnail == "true", number_files == "true", prefix_exclamation == "true", number_style, cleanup_delay)

    return JSONResponse({
        "status": "queued",
        "task_id": task_id,
        "message": f"Started download of {len(url_list)} item(s).",
    })


@app.get("/task/{task_id}")
def get_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/files/")
def list_files():
    files = collect_files()
    return {"files": files}


@app.get("/download-file/{filename}")
def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.delete("/delete-file/{filename}")
def delete_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return JSONResponse({"status": "deleted", "file": filename})


@app.delete("/clear-all/")
def clear_all():
    count = 0
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    return JSONResponse({"status": "cleared", "count": count})


@app.get("/download-all/")
def download_all():
    files = sorted([f for f in DOWNLOAD_DIR.iterdir() if f.is_file()], key=lambda f: f.stat().st_mtime)
    if not files:
        raise HTTPException(status_code=404, detail="No files to download")

    first = files[0].stem
    safe = first.encode("ascii", "replace").decode("ascii").replace("?", "_")[:60]
    zip_name = f"{safe}....zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.post("/upload-cookies/")
async def upload_cookies(file: UploadFile = File(...)):
    content = await file.read()
    COOKIES_FILE.write_bytes(content)
    return JSONResponse({"status": "ok", "message": f"Cookies saved ({len(content)} bytes)"})


@app.get("/cookies-status/")
def cookies_status():
    if COOKIES_FILE.exists():
        size = COOKIES_FILE.stat().st_size
        return {"status": "present", "size_bytes": size}
    return {"status": "missing"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
