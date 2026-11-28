# Architecture (v2)

Status: as of v2.1.0 (2026-11-28); a part marked planned is not built. This page fixes the parts and the contracts between them; each part's own README holds the detail.

## Layers

```
PX4 (flight control)        JSBSim (flight dynamics)          upstream, locked versions, not forked
        \                         /
     px4-llm-sim2hitl: simulation host, deployment, test cases, records, agent rules
                     |  pinned version
     vehicle repository: vehicle definition, PX4 modules, recipes, tasks, records
```

- **Upstream projects** are used as released, at locked versions, and are not forked. Anything they cannot do is added beside them where it can be. A PX4 patch is a last resort; it is kept minimal and listed with its reason in the PX4 lock (`px4/lock.toml`).
- **The toolkit** (this repository) holds no real vehicle. Its test vehicles (`vehicles/`) exist only to test the toolkit.
- **A vehicle repository** pins a toolkit version and holds everything specific to one vehicle.

## Parts

### Vehicle definition

A vehicle is a JSBSim aircraft folder (`<name>/<name>.xml`, `Engines/`, `Systems/`), plus `vehicle.toml`:

- the JSBSim model name
- the PX4 airframe and parameter file for each recipe kind
- the actuator map: PX4 output channel → JSBSim command property, with scale, sign and kind (servo or motor)
- the default avionics profile

The JSBSim folder is the single source of truth for the vehicle's physics. Configurations (mass, CG, payload, servos) and experiments (coefficient scaling, faults) are files of property settings, `configs/*.toml`, applied at start; they never edit the XML. What a configuration may move is in the definition: point masses for mass and CG, declared properties for experiment knobs, JSBSim's actuator failure properties for faults. One file serves SITL, HITL and the fast core, and an unknown property is an error at every level.

### Avionics

Sensors and the servo signal chain belong to the flight controller, not to the airframe. An avionics profile describes them per flight controller:

- the IMU, magnetometer, barometer, airspeed sensor and GPS, with their noise, bias, delay and rate
- the PWM output timing, and the servo delay and hold

Today there is one sensor model for every flight controller (white noise in `simhost/src/avionics.cpp`, a fixed 250 Hz HIL rate); per-flight-controller profiles with bias and delay are planned. The simulation host applies the profile between JSBSim and PX4. Effects that JSBSim cannot express belong in this layer. Each effect is written once, in plain C under `avionics/`, and used by both the simulation host and the fast core; the servo signal chain (`avionics/servo_chain.h`: PWM hold, then transport delay, on the servo channels) is the first. The sensor models are still in the simulation host (`simhost/src/avionics.cpp`).

### Simulation host

One C++ program, linked with the locked JSBSim:

- **Physics.** JSBSim runs at 1 kHz internally and exchanges data with PX4 at the HIL rate.
- **PX4 interface.** PX4's standard HIL MAVLink messages: out `HIL_SENSOR`, `HIL_GPS` and, optionally, `HIL_STATE_QUATERNION` (ground truth); in `HIL_ACTUATOR_CONTROLS`. The C headers are generated with mavgen from the message definitions in the locked PX4 tree.
- **Transports.**
  - SITL: a TCP server on port 4560. PX4's `simulator_mavlink` connects to it, in lockstep: PX4's actuator messages advance the clock.
  - SITL FC: a vehicle repository's own flight-controller build on the computer, with its own startup instead of PX4's posix rcS. `simulator_mavlink` runs in UDP mode (`--sitl-udp`), and its MAVLink instance is a second UDP link (`--mavlink-udp`).
  - HITL: the flight controller's serial port, in real time with a fixed deadline per step.
- **Other MAVLink users.** A UDP relay (`--relay-port`) gives a flight script, a pilot and a ground station the flight controller's MAVLink at the same time. In lockstep, a pilot process that runs on the simulated clock can gate the simulation (`--simclock`, `--pilot-sync`), so that its keep-alive and its checks never fall behind PX4's simulated time.
- **Inputs at run time.**
  - Wind, turbulence and gusts use JSBSim's own models.
  - Faults use JSBSim's actuator fail properties and the avionics layer.
  - Scenario events are applied at scheduled times (`--at T:PROPERTY=VALUE`).
- **Outputs.** A time history of the truth state and of the commands, for the record.
- **Several vehicles in one world.** Planned (one JSBSim instance per vehicle); not built yet.

SITL and HITL run the same program with the same vehicle, avionics and scenario. Only the transport and the clock differ.

### Algorithm modules

Custom flight-control code lives in the vehicle repository as a PX4 external module (`EXTERNAL_MODULES_LOCATION`). Each module is split in two:

- a pure core with no PX4 dependency
- a thin PX4 shell around it

The same core runs in the algorithm-level tests, in training, in SITL, in HITL and in flight.

### Fast core

For training and other sim-bound work, `fastcore/gen.py` turns a vehicle's JSBSim folder into a C core with a C and Python interface: the vehicle's own parts (aerodynamic functions and tables, flight-control components, mass, propulsion constants) are translated, and the shared physics is written once. Everything a configuration may change is a per-vehicle parameter of the core, under the same property names, so a batch can mix configurations and a failure can start mid-episode. JSBSim stays the reference: `fastcore/check.py` compares every generated core with JSBSim, exactly at the level of forces and moments and within stated limits in flight. The generator lives here; a generated core is a build product of the vehicle repository that uses it. See `fastcore/README.md`.

### Test cases

Status: planned as a format. Today a recipe's `hitl.json` names a command script (Python, tied to the pilot and PX4's modes) and a check over the ULog; the check is the part that already runs the same way in SITL, HITL and flight.

A test case is data and has three parts:

1. **Scenario:** initial state, environment, faults and a timeline of actions.
2. **Check:** a Python function over the record that returns PASS or FAIL with its numbers.
3. **Record:** the ULog, the simulation host's time history, and every version involved (toolkit, vehicle, PX4, JSBSim, firmware, parameters).

The same test case runs at every level, and each level proves something different:

| Level | Proves |
|---|---|
| Algorithm (core only, no PX4) | the algorithm's logic, at sweep speed |
| SITL (PX4 on the computer) | integration with PX4: modes, estimator, parameters |
| HITL (real flight controller) | timing, serial links, the flight controller's own logging |
| Flight | the real vehicle, judged by the same check on the ULog |

### Orchestration

Python tools in `tools/` drive everything that is not physics:

| Tool | Does | Documented in |
|---|---|---|
| `recipe.py` | reads a deploy recipe and checks a full parameter readback against it | [recipes.md](recipes.md) |
| `px4build.py` | builds a recipe's firmware: pinned PX4, committed patches, external modules | [recipes.md](recipes.md) |
| `fc.py` | one flight controller over MAVLink: identity, parameters (exact bytes), SD files (MAVLink FTP), logs, disarm, reboot, recover | [recipes.md](recipes.md) |
| `deploy.py` | puts a recipe on a flight controller: flash, parameters, boot file, logger topics, one reboot, the proof | [recipes.md](recipes.md) |
| `sitl_fc.py` | a recipe's SITL FC: PX4 SITL built with its modules and started like the flight controller | [sitl_fc.md](sitl_fc.md) |
| `pilot.py`, `sequence.py` | the pilot (a fixed-wing takeoff flown with sticks) and the command scripts it runs | [pilot.md](pilot.md) |
| `fly.py` | one test flight of a recipe, SITL or HITL: FC, simhost, pilot, recover, the flight's log, the check | [recipes.md](recipes.md) |
| `linear.py` | trims, linear models and transfer functions of a fixed-wing vehicle, checked against the nonlinear model; the compare of two such records | its docstring; `linear_model.m` reads them into MATLAB |

They enforce the safety rules: recipe and board roles (a flight recipe goes only onto a board a person marked for an aircraft, and only with `--flight`), flight-controller identity, disarmed state, parameter read-back, a proven reboot, a log newer than the flight's start, and the recovery after a HITL flight cannot be skipped.

### Anchor

The anchor is the recorded reference behaviour of a vehicle:

- steady states
- responses to control inputs
- the ground roll
- statistics of the wind response

The anchor tools live here, and the anchor answers live in the vehicle repository. Changing a vehicle's anchor requires a person's approval. Partly built: `tools/linear.py` records the behaviour and compares two records; the lock is still the vehicle repository's own.

### Machine resources

Planned. Several vehicle repositories can share one computer. A machine-wide registry and lock coordinates flight controllers, serial ports, SITL instance numbers and ports, and PX4 build trees per PX4 version.

## Versions

- The toolkit is released with version tags, vMAJOR.MINOR.PATCH: MAJOR for a very large change (for example another flight stack such as ArduPilot), MINOR for a new PX4 or JSBSim version or a change vehicle repositories must act on to upgrade, PATCH for everyday changes that need nothing from them.
- A vehicle repository pins one tag in `sim2hitl.lock`, together with the PX4 and JSBSim versions that tag supports, and stays on it while its work goes on. Its own version numbers, if any, are its own choice.
- A toolkit change is tested against vehicle repositories through a local development link before it is released. Each vehicle repository then upgrades on its own schedule and runs its own checks.

## Known limits of the upstream projects

| Limit | Where it is handled |
|---|---|
| JSBSim tables clamp instead of extrapolating | vehicle definitions give tables enough breakpoints; a propeller beyond its table gives a thrust that stops changing, so trims start from a scanned angle of attack and throttle (`tools/linear.py`) |
| FGTrim fails with electric motors faster than about 0.25 s (`GetSteadyState` uses fixed 0.5 s steps) | trims solve the equilibrium with the engines run to their steady speed (`tools/linear.py`), or are flown (`tools/vehicle_check.py`); FGTrim is reported next to them as a check |
| FGLinearization's engine-speed rows are wrong for an electric motor and propeller (Testbird: thrust follows the throttle at once) | `tools/linear.py` linearises by its own central differences, with the thrust quasi-steady and the engine's lag measured separately |
| `RunIC` also advances the flight-control components (they keep the step they were loaded with), and `forces/hold-down` zeroes the velocities | actuator and engine poles are measured on free runs with the airframe's own response taken out (`tools/linear.py`) |
| JSBSim has no RK4 integrator | Adams-Bashforth 2 with 1 kHz substeps |
| Propeller thrust uses only the axial inflow (no rotor drag in edgewise flight) | aerodynamic functions in the vehicle definition (multirotors) |
| `execrate` has no phase, so PWM hold timing cannot be modelled in JSBSim | avionics layer |
| JSBSim at 1 kHz is too slow for sim-bound training (a fixed-wing PPO training: 7.4× as long) | the fast core (`fastcore/`), generated from the JSBSim definition |

## Not in scope

- A physics engine of our own. The fast core is a translation of a JSBSim definition, checked against JSBSim; it adds no physics of its own.
- Flight-control algorithms. They live in vehicle repositories.
- Training frameworks. Training repositories pin a vehicle repository and hand back artifacts.
- Real-flight operations beyond records and checks.
