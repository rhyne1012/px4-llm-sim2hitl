# Architecture (v2)

Status: draft, 2026-11-27. This page fixes the parts and the contracts between them; each part's own README holds the detail.

## Layers

```
PX4 (flight control)        JSBSim (flight dynamics)          upstream, locked versions, unmodified
        \                         /
     px4-llm-sim2hitl: simulation host, deployment, test cases, records, agent rules
                     |  pinned version
     vehicle repository: vehicle definition, PX4 modules, recipes, tasks, records
```

- **Upstream projects** are used as released, at locked versions. Anything they cannot do is added beside them, never patched into them. A PX4 patch is a last resort; it is kept minimal and listed in the PX4 lock.
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

The simulation host applies the profile between JSBSim and PX4. Effects that JSBSim cannot express belong in this layer. Each effect is written once, in plain C under `avionics/`, and used by both the simulation host and the fast core; the servo signal chain (`avionics/servo_chain.h`: PWM hold, then transport delay, on the servo channels) is the first. The sensor models are still in the simulation host (`simhost/src/avionics.cpp`).

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

A Python package with a command line drives everything that is not physics:

- recipes, firmware build, flashing, identity check, parameters and boot file
- running test cases, checks and records

It also enforces the safety rules: flight-controller identity, disarmed state, parameter read-back and recovery cannot be skipped.

### Anchor

The anchor is the recorded reference behaviour of a vehicle:

- steady states
- responses to control inputs
- the ground roll
- statistics of the wind response

The anchor tools live here, and the anchor answers live in the vehicle repository. Changing a vehicle's anchor requires a person's approval.

### Machine resources

Several vehicle repositories can share one computer. A machine-wide registry and lock coordinates flight controllers, serial ports, SITL instance numbers and ports, and PX4 build trees per PX4 version.

## Versions

- The toolkit is released with version tags.
- A vehicle repository pins one tag in `sim2hitl.lock`, together with the PX4 and JSBSim versions that tag supports.
- A toolkit change is tested against vehicle repositories through a local development link before it is released. Each vehicle repository then upgrades on its own schedule and runs its own checks.

## Known limits of the upstream projects

| Limit | Where it is handled |
|---|---|
| JSBSim tables clamp instead of extrapolating | vehicle definitions give tables enough breakpoints |
| FGTrim fails with electric motors faster than about 0.25 s (`GetSteadyState` uses fixed 0.5 s steps) | steady states are found by flying (`tools/vehicle_check.py`) |
| JSBSim has no RK4 integrator | Adams-Bashforth 2 with 1 kHz substeps |
| Propeller thrust uses only the axial inflow (no rotor drag in edgewise flight) | aerodynamic functions in the vehicle definition (multirotors) |
| `execrate` has no phase, so PWM hold timing cannot be modelled in JSBSim | avionics layer |
| JSBSim at 1 kHz is too slow for sim-bound training (SkyTalon PPO: 7.4× as long) | the fast core (`fastcore/`), generated from the JSBSim definition |

## Not in scope

- A physics engine of our own. The fast core is a translation of a JSBSim definition, checked against JSBSim; it adds no physics of its own.
- Flight-control algorithms. They live in vehicle repositories.
- Training frameworks. Training repositories pin a vehicle repository and hand back artifacts.
- Real-flight operations beyond records and checks.
