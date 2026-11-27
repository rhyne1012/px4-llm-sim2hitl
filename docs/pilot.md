# Pilot

`tools/pilot.py` flies a fixed-wing like a person with sticks: it takes off from a runway in Stabilized, levels off at a set altitude, runs a command script, and keeps PX4's manual input alive until it is stopped. In HITL there is no receiver, so the pilot is the flight controller's RC. The same pilot flies SITL (lockstep, on simhost's simulated clock) and HITL (real time).

```sh
PY=<python with pymavlink>
"$PY" -B tools/pilot.py takeoff --vehicle <vehicle folder> --relay-port 14600 --listen-port 14601 \
    --log-dir <run>/pilot --after <vehicle repo>/<commands>/<script>.py [--climb-bank 30]
"$PY" -B tools/pilot.py status --relay-port 14600 --listen-port 14601 --log-dir <run>/pilot
"$PY" -B tools/pilot.py stop --log-dir <run>/pilot
```

- `--relay-port` is simhost's `--relay-port`. The pilot binds its own `--listen-port` and is one more peer of the relay. The runner chooses both ports.
- `--log-dir` holds `status.json` (every 0.5 s), the `stop` file and `pilot_<time>.csv` (10 Hz: state, mode, telemetry, sticks). `stop` creates the stop file; SIGINT and SIGTERM do the same.
- `takeoff` returns 0 after a stop, a ground-station takeover or a script that finished with `release`, and 2 otherwise. A runner waits for `status.json` `after_state` (`complete` or `failed`), then stops the pilot.
- In lockstep, set `SIM2HITL_SIMCLOCK` and `SIM2HITL_PILOTSYNC` to simhost's `--simclock` and `--pilot-sync` files (`tools/simclock.py`; start simhost first). The pilot then runs on the simulated clock and gates the simulation, so its keep-alive and its checks never fall behind PX4. Only the flying pilot gates; `status` only reads the clock.

## Flight

| State | What the pilot does | Next | Gives up |
|---|---|---|---|
| connect | waits for fresh telemetry through the relay | telemetry fresh | 15 s |
| check | reads back `SYS_HITL`, `FW_MAN_P_MAX` (and `FW_MAN_R_MAX` with `--climb-bank`, the RC parameters with `INPUT = 'rc'`); checks fixed-wing, disarmed, on the ground (CAS ≤ 5 m/s, height within ±5 m) | all pass | refuses on any failure; 8 s (15 s for RC) to read back |
| mode | requests Stabilized, sticks already streaming | Stabilized, after at least 1 s | 8 s |
| arm | requests arming | armed | 10 s, then abandon |
| roll | throttle to `takeoff_throttle` at 1/s | CAS ≥ `rotate_cas` | 40 s, then abandon |
| climb | pitch to `climb_pitch` at 30°/s; with `--climb-bank`, bank above 20 m | height ≥ `altitude` − 2 m | 180 s: level off, the script is not started |
| cruise | `cruise_throttle`; pitch = `altitude_gain` × height error − `climb_damping` × climb rate, within ±8° | the script starts after the steady time | readiness 60 s (`--after-timeout`) |
| loiter | neutral sticks at `cruise_throttle` while PX4 navigates | Stabilized returns to cruise | — |

- `--climb-bank B` (degrees, positive right, at most 35 and at most `FW_MAN_R_MAX`) climbs and waits in a banked circle, so the climb-out stays near home. The wings level once the aircraft is within −10/+5 m of the altitude with |climb| ≤ 1.5 m/s and either heads within 45° of home or is within 150 m of it.
- The altitude hold is proportional only: level flight settles about (trim pitch ÷ `altitude_gain`) metres off the altitude. Judge "level" by the climb rate, not by the height.
- Heights are above the EKF origin.

## Safety

- The pilot refuses to fly unless the flight controller reads back `SYS_HITL=1` and reports a fixed-wing that is disarmed on the ground. A SITL build that keeps `SYS_HITL=1` (a vehicle repository's SITL FC) qualifies; stock PX4 SITL does not. No parameter is written.
- On the ground (arm, roll), a stop or lost telemetry abandons the takeoff: neutral sticks, disarm. In the air the pilot lets go of the sticks.
- Lost telemetry: no HEARTBEAT for 3 s, or no VFR_HUD, LOCAL_POSITION_NED or ATTITUDE for 1 s (pilot clock).
- Once flying, the sticks go on through every PX4 mode change: frozen in OFFBOARD, level flight with altitude hold in Stabilized, neutral in any other mode. They are PX4's only RC; if they stopped for `COM_RC_LOSS_T`, PX4's RC-loss failsafe would take over and replace the behaviour under test. During the takeoff (roll, climb), leaving Stabilized hands back.
- Hand-back: a stop, a ground station's sticks moving by more than 150/1000, lost telemetry, a disarm, or a failed command script.

## Automation numbers

The numbers belong to the vehicle: a `[pilot]` table in its `vehicle.toml` (`--vehicle <folder>`), each overridable on the command line (`--takeoff-throttle` etc.). The toolkit has no defaults. The pilot refuses to fly if one is missing, out of range or unknown, and records each value with its source in its log and in `status.json` (`pilot_numbers`).

```toml
[pilot]
takeoff_throttle = 0.6    # throttle of the ground roll and the climb, 0-1
cruise_throttle = 0.32    # throttle of level flight, 0-1
rotate_cas = 12.0         # m/s: pitch up from this calibrated airspeed, 5-30
climb_pitch = 12.0        # deg of pitch in the climb, 0-25
altitude = 100.0          # m above the EKF origin, 20-500
altitude_gain = 0.5       # deg of pitch per m of height error, > 0
climb_damping = 1.0       # deg of pitch per m/s of climb rate, >= 0
rate = 50.0               # stick frames per second, 20-100
```

- `takeoff_throttle` must start the ground roll on the model's ground and reach `rotate_cas` within 40 s.
- `rotate_cas` lies above the stall speed with a margin; `climb_pitch` neither stalls nor fails to climb.
- PX4's `FW_MAN_P_MAX` (and `FW_MAN_R_MAX`) turn degrees into stick values; they are read back, never assumed.

## Command scripts

A command script is a Python file in the vehicle repository, given as `--after <path>`. It is loaded and checked before the pilot opens its port; an invalid script refuses the flight. It runs once, after the climb, when for `--after-stable-seconds` (3 s) in a row PX4 is in Stabilized, the height is within ±5 m of `altitude`, `rotate_cas` ≤ CAS ≤ 30 m/s, |roll| ≤ 5°, |climb| ≤ 1.5 m/s and the pitch is −15° to 20°.

The script shares the pilot's one link, telemetry and stick writer. It is ticked once per pilot step and advances at most one action per tick. It never opens a socket, sends MAVLink outside `flight.link`, sleeps or starts a process.

### The two forms

**A sequence.** `build_sequence()` returns a list of actions, and `ON_FINISH` says what follows the last one. The actions come from the toolkit's `tools/sequence.py`, which is on the pilot's path:

```python
from sequence import Mode, Sticks, Wait

ON_FINISH = 'loiter'

def build_sequence():
    return [Mode(4, 3, timeout=8.), Wait(10.)]
```

| Action | Meaning |
|---|---|
| `Wait(seconds)` | keep the last sticks |
| `Mode(main, sub=0, timeout=5)` | request the PX4 custom mode every second until the heartbeat shows it; fails on timeout |
| `Expect(main, sub=0, timeout=5)` | wait, without a request, for PX4 to switch by itself (a failsafe); fails on timeout |
| `Select(main, sub=0, seconds=2)` | request at once and every second, also when PX4 already shows the mode (a person moving the switch); PX4 must show it at the end |
| `Sticks(pitch, roll, throttle, seconds, yaw=0)` | MANUAL_CONTROL x/y/z/r, normalized: pitch, roll and yaw −1..1, throttle 0..1. Not angles; negative pitch is nose up |
| `RcOff()` / `RcOn()` | the transmitter off and on: no stick frames in between (PX4's RC-loss failsafe), heartbeats and mode requests go on. They alternate, no `Sticks` in between, `RcOn` before the end |

Main modes 1–8 and submodes 0–255 are accepted; for example 4/3 is AUTO_LOITER, 4/4 AUTO_MISSION, 6 OFFBOARD, 7 STABILIZED. PX4 enters OFFBOARD only while a source sends the offboard signal. Any mode that PX4 shows and the sequence did not ask for fails the sequence.

`ON_FINISH`:
- `'hold'`: PX4 must be in Stabilized; the roll and yaw sticks centre and the pilot's altitude hold continues.
- `'loiter'`: PX4 must be in AUTO_LOITER (4/3); the pilot streams neutral sticks and heartbeats until it is stopped, and keeps streaming through later mode changes.
- `'release'`: the pilot lets go of the sticks (exit 0); it does not disarm.

**A reacting script.** `make_script()` returns an object with `finish` (`'hold'`, `'loiter'` or `'release'`), `begin()`, `cancel(reason)` and `tick(flight, now)`. The loader sets `name`, `input`, `state` (`'waiting'`), `index` and `reason`. `begin()` sets `state = 'running'`. The object checks its own modes and its own end: it sets `state` to `'complete'` or `'failed'` (with `reason`), and calls `flight.go('loiter', ...)` or `flight.release(...)` as its finish requires.

**`INPUT = 'rc'`** at module level makes the pilot a transmitter from its first frame: RC_CHANNELS_OVERRIDE through the FC's own `RC_MAP_*`, `RCn_MIN/TRIM/MAX/REV`, `COM_FLTMODEn` and switch thresholds (`tools/rc_output.py`), with the arm switch on, the mode switch on Stabilized and the offboard switch off. PX4 reads it like a receiver, switches included. A ground station's joystick and a real receiver must then stay off.

### The `flight` object

What a script may use; nothing else is part of the contract.

| Name | Meaning |
|---|---|
| `flight.vehicle` | latest telemetry: `mode`, `sub_mode`, `armed`, `vehicle_type`, `cas`, `height`, `climb`, `pitch`, `roll` (deg), `north`, `east`, `v_north`, `v_east` (EKF origin), `params`, `texts` (last 5 STATUSTEXT), `text_log` (`(time, text)`, last 500), `mission_seq`, `mission_requests` (consume them), `mission_ack` (`(time, result)`), `seen` (arrival times) |
| `flight.sticks` | `[x, y, z, r]`: pitch, roll −1000..1000, throttle 0..1000, yaw; sent every step |
| `flight.pitch_command`, `flight.pitch_scale` | the pitch command in degrees and `FW_MAN_P_MAX` |
| `flight.hold_level(dt)`, `flight.dt` | one step of wings-level flight with the altitude hold; the step's duration |
| `flight.a` | the numbers: `cruise_throttle`, `altitude` and the other `[pilot]` keys, `climb_bank` |
| `flight.link.send(message)` | send a pymavlink message (for example a mission upload) |
| `flight.command(id, *params)`, `flight.mode_command_id` | send COMMAND_LONG to the FC; the set-mode command (`flight.command(flight.mode_command_id, 1, main, sub)`) |
| `flight.go(state, reason)`, `flight.release(reason)` | change the pilot's state (`'loiter'`); let go of the sticks |
| `flight.rc` | with `INPUT = 'rc'`: `rc.switch['offboard']`, `rc.switch['arm']`, `rc.set_mode('MISSION')` and the other `FLTMODE` names |
| `flight.rc_paused` | set True to emulate receiver loss (no stick frames) |
| `flight.log_dir` | the pilot's `--log-dir`, for the script's own record |

`now` in `tick` is the pilot's clock (simulated in lockstep): measure every duration with it.

### Imports and moving a script

- `tools/` is on the pilot's path: `from sequence import ...`.
- The parent of a script's folder is appended to `sys.path`, so scripts in one folder import each other as `<folder>.<name>` (for example `from commands.agent_r5_steps import at`).
- A script written for an earlier copy of this framework needs only its import line changed, from `from commands.sequence import ...` to `from sequence import ...`. Actions from any other module are refused at load time with that hint. A `make_script()` script that imports no actions needs no change.
- Check a script offline before a flight:

  ```sh
  "$PY" -B -c "import sys; sys.path.insert(0, 'tools'); from sequence import load_script; s = load_script('<path>'); print(s.finish, getattr(s, 'actions', s))"
  ```

`status.json` reports the script: `after_script`, `after_state` (`disabled`, `waiting`, `running`, `complete`, `failed`, `cancelled`), `after_step` (from 0), `after_reason`.

## Known limits

- **Ground-station takeover through simhost.** The takeover check acts on MANUAL_CONTROL from another system that reaches the pilot's port. simhost's relay passes only the flight controller's messages to its peers, so a ground station's joystick on the relay goes to PX4 and never reaches the pilot: through simhost, this hand-back does not trigger. Keep the ground station's joystick off while the pilot flies; use `stop` instead.
- **Fixed limits.** The readiness window (CAS ≤ 30 m/s, |roll| ≤ 5°, ±5 m), the ground check (CAS ≤ 5 m/s, ±5 m), the pitch hold limit (±8°), the bank height (20 m), the level-off rule (45°, 150 m), the stick slew rates and the accepted ranges of the numbers come from the first vehicle (a 1.3 kg fixed-wing). A vehicle outside them needs them moved into `[pilot]`.
- **Takeoff.** Runway takeoff from rest only: a hand launch, catapult or vertical takeoff needs another pilot.
