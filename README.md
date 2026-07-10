## Start




source /home/ege/Projekte/yt-audio/.venv/bin/activate.fish
python run.py


### Windows

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python run.py
```

Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python run.py
```

Copy `.env.example` to `.env` if you want to change the download folder, host, port, or proxy settings.
By default the app binds to `0.0.0.0`, so it is reachable from other devices on your local network as well as `localhost`.
```