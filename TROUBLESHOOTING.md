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

Use Python 3.11 when possible. Python 3.13 is not supported yet.

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

## npm test Cannot Find Jest

Recreate `node_modules` from the lockfile:

```powershell
Remove-Item -Recurse -Force node_modules
npm ci
npm test
```

If this still fails, check:

```powershell
node --version
npm --version
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
Test-NetConnection <tm5-controller-ip> -Port 502
```

Then confirm:

- `FAKE_ROBOT=false`
- `ROBOT_IP` is the controller IP
- `ROBOT_PORT=502`
- TMflow Modbus server is enabled
- Register base values match the TMflow project
- `ROBOT_VERIFY_STATUS_ON_CONNECT=true`
- `ROBOT_COMMAND_HANDSHAKE_ENABLED=true`
- `ROBOT_GRIPPER_FEEDBACK_ENABLED=true`

If the connection opens but moves fail, inspect the TMflow register watch:

- Python should write command id, pose/profile registers, then trigger `1`.
- TMflow should echo the same command id to the ACK register.
- Status should change to moving, then complete or error.
- Error status should also write a useful error code.
- Gripper open/close should update the gripper status register (`0=open`, `1=closed`, `2=error`).

If ACK never changes, the TMflow project is not consuming the trigger register
or the Python/TMflow register map does not match.

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
