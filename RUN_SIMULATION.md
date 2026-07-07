# Run Simulation Mode

Simulation mode is the required first test after moving the project to a new
computer.

## Environment

Set these values in `.env`:

```env
SYSTEM_MODE=simulation
FAKE_ROBOT=true
FAKE_VISION=true
FAKE_AI=true
AUTO_EXECUTE_ROBOT=false
ENGINE_AUTO_ANALYZE=false
```

## Start

```powershell
.\.venv\Scripts\python.exe main.py
```

Open:

- Console: `http://127.0.0.1:5000/`
- Dashboard: `http://127.0.0.1:5000/dashboard`

## Smoke Test

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
npm test
```

Expected result:

- UI loads without real camera or robot.
- Player mode waits for the Start button.
- Robot commands are not sent to hardware.
- Preflight should clearly show simulation/fake status.
