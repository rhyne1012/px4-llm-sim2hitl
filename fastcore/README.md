# Fast core

A generated C version of a vehicle's JSBSim model, for work that needs many simulated hours: reinforcement learning, sweeps, Monte Carlo. JSBSim stays the reference; the core is derived from it and checked against it every time it is generated.

Status: v2 draft, 2026-11-27. Verified on Testbird only (`docs/verification.md`).

## Why

On sim-bound training, JSBSim at 1 kHz is too slow: measured on 2026-11-27, SkyTalon's PPO training would take 7.4× as long (14 h → 4.4 days). Most of JSBSim's time goes into its generality (the property tree, interpreted function trees, models the vehicle does not use), not into the physics of one vehicle.

## How

```
vehicle folder (JSBSim XML)  →  fastcore/gen.py  →  <name>_core.c/.h, lib<name>_core.so, <name>_core.json
                                                       ↑ includes fastcore/runtime/fastcore.h (shared physics)
                                fastcore/check.py →  check.json (against JSBSim)
                                fastcore/bench.py →  bench.json (speed)
```

- **Translated from the vehicle:** aerodynamic functions and tables, flight-control components, mass and inertia, engine and propeller constants. Constants are converted with JSBSim's own unit factors, so the core holds the same numbers JSBSim does.
- **Shared, written once:** equations of motion, atmosphere, table interpolation, quaternion kinematics. Each formula names the JSBSim 1.3.3 source it follows.
- **Refused, not approximated:** any element the generator does not translate stops it with the file and the element. A core never silently differs from its definition.

The generator lives in this repository. A generated core is a build product of the vehicle repository that uses it: run `gen.py` on the vehicle folder from the toolkit version the vehicle repository pins, and keep `check.json` next to the core. Training code stays in the training repository.

```
python3 fastcore/gen.py <vehicle folder> --out <build dir>
JSBSIM_PYTHON=<jsbsim 1.3.3 wheel> <python with numpy> fastcore/check.py <vehicle folder> --out <build dir>
```

Use a core only with a passing `check.json` whose `core` hashes match the vehicle files it was generated from.

## Interface

C (`<name>_core.h`) and Python (`fastcore.py`, ctypes; calls release the GIL). All arrays are float64, row-major, one row per vehicle; the column names are in `<name>_core.json`.

| Array | Contents |
|---|---|
| `x` (state) | NED position from an origin (m); body velocity relative to the ground (m/s); quaternion body → NED, scalar first; body rates (rad/s); propeller speeds (rad/s). Then held flight-control outputs, the flight-control components' own states, and auxiliary values. |
| `u` (inputs) | The JSBSim command properties the flight control reads, e.g. `fcs/elevator-cmd-norm`, `fcs/throttle-cmd-norm[0]`. |
| `env` | Wind NED (m/s), gravity (m/s²), altitude of the NED origin and of the ground above sea level (m). |
| `y` (outputs) | Forces and moments (total, aerodynamic, per propeller), specific force (what an accelerometer measures), α, β, airspeed, dynamic pressure, density, propeller rpm, current and power, height of the lowest contact point above the ground, and the value of every aerodynamic function. |

- `reset(x, u)` initialises the flight-control states from the inputs, as JSBSim's `RunIC` does.
- `step(x, u, env, dt, k, y)` advances `k` steps of `dt` (default 4 ms, RK4), with the flight control updated once per step.
- `eval(x, env, jsbsim_order, xd, y)` gives derivatives and outputs at given states without advancing them, e.g. for control-effectiveness derivatives by finite differences on the actuator positions.

Call `step` with many vehicles and several steps at once: one call costs a few µs of Python overhead.

## What the core leaves out

Written into each `<name>_core.json` as `not_modelled`:

- **Ground reactions.** The core is for flight. The outputs give the height of the lowest contact point so a training loop can end an episode on contact.
- **Earth.** Flat and non-rotating, constant gravity from `env`: no Coriolis or transport rate.
- **Atmosphere.** Standard day, first layer only (below 11 km). No turbulence; the wind is constant within a call.
- **Timing.** α̇ comes from the previous derivative evaluation, as JSBSim's comes from the previous frame. `aero/cl-squared` comes from the current lift, where JSBSim uses the previous frame's. The flight control runs once per step and holds its outputs over the step.

## Translated JSBSim elements

| Area | Translated |
|---|---|
| Aerodynamics | axes `LIFT DRAG SIDE` or `X Y Z`, and `ROLL PITCH YAW` (body frame); pre-functions; the AERORP moment transfer |
| Functions | `value property table` (1D, 2D) `product sum difference quotient pow sqrt abs sin cos tan asin acos atan atan2 exp ln log10 min max avg fraction integer mod lt le gt ge eq nq and or not ifthen` |
| Properties | `aero/` (α, β and their rates and degrees, qbar, ci2vel, bi2vel, cl-squared, qbar-area, h_b-cg/mac), `velocities/` (vt, mach, body and aero rates, aero velocities), `metrics/`, `atmosphere/` (rho, T, P), `position/` (h-sl, h-agl), and the `fcs/` values written by flight-control components |
| Flight control | `summer`, `pure_gain`, `aerosurface_scale`, `lag_filter`, `actuator` (lag, rate limit, bias, clip); `clipto` with numbers |
| Mass | empty weight, CG, the inertia matrix with JSBSim's sign convention for the products of inertia |
| Propulsion | `brushless_dc_motor` with a fixed-pitch, direct-drive `propeller` (C_THRUST, C_POWER, CT/CP_RPM_FACTOR), thruster `location` and `orient` |

Checked so far is what Testbird uses: wind axes, 1D tables, `product pow abs`, `summer pure_gain actuator`, one motor and propeller with zero orientation. The rest is translated but has no check yet; a vehicle that uses it gets one from its own `check.py` run.

Not yet: point masses, fuel tanks, other engine and thruster types, 3D tables, `fcs_function`, `switch`, `kinematic` and the other flight-control components, properties as parameters (`<clipto>` with properties), stall hysteresis, external and buoyant forces. They are added when a vehicle needs them, with a check that covers them.

## Checks

`check.py` runs two checks and writes them to `check.json`:

1. **Snapshots (translation).** JSBSim flies from random states (8–32 m/s, α −25…35°, β ±20°, rates ±1.5 rad/s, random inputs, wind in half of them) on a non-rotating Earth. At a random frame its full state, including actuator positions, propeller speed and the previous frame's accelerations, goes into the core in JSBSim's order, and every force, moment, aerodynamic function and propeller value is compared. Limit: relative error 1e-9; rounding is about 1e-12.
2. **Flights (simplifications).** From trimmed level flight, JSBSim as simhost runs it (1 ms, Adams-Bashforth 2, rotating WGS84 Earth) and the core at 1 ms and 4 ms fly eight open-loop input sequences for 20 s: hold, elevator, aileron and rudder doublets, throttle steps, a multisine on all inputs, a crosswind, and a pull to the stall. Limits, as the largest difference within the first 10 s for the 4 ms core: position 0.3 m, attitude 0.3°, airspeed 0.03 m/s. A person set them on 2026-11-27, after the first Testbird measurement (worst 0.08 m, 0.09°, 0.008 m/s). The flights run open loop, so differences grow with time; the 20 s values are recorded but not judged.

`bench.py` measures the core and JSBSim on the same machine.
