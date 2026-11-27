# Fast core

A generated C version of a vehicle's JSBSim model, for work that needs many simulated hours: reinforcement learning, sweeps, Monte Carlo. JSBSim stays the reference; the core is derived from it and checked against it every time it is generated.

Status: v2 draft, 2026-11-27. Verified on Testbird only (`docs/verification.md`).

## Why

On sim-bound training, JSBSim at 1 kHz is too slow: measured on 2026-11-27, SkyTalon's PPO training would take 7.4× as long (14 h → 4.4 days). Most of JSBSim's time goes into its generality (the property tree, interpreted function trees, models the vehicle does not use), not into the physics of one vehicle.

## How

```
vehicle folder (JSBSim XML, vehicle.toml)  →  fastcore/gen.py  →  <name>_core.c/.h, lib<name>_core.so, <name>_core.json
                                     includes fastcore/runtime/fastcore.h (shared physics), avionics/servo_chain.h
                                              fastcore/check.py →  check.json (against JSBSim)
                                              fastcore/bench.py →  bench.json (speed)
```

- **Translated from the vehicle:** aerodynamic functions and tables, flight-control components, mass and inertia with point masses, engine and propeller constants. Constants are converted with JSBSim's own unit factors, so the core holds the same numbers JSBSim does.
- **Shared, written once:** equations of motion, atmosphere, table interpolation, quaternion kinematics (`runtime/fastcore.h`), each formula naming the JSBSim 1.3.3 source it follows; the servo signal chain (`avionics/servo_chain.h`), the same code simhost runs.
- **Refused, not approximated:** any element the generator does not translate stops it with the file and the element. A core never silently differs from its definition.

The generator lives in this repository. A generated core is a build product of the vehicle repository that uses it: run `gen.py` on the vehicle folder from the toolkit version the vehicle repository pins, and keep `check.json` next to the core. Training code stays in the training repository.

```
python3 fastcore/gen.py <vehicle folder> --out <build dir>
JSBSIM_PYTHON=<jsbsim 1.3.3 wheel> <python with numpy> fastcore/check.py <vehicle folder> --out <build dir>
```

Use a core only with a passing `check.json` whose `core` hashes match the vehicle files it was generated from.

## Parameters and configurations

What may differ between vehicles of one batch, or change during an episode, is a parameter: a column of the array `p`, named by its JSBSim property and in JSBSim's units. A core has these parameters:

| Parameter | From | Example |
|---|---|---|
| point masses | `<pointmass>` in the mass balance | `inertia/pointmass-weight-lbs[0]`, `inertia/pointmass-location-X-inches[0]` |
| declared properties | `<property value="...">` in the aerodynamics or a system | `aero/scale/cm-alpha` |
| actuator failures | every `<actuator>` | `fcs/elevator-servo/malfunction/fail_stuck` (also `fail_zero`, `fail_hardover`) |
| servo chain | `vehicle.toml` actuators of `kind = "servo"` | `avionics/servo/pwm-period-s`, `pwm-phase-s`, `delay-s` |

A configuration (a CG, a payload, slow servos) or an experiment (a scaled coefficient) is a file of such settings, `vehicles/<name>/configs/*.toml`:

```toml
description = "battery 10 cm aft: CG x 0.42 m, static margin about 5 %"
[set]
"inertia/pointmass-location-X-inches[0]" = 19.6850394   # 0.50 m
```

The same file drives every level: `fastcore.load_config()` reads it for the core (`core.params(n, settings)`), and `tools/sitl_flight.py --config` and `tools/hitl_flight.py --config` pass it to simhost, which sets the JSBSim properties before the start and the servo chain from the `avionics/servo/*` keys. A name the vehicle does not have is an error everywhere: JSBSim would create the property silently. Failures during a flight are scenario events: `--at T:PROPERTY=VALUE` in the flight scripts and simhost, a change of `p` between `step` calls in training.

A vehicle exposes experiment knobs as declared properties that its functions multiply in (Testbird: `aero/scale/cm-alpha`, `aero/scale/elevator`), and models what can move as point masses (Testbird's battery, so its CG moves at constant mass). Mass, CG and inertia follow from the point masses in JSBSim's own order of operations.

## Interface

C (`<name>_core.h`) and Python (`fastcore.py`, ctypes; calls release the GIL). All arrays are float64, row-major, one row per vehicle; the column names are in `<name>_core.json`.

| Array | Contents |
|---|---|
| `x` (state) | NED position from an origin (m); body velocity relative to the ground (m/s); quaternion body → NED, scalar first; body rates (rad/s); propeller speeds (rad/s). Then held flight-control outputs, the flight-control components' states, auxiliary values, and the servo chain's state. |
| `u` (inputs) | The JSBSim command properties the flight control reads, e.g. `fcs/elevator-cmd-norm`, `fcs/throttle-cmd-norm[0]`. Servo inputs go through the servo chain first. |
| `p` (parameters) | See above; `core.params(n, settings...)` starts from the vehicle's values. |
| `env` | Wind NED (m/s), effective gravity (m/s², gravitation and centrifugal), altitude of the NED origin and of the ground above sea level (m), latitude (deg) and Earth rate (rad/s; 0 for a non-rotating Earth). |
| `y` (outputs) | Forces and moments (total, aerodynamic, per propeller), specific force (what an accelerometer measures), inertial body rates (what a gyro measures), α, β, airspeed, dynamic pressure, density, propeller rpm, current and power, mass, CG and inertia, height of the lowest contact point above the ground, and the value of every aerodynamic function. |

- `reset(x, u, p)` initialises the flight-control and servo-chain states from the inputs, as JSBSim's `RunIC` does.
- `step(x, u, p, env, dt, k, y)` advances `k` steps of `dt` (default 4 ms, RK4), with the servo chain and the flight control updated once per step. The servo-chain times must be whole multiples of `dt`; otherwise the call fails for that vehicle.
- `eval(x, p, env, jsbsim_order, xd, y)` gives derivatives and outputs at given states without advancing them, e.g. for control-effectiveness derivatives by finite differences on the actuator positions.

Call `step` with many vehicles and several steps at once: one call costs a few µs of Python overhead.

## What the core leaves out

Written into each `<name>_core.json` as `not_modelled`:

- **Ground reactions.** The core is for flight. The outputs give the height of the lowest contact point so a training loop can end an episode on contact.
- **Earth.** Flat, but rotating: the local frame turns with the Earth at the latitude of `env`, so the Coriolis acceleration and the Earth rate in Euler's equation and in the propeller's gyroscopic moment are modelled. Constant effective gravity from `env`; no curvature, transport rate or change of gravity with height. Leaving the rotation out cost 0.05 m and 0.03° in 10 s of level flight at 17 m/s (Coriolis, 0.001 m/s²).
- **Atmosphere.** Standard day, first layer only (below 11 km). No turbulence; the wind is constant within a call.
- **Timing.** α̇ comes from the previous derivative evaluation, as JSBSim's comes from the previous frame. `aero/cl-squared` comes from the current lift, where JSBSim uses the previous frame's. The servo chain and the flight control run once per step and hold their outputs over the step. Parameters are constant within a call.

## Translated JSBSim elements

| Area | Translated |
|---|---|
| Aerodynamics | axes `LIFT DRAG SIDE` or `X Y Z`, and `ROLL PITCH YAW` (body frame); pre-functions; declared properties; the AERORP moment transfer |
| Functions | `value property table` (1D, 2D) `product sum difference quotient pow sqrt abs sin cos tan asin acos atan atan2 exp ln log10 min max avg fraction integer mod lt le gt ge eq nq and or not ifthen` |
| Properties | `aero/` (α, β and their rates and degrees, qbar, ci2vel, bi2vel, cl-squared, qbar-area, h_b-cg/mac), `velocities/` (vt, mach, body and aero rates, aero velocities), `metrics/`, `atmosphere/` (rho, T, P), `position/` (h-sl, h-agl), declared properties, and the `fcs/` values written by flight-control components |
| Flight control | `summer`, `pure_gain`, `aerosurface_scale`, `lag_filter`, `actuator` (failures, lag, rate limit, bias, clip); numbers or declared properties for gains, lags, rate limits and clip limits |
| Mass | empty weight and CG, point masses (without `<form>`), the inertia matrix with JSBSim's sign convention for the products of inertia |
| Propulsion | `brushless_dc_motor` with a fixed-pitch, direct-drive `propeller` (C_THRUST, C_POWER, CT/CP_RPM_FACTOR), thruster `location` and `orient` |

Checked so far is what Testbird uses: wind axes, 1D tables, `product pow abs`, `summer pure_gain actuator` with all three failures, two point masses, two declared properties, one motor and propeller with zero orientation, the servo chain. The rest is translated but has no check yet; a vehicle that uses it gets one from its own `check.py` run.

Not yet: point-mass shapes, fuel tanks, other engine and thruster types, 3D tables, `fcs_function`, `switch`, `kinematic` and the other flight-control components, actuator deadband, hysteresis and delay, stall hysteresis, external and buoyant forces. They are added when a vehicle needs them, with a check that covers them.

## Checks

`check.py` runs three checks and writes them to `check.json`:

1. **Snapshots (translation).** JSBSim flies from random states (8–32 m/s, α −25…35°, β ±20°, rates ±1.5 rad/s, random inputs) with random point masses and declared properties, half of them on a non-rotating Earth (with wind in half of those) and half on the rotating Earth. On the rotating Earth JSBSim's reported Euler angles and the transformation it applies to the wind differ by about 2e-10 rad, so those run without wind. At a random frame its full state, including actuator positions, propeller speed and the previous frame's accelerations, goes into the core in JSBSim's order, and every force, moment, aerodynamic function, propeller value, mass property and angular acceleration is compared. Limit: relative error 1e-9; rounding is about 1e-12.
2. **Flight-control sequences (translation).** Random command sequences at 1 ms with actuator failures switched on and off at random, without and with two servo-chain settings. The core's actuator positions must equal JSBSim's frame by frame (limit 1e-12 rad); JSBSim's commands go through an independent Python servo chain (`fastcore.ServoChainRef`).
3. **Flights (simplifications).** From trimmed level flight, JSBSim as simhost runs it (1 ms, Adams-Bashforth 2, rotating WGS84 Earth) and the core at 1 ms and 4 ms fly open-loop input sequences for 20 s: hold, elevator, aileron and rudder doublets, throttle steps, a multisine on all inputs, a crosswind and a pull to the stall; four of them again with all of the vehicle's configuration files; and three failures switched on in flight (elevator stuck, rudder zero, aileron hardover, from 1500 m). Limits, as the largest difference within the first 10 s for the 4 ms core: position 0.3 m, attitude 0.3°, airspeed 0.03 m/s; for the failure flights the attitude limit is 1°. A person set them on 2026-11-27, after the first Testbird measurement (worst 0.08 m, 0.09°, 0.008 m/s) and, for the failures, after the aileron hardover: it ends in a spiral dive at 280°/s roll and 63 m/s, where JSBSim at 1 ms itself differs from JSBSim at 0.25 ms by 0.16° and 1° is about 3.5 ms of roll. The flights run open loop, so differences grow with time; the 20 s values are recorded but not judged.

`bench.py` measures the core and JSBSim on the same machine, with the default parameters and with each configuration file.
