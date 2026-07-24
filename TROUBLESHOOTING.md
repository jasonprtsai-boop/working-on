# Troubleshooting

## PowerShell Blocks .ps1 Scripts

Some Windows lab PCs disable direct `.ps1` execution. Use the project wrappers
instead of running scripts directly:

```powershell
.\check_system.cmd
.\check_system_strict.cmd
```

For setup:

```powershell
powershell.exe -ExecutionPolicy Bypass -File setup_env.ps1
```

## Python Version Error

Use Python 3.11.9 when possible. Python 3.13 is not supported yet.

```powershell
Remove-Item -Recurse -Force .venv
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
```

## Missing Flask Or Other Python Packages

The active terminal is probably not using `.venv`.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

## Jest Cannot Be Found

Recreate `node_modules` from the lockfile:

```powershell
Remove-Item -Recurse -Force node_modules
.\scripts\npm24.cmd ci
.\scripts\npm24.cmd test
```

If this still fails, check:

```powershell
.\scripts\node24.cmd --version
.\scripts\npm24.cmd --version
```

Expected major versions:

- Node.js 24
- npm 11 or newer

## Camera Stream Flickers Or Freezes

Check in this order:

1. Use a powered USB port or powered hub.
2. Disable USB selective suspend in Windows power settings.
3. Lower `VISION_MJPEG_FPS`.
4. Lower `VISION_MJPEG_QUALITY`.
5. Try a different `CAMERA_INDEX`.
6. Restart the application after changing camera hardware.

## Robot Does Not Connect

Check:

```powershell
Test-NetConnection 169.254.47.64 -Port 5890
```

Then confirm:

- `FAKE_ROBOT=false`
- `ROBOT_ADAPTER=tmflow_json`
- `ROBOT_IP=169.254.47.64`
- `ROBOT_PORT=5890`
- PC Ethernet is on the same link-local subnet, for example `169.254.47.50` / `255.255.0.0`
- TMflow TCP JSON socket server is running
- TMflow returns newline-delimited UTF-8 JSON responses with the same command `id`
- `ROBOT_TMFLOW_WIRE_FORMAT=envelope` unless the TMflow project requires `flat_json`

Probe HELLO directly:

```powershell
.\.venv\Scripts\python.exe -c "import json,socket`ns=socket.create_connection(('169.254.47.64',5890),3)`nmsg={'version':'1.0','type':'COMMAND','id':'CMD_MANUAL_001','timestamp':'2026-07-24T00:00:00+08:00','command':'HELLO','payload':{'client':'manual_probe'}}`ns.sendall((json.dumps(msg)+'\n').encode())`nprint(s.recv(4096).decode())`ns.close()"
```

Expected result is a JSON line with `status` equal to `DONE`.

If the connection opens but moves fail, inspect the TMflow TCP JSON flow:

- Confirm `MOVE_L` returns `ACK`, then `STARTED`, then `DONE` or `ERROR`.
- Confirm response `id` matches the request `id`.
- Confirm the requested point is within TMflow safety limits and software soft limits.
- Confirm `GRIPPER` returns `ACK`, then `DONE` before live pick/place testing.

Compatibility paths still exist: use `ROBOT_ADAPTER=techmanpy` for the
TechmanPy External Script client, or `ROBOT_ADAPTER=modbus` for the old register
bridge. For Modbus, port `502`, register base values, command ACK, status, and
gripper feedback must match the TMflow project.

## Quality Gate Reports trailing_whitespace

Run:

```powershell
rg -n "[ \t]+$" .
```

Remove trailing spaces, then rerun:

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
git diff --check
.\check_system.cmd
```

## Real Robot Moves Too Fast

Keep the software defaults low:

```env
ROBOT_MAX_SPEED=80
ROBOT_TRAVEL_SPEED=30
ROBOT_LIFT_SPEED=30
ROBOT_APPROACH_SPEED=15
ROBOT_DEFAULT_ACCELERATION=60
```

Also lower the TMflow/controller TCP speed limit, force limit, and safety
space settings. Software limits alone are not enough for human-facing use.
