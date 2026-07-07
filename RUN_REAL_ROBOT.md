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
ROBOT_VERIFY_STATUS_ON_CONNECT=true
ROBOT_IP=<tm5-controller-ip>
ROBOT_PORT=502
ROBOT_COMMAND_HANDSHAKE_ENABLED=true
ROBOT_GRIPPER_FEEDBACK_ENABLED=true
```

## TMflow Register Contract

The Python side expects TMflow to treat the pose registers as data only, then
execute motion only after the trigger register changes:

```text
6998       command id written by Python
6999       command trigger, 1=start, 0=clear
7000-7011  pose x,y,z,rx,ry,rz as scaled_int32, scale 100
7012-7013  speed and acceleration profile
7098       gripper command
7099       halt command
7100       robot status, 0=idle, 1=moving, 2=complete, 3=error
7101       command ack, TMflow must echo command id
7102       robot error code
7103       gripper status, 0=opened, 1=closed, 2=error
```

Required command flow:

1. Python writes `command_id`.
2. Python writes speed/acceleration profile.
3. Python writes motion coordinates.
4. Python writes trigger `1`.
5. TMflow echoes `command_id` to ACK.
6. TMflow sets status `moving`.
7. TMflow sets status `complete` or `error`. Returning to idle after complete is allowed.
8. Python clears trigger to `0`.

Do not enable `AUTO_EXECUTE_ROBOT=true` until this ACK/status flow is verified
in the setup hardware tests.

## Commissioning Order

1. Start the server.
2. Open the setup page and log in with the configured `SETUP_PASSWORD`.
3. Verify camera and board calibration.
4. Verify origin height, safe Z, grab Z, and place offset.
5. Verify software X/Y/Z limits and dead-zone range.
6. Run setup preflight.
7. Run robot connect/status test.
8. Confirm command ID, trigger, ACK, status, error-code, and gripper-status registers.
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
2. Run `Test-NetConnection <tm5-controller-ip> -Port 502`.
3. Use setup hardware test `status` to read only the STATUS register.
4. Use setup hardware test `write_pose` with live hardware enabled to write one pose/profile without trigger.
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
- Robot status register does not return expected completion/error values.
- The arm approaches outside calibrated board/dead-zone limits.
- Any move requires manual intervention.
- The operator cannot predict the next arm motion.
