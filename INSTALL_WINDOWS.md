# Windows Installation

This is the recommended setup for a normal Windows test computer.

## Supported Versions

- Windows 10/11 64-bit
- Python 3.11 recommended
- Python 3.9, 3.10, 3.11, and 3.12 are supported
- Python 3.13 is not supported yet for this project
- Node.js 24 LTS recommended
- npm 11 or newer

## Clean Install

Run these commands from the project root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
npm ci
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:5000/`.

## Setup Helper

The helper creates `.venv`, installs Python dependencies, installs Node
dependencies if npm is available, initializes folders, and checks protected
assets:

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

## Node Reset

Use this when Jest or `node_modules` becomes inconsistent after copying the
folder to another computer:

```powershell
Remove-Item -Recurse -Force node_modules
npm ci
npm test
```

Keep `package-lock.json`. It is the reproducible dependency baseline.

## Python Reset

Use this when the venv was created by the wrong Python version:

```powershell
Remove-Item -Recurse -Force .venv
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
```

## Verification

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
npm test
```
