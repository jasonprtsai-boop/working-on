# Lab PC Installation

Use this checklist for the computer that will connect to the camera and
TM5-700.

## Before Installing

- Confirm Windows 10/11 64-bit.
- Install Python 3.11.9 64-bit.
- Install Node.js 24 LTS.
- Disable aggressive USB power saving for the camera port.
- Connect the lab PC and robot controller to the same isolated network.
- Configure the PC Ethernet adapter for the robot link, for example `169.254.47.50` with subnet mask `255.255.0.0`.
- Confirm TMflow `1.82`, controller `1.82.51`, robot IP `169.254.47.64`, and the TMflow TCP JSON socket server on TCP `5890`.

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt -r requirements.vision.txt
npm ci
Copy-Item .env.example .env
```

Edit `.env` for the lab computer:

```env
SMART_CHESS_HOST=127.0.0.1
FAKE_ROBOT=true
FAKE_VISION=false
FAKE_AI=true
AUTO_EXECUTE_ROBOT=false
CAMERA_INDEX=0
ROBOT_ADAPTER=tmflow_json
ROBOT_IP=169.254.47.64
ROBOT_PORT=5890
ROBOT_PC_IP=169.254.47.50
ROBOT_SUBNET_MASK=255.255.0.0
TMFLOW_VERSION=1.82
TM_CONTROLLER_VERSION=1.82.51
ROBOT_TMFLOW_PROTOCOL_VERSION=1.0
ROBOT_TMFLOW_WIRE_FORMAT=envelope
ROBOT_TMFLOW_REQUIRE_HELLO=true
```

Start in simulation-safe mode first:

```powershell
.\.venv\Scripts\python.exe main.py
```

Before connecting the real robot, run the full software check:

```powershell
.\check_system.cmd
```

## First Setup Flow

1. Log in to the setup page with password `login`.
2. Select and verify the camera.
3. Calibrate the board view.
4. Set origin height, safe Z, grab Z, and place offset.
5. Set software X/Y/Z limits and dead-zone range.
6. Run preflight.
7. Run hardware tests only after TMflow safety limits and the TCP JSON socket server are enabled.
8. Enable `FAKE_ROBOT=false` only for real robot validation.
9. Enable `AUTO_EXECUTE_ROBOT=true` only after one-move testing succeeds.

## Lab Rule

Do not use real robot mode on a shared or public network. Keep the robot,
camera, and control PC on a controlled lab network.
