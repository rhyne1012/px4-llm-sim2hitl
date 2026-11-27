# Testbird

The toolkit's fixed-wing test vehicle. It is not a real aircraft, and it never syncs with one. Its only job is to exercise the toolkit end to end (SITL, HITL, deployment, anchor) with a plausible small UAV.

| | |
|---|---|
| Mass | 6.0 kg: a 4.8 kg airframe and a 1.2 kg battery (a point mass), both at the reference point |
| Wing | span 2.60 m, area 0.75 m² (aspect ratio 9.0), mean chord 0.2885 m |
| Tail | horizontal 0.12 m², vertical 0.065 m², both 1.00 m behind the CG |
| Propulsion | brushless motor (6S, 340 rpm/V, 0.06 Ω) on an APC 18x8E propeller, tractor |
| Gear | tricycle, steerable nose wheel, brakes on the mains |
| Surfaces | elevator, aileron (single channel), rudder: ±25°, servo lag 25 rad/s, 300 °/s |

## Files

- `testbird.xml`: the vehicle (JSBSim 1.3.3).
- `Systems/controls.xml`: the actuators, with their sign conventions.
- `Engines/testbird_motor.xml`: the motor (JSBSim `brushless_dc_motor`).
- `Engines/APC_18x8E.xml`: the propeller, copied unchanged from JSBSim's `engine/` folder (LGPL-2.1). It is APC's PER3 measurement data, converted by JSBSim's `apc_dat_to_jsbsim_xml.py`.
- `aeromatic/answers.txt`: the first attempt (see below).
- `vehicle.toml`: how PX4's outputs drive the model, the start position, and the pilot's numbers (`[pilot]`).
- `configs/`: model configurations (`aft_cg.toml`, `slow_servos.toml`).
- `recipes/cubeorangeplus_hitl/`: its deploy recipe ([docs/recipes.md](../../docs/recipes.md)): PX4 v1.18.0 plus the Cube Orange+ HIL board variant, no external module; airframe 2100 (its `param set-default` values in the `airframe` section), the control allocation and HIL outputs of PX4's plane SITL airframe, and Testbird's speeds and trim. The image and parameter list are build products (`tools/px4build.py`), not tracked.
- `commands/loiter.py`, `checks/loiter_check.py`: the test flight: after the pilot's level-off, 60 s in PX4's loiter, judged on the ULog (limits in the check).

## Flying it

```sh
PY=<python with pymavlink and pyulog>
"$PY" -B tools/fly.py sitl vehicles/testbird/recipes/cubeorangeplus_hitl --vehicle vehicles/testbird --instance 9
"$PY" -B tools/fly.py hitl vehicles/testbird/recipes/cubeorangeplus_hitl --vehicle vehicles/testbird --link /dev/serial/by-id/<the FC> --deploy flash
```

HITL needs the aircraft made safe first (propellers off, ESCs unpowered) and flashes the Cube with Testbird's image. The SITL flight passed on 2026-11-27 (docs/verification.md); the HITL flight through this pipeline has not been flown yet.

## Where the numbers come from

AeromatiC++ 3.3.21, JSBSim's own generator, was tried first. Its empirical sizing is meant for full-size aircraft and fails at this scale: CD0 came out NaN, the wing t/c 0.9 % and the fuselage diameter 1.37 m. The aerodynamics are therefore first-order textbook estimates from the geometry, all about the CG:

- **Lift.**
  - Wing lift slope from the Helmbold lifting-line formula, 2πA/(2+√(A²+4)) = 5.04/rad.
  - Downwash dε/dα = 2CLα,w/(πA) = 0.36.
  - Tail lift slope 3.88/rad (A = 4), tail efficiency 0.9, elevator effectiveness τ = 0.45.
  - Total: CLα = 5.40/rad, CL0 = 0.40, stall near 9° (CLmax 1.25), and flat-plate behaviour beyond it.
- **Drag.** CD0 = 0.030, with gear. Induced drag K = 1/(πeA), e = 0.8, which gives 0.0442. Separated-flow drag past the stall.
- **Pitch.** Tail volume V_H = 0.555.
  - Static margin 12 %, so Cmα = −0.648/rad.
  - Cmq = −2ηV_H·CLα,t·l_t/c̄ = −13.4.
  - Cmα̇ = Cmq·dε/dα = −4.8.
  - Cmδe = −0.872/rad.
  - Cm0 = 0.013 puts the elevator-neutral trim near 16 m/s.
- **Lateral-directional.** Fin volume V_V = 0.033.
  - Static derivatives: CYβ −0.35, Cnβ 0.08, Clβ −0.10 (5° dihedral equivalent).
  - Damping and cross terms (strip theory, reduced for tip loss): Clp −0.55, Cnr −0.09, Clr 0.12, Cnp −0.05.
  - Ailerons: Clδa 0.18, with adverse yaw Cnδa −0.015.
  - Rudder: Cnδr 0.046, CYδr −0.119, Clδr −0.005.
  - With Clβ = −0.07, the spiral mode diverged fast enough to roll the aircraft over in about 20 s with no roll control; −0.10 makes it nearly neutral.
- **Inertia.** From radii of gyration 0.25 (roll, of the half span), 0.38 (pitch, of the half length) and 0.39 (yaw). The battery sits at the CG, so it adds nothing; moving it (`configs/aft_cg.toml`) moves the CG at constant mass and adds its parallel-axis inertia.
- **Configurations and knobs.** `configs/aft_cg.toml` (battery 10 cm aft: CG 2 cm aft, static margin about 5 %), `configs/slow_servos.toml` (slow servos: 50 Hz PWM sampled 8 ms into the frame, 40 ms delay). Declared properties `aero/scale/cm-alpha` and `aero/scale/elevator` (default 1) scale Cmα and the elevator derivatives for experiments.
- **Gear.** Springs for about 15 mm static deflection, with damping ratio about 0.6. The mains carry 85 % of the weight.

## Checks

`python3 tools/vehicle_check.py vehicles/testbird --speeds 12 15 17 20 23` (JSBSim 1.3.3, dt 2 ms), 2026-11-27:

| | |
|---|---|
| Rest on the ground | level (θ 0.07°), gear compression 14–15 mm |
| Static thrust | 43.7 N (thrust/weight 0.74) at 6657 rpm, 831 W |

Steady level flight, flown (the elevator holds the airspeed, the throttle the height, the ailerons the wings level):

| Airspeed (m/s) | α (°) | elevator | throttle | thrust (N) | power (W) |
|---|---|---|---|---|---|
| 12 | 5.33 | −0.126 | 0.49 | 4.38 | 76 |
| 15 | 1.85 | −0.021 | 0.57 | 4.58 | 101 |
| 17 | 0.47 | 0.020 | 0.64 | 5.14 | 129 |
| 20 | −0.89 | 0.060 | 0.74 | 6.45 | 192 |
| 23 | −1.74 | 0.086 | 0.85 | 8.14 | 278 |

At 17 m/s, the hand calculation from the coefficients above gives α 0.43°, elevator 0.021 and drag 5.1 N.

The rows are steady after 60 s of flight (climb rate below 0.05 m/s, airspeed within 0.1 m/s), averaged over the last 5 s. The wings sit at −0.6° to −1.1° of bank against the propeller torque.

JSBSim's own trim (FGTrim) fails on this vehicle ("udot doesn't appear to be trimmable"). `FGPropulsion::GetSteadyState` marches the propeller speed in fixed 0.5 s steps, which is unstable for a motor and propeller whose time constant is about 0.1 s. The PX4 JSBSim bridge's Rascal shows the same message. The toolkit therefore finds steady states by flying, rather than by changing the vehicle's physics to suit the trim routine.
