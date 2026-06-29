import io
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

CLEANUP_5MIN = 300
CLEANUP_30SEC = 30


def clean_old_files():
    now = time.time()
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and now - f.stat().st_mtime > CLEANUP_5MIN:
            f.unlink()


def schedule_delete(path: Path, delay: int):
    threading.Timer(delay, lambda p=path: p.unlink(missing_ok=True)).start()


COOKIES_FILE = DOWNLOAD_DIR / "cookies.txt"
WARP_PROXY = "socks5://127.0.0.1:40000"

import socket


def warp_available():
    try:
        s = socket.create_connection(("127.0.0.1", 40000), timeout=1)
        s.close()
        return True
    except:
        return False


def build_args(url_list: list[str], mode: str, quality: str) -> list[str]:
    use_cookies = COOKIES_FILE.exists() and COOKIES_FILE.stat().st_size > 100
    client = "web" if use_cookies else "android"

    args = [
        sys.executable, "-m", "yt_dlp",
        "--force-ipv4",
        "--ignore-errors",
        "--add-metadata",
        "--no-write-thumbnail",
        "--no-playlist",
    ]

    if warp_available():
        args.extend(["--proxy", WARP_PROXY])

    args.extend([
        "--extractor-args", f"youtube:player_client={client};skip=webpage",
        "--no-check-formats",
        "-o", f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
    ])

    if use_cookies:
        args.extend(["--cookies", str(COOKIES_FILE)])

    if mode == "audio":
        args.extend(["-f", "bestaudio/best"])
    elif mode == "video":
        if quality and quality != "best":
            args.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/bestvideo[height<={quality}]/best"])
        else:
            args.extend(["-f", "bestvideo+bestaudio/best"])

    args.extend(url_list)
    return args


def collect_files():
    return sorted(
        [
            {"name": f.name, "size_mb": round(f.stat().st_size / (1024 * 1024), 2)}
            for f in DOWNLOAD_DIR.iterdir() if f.is_file()
        ],
        key=lambda x: x["name"],
    )


def download_task(task_id: str, url_list: list[str], mode: str, quality: str):
    tasks[task_id] = {"status": "running", "mode": mode, "quality": quality}
    try:
        args = build_args(url_list, mode, quality)
        result = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Exit code {result.returncode}")

        files = collect_files()
        tasks[task_id] = {"status": "done", "mode": mode, "quality": quality, "files": files}
        global latest_task_id
        latest_task_id = task_id

        # schedule all files for deletion after 5min
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file():
                schedule_delete(f, CLEANUP_5MIN)

    except Exception as e:
        tasks[task_id] = {"status": "error", "mode": mode, "quality": quality, "message": str(e)}


@app.post("/download/")
async def start_download(
    urls: str = Form(...),
    mode: str = Form("audio"),
    quality: str = Form("best"),
    background_tasks: BackgroundTasks = None,
):
    url_list = [u.strip() for u in urls.replace("\n", ",").split(",") if u.strip()]
    if not url_list:
        raise HTTPException(status_code=400, detail="No URLs provided")
    if mode not in ("audio", "video"):
        raise HTTPException(status_code=400, detail="Mode must be 'audio' or 'video'")

    clean_old_files()

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"status": "queued", "mode": mode, "quality": quality}
    background_tasks.add_task(download_task, task_id, url_list, mode, quality)

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
    task = tasks.get(latest_task_id) if latest_task_id else None
    files = task.get("files", []) if task and task.get("status") == "done" else []
    return {"files": files, "task_id": latest_task_id}


@app.get("/download-file/{filename}")
def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    schedule_delete(file_path, CLEANUP_30SEC)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/download-all/")
def download_all():
    task = tasks.get(latest_task_id) if latest_task_id else None
    if not task or task.get("status") != "done" or not task.get("files"):
        raise HTTPException(status_code=404, detail="No files to download")

    files = [DOWNLOAD_DIR / f["name"] for f in task["files"]]
    files = [f for f in files if f.exists()]
    if not files:
        raise HTTPException(status_code=404, detail="No files found on disk")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)

    for f in files:
        schedule_delete(f, CLEANUP_30SEC)

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="downloads.zip"'},
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
