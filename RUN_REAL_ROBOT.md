# Run Real TM5-700 Robot Mode

Real robot mode must be treated as a commissioning procedure, not a normal
software launch.

## Required TMflow Safety Setup

Before setting `FAKE_ROBOT=false`, confirm these items in TMflow or the robot
controller:

- TCP speed limit is lower than the software `ROBOT_MAX_SPEED`.
- Force/collision detection is enabled and tested.
- G-Sensor/collision safety is enabled.
- Safety area or virtual wall prevents the arm from reaching people.
- Joint and tool motion cannot pinch hands near the board edge.
- E-Stop is physically reachable and tested.
- Gripper open/close force is safe for chess pieces and fingers.
- Manual reduced-speed jog test passes before automatic moves.

Software coordinate limits are only a second layer. They do not replace robot
controller safety functions.

## Conservative Software Defaults

The project defaults are intentionally slow for first real-hardware tests:

```env
ROBOT_MAX_SPEED=80
ROBOT_TRAVEL_SPEED=30
ROBOT_LIFT_SPEED=30
ROBOT_APPROACH_SPEED=15
ROBOT_DEFAULT_ACCELERATION=60
AUTO_EXECUTE_ROBOT=false
```

Increase these only after TMflow safety, one-move validation, and operator
sign-off are complete.

## Environment

Set `.env`:

```env
SYSTEM_MODE=real_robot
FAKE_ROBOT=false
FAKE_VISION=false
FAKE_AI=false
AUTO_EXECUTE_ROBOT=false
ROBOT_ADAPTER=tmflow_json
ROBOT_IP=169.254.47.64
ROBOT_PORT=5890
ROBOT_PC_IP=169.254.47.50
ROBOT_SUBNET_MASK=255.255.0.0
ROBOT_CONNECT_TIMEOUT_SEC=3.0
TMFLOW_VERSION=1.82
TM_CONTROLLER_VERSION=1.82.51
ROBOT_TMFLOW_PROTOCOL_VERSION=1.0
ROBOT_TMFLOW_WIRE_FORMAT=envelope
ROBOT_TMFLOW_REQUIRE_HELLO=true
ROBOT_TMFLOW_ACK_TIMEOUT_SEC=2.0
ROBOT_TMFLOW_DONE_TIMEOUT_SEC=30.0
ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC=90.0
ROBOT_TMFLOW_BASE=ChessBoard_Base
ROBOT_TMFLOW_TCP=ChessGripper_TCP
```

## TMflow TCP JSON Contract

The primary real-robot path is the Part 2 TMflow TCP JSON protocol. Python is
the TCP client; TMflow is the socket server. Every message is one UTF-8 JSON
object terminated by `\n`.

For the confirmed lab baseline, use:

```text
PC TMflow:       1.82
Controller:      1.82.51
Robot IP:        169.254.47.64
Robot subnet:    255.255.0.0
Suggested PC IP: 169.254.47.50
Robot port:      5890
```

Before any live motion, confirm the TMflow project is running a TCP socket
server that accepts:

```text
HELLO
PING / PONG
GET_STATE
MOVE_L with ACK -> STARTED -> DONE or ERROR
GRIPPER with ACK -> DONE or ERROR
STOP
```

Quick protocol probe from Python:

```powershell
.\.venv\Scripts\python.exe -c "import json,socket`ns=socket.create_connection(('169.254.47.64',5890),3)`nmsg={'version':'1.0','type':'COMMAND','id':'CMD_MANUAL_001','timestamp':'2026-07-24T00:00:00+08:00','command':'HELLO','payload':{'client':'manual_probe'}}`ns.sendall((json.dumps(msg)+'\n').encode())`nprint(s.recv(4096).decode())`ns.close()"
```

Expected result is a JSON line with the same `id` and status `DONE`.

Use `ROBOT_TMFLOW_WIRE_FORMAT=envelope` for the full Part 2 JSON envelope. If
TMflow 1.82 parsing cannot handle nested payloads, switch to
`ROBOT_TMFLOW_WIRE_FORMAT=flat_json` and keep RobotService / Vision / AI code
unchanged.

`techmanpy` remains available with `ROBOT_ADAPTER=techmanpy`. The older Modbus
register bridge remains available only with `ROBOT_ADAPTER=modbus`; do not
treat port `502` as the default real-robot path for this lab setup.

## Commissioning Order

1. Start the server.
2. Open the setup page and log in with the configured `SETUP_PASSWORD`.
3. Verify camera and board calibration.
4. Verify origin height, safe Z, grab Z, and place offset.
5. Verify software X/Y/Z limits and dead-zone range.
6. Run setup preflight.
7. Run robot connect/status test.
8. Confirm TMflow TCP JSON reports HELLO/PING/GET_STATE on port `5890`.
9. Run gripper open/close tests with the arm away from the board.
10. Run safe Z and origin tests.
11. Run dead-zone test.
12. Run one-move test with a clear board and one operator at E-Stop.
13. Set `AUTO_EXECUTE_ROBOT=true` only after the above tests pass.

## Formal Robot Calibration Points

Measure and save at least these robot-space points before the first real game:

```text
a0
i0
a9
i9
e4 or e5
dead zone slot 1
```

Acceptance criteria:

- All 90 board intersections are inside X/Y/Z soft limits.
- The full dead-zone range is inside X/Y soft limits.
- `Z_SAFE` clears the tallest chess piece and gripper body.
- `Z_GRAB` reaches the piece without pressing into the board.
- The saved robot calibration file and setup settings are reloaded after restart.

## Real-Hardware Dry Run Sequence

Run this before any automatic game. Keep `AUTO_EXECUTE_ROBOT=false` until the
last step passes.

1. Ping the TM5-700 controller IP from Windows.
2. Run `Test-NetConnection 169.254.47.64 -Port 5890`.
3. Use setup hardware test `connect` and `status` to verify the TMflow TCP JSON endpoint and state.
4. Use setup hardware test `write_pose` in dry-run only; live no-trigger pose writes are a Modbus-only legacy test.
5. Move to a0 above the board at `Z_SAFE`.
6. Move to `corner_a0`, `corner_i0`, `corner_a9`, and `corner_i9` at `Z_SAFE`.
7. Move to `center_e4` at `Z_SAFE`.
8. Test `grab_z` at e4.
9. Test `gripper_open` and `gripper_close`.
10. Test one move `a0a1`.
11. Test a capture move and confirm the piece is placed into dead zone slot 1.
12. Run setup preflight with auto-execute required.
13. Enable `AUTO_EXECUTE_ROBOT=true`.

## Stop Conditions

Stop immediately if:

- Camera stream freezes or detection age is stale.
- Python cannot reach port `5890`, or TMflow does not return ACK/DONE/ERROR JSON responses.
- The arm approaches outside calibrated board/dead-zone limits.
- Any move requires manual intervention.
- The operator cannot predict the next arm motion.
