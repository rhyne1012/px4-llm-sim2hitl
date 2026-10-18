# px4-llm-sim2hitl

[繁體中文](README.md) | **English**

> **This is a translation.** The authoritative README is [README.md](README.md) (Traditional Chinese); where the two differ, follow README.md. Translated from README.md with SHA-256 `6ee73be35b5710da203400ccb84165b5e114d19d88dcf466105537afbe8ff1de`: if `sha256sum README.md` prints something else, this translation is behind. The AI rules ([AGENTS.md](AGENTS.md)) and the folder READMEs are in Traditional Chinese only; an AI agent reads them without trouble.

Flight-control development kit: MATLAB/Simulink aircraft model → C → SITL (minimal PX4) → custom PX4 firmware → HITL on a real flight controller (Pixhawk). When you develop with an AI, its working rules are in [AGENTS.md](AGENTS.md).

![Overview: requirements & spec → SITL → HITL on the real flight controller; the human picks the next step, the AI does the work](images/overview.svg)

**The example aircraft is SkySurfer** (fixed-wing): `model/`, `hitl/aircraft/skysurfer/`, the model release names `skysurfer-…` and `SkySurfer_Core` belong to the aircraft. The kit is called `px4-llm-sim2hitl`: folders use the full name (`~/.cache/px4-llm-sim2hitl`, `~/.local/share/px4-llm-sim2hitl/venv`, `~/.config/px4-llm-sim2hitl`), environment variables the short name `SIM2HITL_*` (environment variables cannot contain a hyphen). To use your own aircraft, see stage 1.1.

> Status: the move from the old macOS project to Ubuntu is done and the whole pipeline runs (see the last section).

## The spirit of this project

**This is not an automation toolkit, and it should not grow into one that tries to cover every development case; it is a handover that lets your AI understand this pipeline from the start.** How the path goes from the aircraft model, the PX4 source, SITL, building and flashing to the real flight controller, where the traps are, what has already been verified and what counts as right are all written down in the docs (this README, [AGENTS.md](AGENTS.md), the folder READMEs) and in the existing checks. Once your AI has read them it can pick up where things stand without working out the whole pipeline from scratch each time, and spend its time and tokens on the real work: debugging and developing with you.

An analogy: every new conversation, your AI is like a colleague on their first day at work. This package is the handover left by the people before: how the system works, where the traps are, what has already been verified, the house rules, and one basic route that has actually been run end to end (model → SITL → flashing → HITL). A handover does not do the work for the newcomer, nor does it list every situation they will meet; it lets them put their mind on your problem from day one, and know where to start when something new comes up. New lessons and the rules agreed with you go back into the handover, so the next newcomer gets up to speed faster.

- **Understanding first, tools second**: commands and scripts only fix steps that are already understood. The docs say why things are done this way and where the traps are, for example the SD-card read error, the ground model that never turns the aircraft, and when the wind starts. That way the AI knows where to look when something goes wrong, and does not force things through by bypassing a safety check.
- **Purpose**: hand this package to someone else so that they and their AI can go from changing the aircraft model and developing flight control all the way to building, flashing and HITL.
- **Simple, light, one source**: everything lives in one place; reuse existing programs and checks; add nothing for cases that may never come.
- **The AI speaks plainly**: the AI looks up and handles the technical details; it asks the human only about goals, choices and success criteria.
- **Stage 1 matters most**: the AI first reads the PX4 source of the locked version, lays out the feasible ways to plug in in plain words, and the human chooses; then it suggests a "minimal end-to-end run" first, so the whole path works and is recorded, and later changes go through the automation.
- **Stage 3 in one go**: build → flash → identity check → parameters → boot file → HITL → flight log, in one command; before starting, tell the human what is on the FC now, then always flash again (when only an external module changed, the version hashes the FC reports may stay the same, so old and new cannot be told apart).
- **Automation grows with the development**: tools are a by-product of understanding. When the same thing has been done two or three times, the AI suggests turning it into a command or script in the project, and the human decides; fewer tokens the more it is used.
- **Environment not hard-coded, pass criteria hard-coded**: paths, compiler, MATLAB and the PX4 source tree are found automatically and can be set; when changing platform, ask the AI to check the official docs. The yardsticks (version lock, check tolerances, 4 ms, load thresholds) do not change with the environment.
- **No permission levels**: at the end of each stage ask "next step 1/2/3"; no item-by-item questions within a stage. The runtime safety checks (FC identity, disarmed, read-back, recovery) cannot be bypassed; see AGENTS section 3.
- **Remind, don't block**: non-default flight parameters run and are recorded; whatever looks wrong is told to the human, who decides.
- **SITL and HITL use the same yardstick**: the same scenario, the same judging program, the same kind of log (ULog); the difference between the two is itself the information you are after.

## Pipeline

1. **Requirements and specification**: agree first on what to do and what counts as success.
   - 1.1 Aircraft model and trim (when changing the aircraft or the model)
   - 1.2 Algorithm, deployment and acceptance
2. **SITL (simulation on the computer)**: simulate repeatedly; results are saved as `trace.csv` + ULog (MATLAB reads it directly).
3. **HITL (automatic build, flash, test)**
   - 3.1 Manual HITL (`./runbridge` + QGC)
   - 3.2 Exit check: after QGC turns HITL off, confirm the control surfaces get outputs (not done yet)

## Environment setup (first time)

Verified on **Ubuntu 24.04 x86-64** only. Each item below says "why" and "how it was done on the validation machine (Ubuntu)"; the how is only an example. When changing platform or version, **ask the AI to check the item's official documentation first** and confirm the right way before installing.

| Item | Why | Ubuntu 24.04 way (example) | How to check |
|---|---|---|---|
| Python environment | runtime, tests, SITL, analysis | install [uv](https://docs.astral.sh/uv/), then `./runbridge --setup` (venv in `~/.local/share/px4-llm-sim2hitl/venv`) | `./runbridge --check-python` |
| MATLAB | only to change the aircraft model (code generation in stage 1.1): R2026b + Simulink + Simulink Coder + Embedded Coder + Aerospace Blockset. No Java needed | MathWorks installer; connecting the MATLAB MCP server is recommended so the AI can drive MATLAB | `matlab` on PATH, or set `SIM2HITL_MATLAB_ROOT` |
| C compiler | plant and HIL libraries | the system gcc (`CC` selects another) | `cc --version` |
| PX4 source and toolchain | SITL and firmware builds; version locked in [px4/px4_lock.json](px4/px4_lock.json) | download the locked tag outside the project, `python3 px4/check_px4_tree.py --path <tree> --remember`; toolchain with PX4's official script `bash <tree>/Tools/setup/ubuntu.sh --no-sim-tools` (no Gazebo; uses sudo). Official reference: PX4 docs "Ubuntu Development Environment" | `python3 px4/check_px4_tree.py` gives PASS |
| **Real-time scheduling limit** | the worker thread of the 4 ms loop uses real-time scheduling (Linux: SCHED_FIFO, priority 2). It runs without the permission, but with less timing margin: on the validation machine the 600 s load test was at most 3.7 ms late (threshold 4 ms), 0.47 ms with the permission | desktop programs are started by the systemd user service, which `/etc/security/limits.d` does not reach; use systemd, both files are needed: `/etc/systemd/system/user@<UID>.service.d/rtprio.conf` with `[Service]` and `LimitRTPRIO=10` (the limit of the user manager itself), and `/etc/systemd/user.conf.d/rtprio.conf` with `[Manager]` and `DefaultLimitRTPRIO=10` (the value it applies to the desktop programs it starts; with only the first one, desktop programs were still at 0 after a reboot), `sudo systemctl daemon-reload`, then log in again. For one process only, temporarily: `sudo prlimit --pid <PID> --rtprio=10:10`. Official references: systemd.exec(5) `LimitRTPRIO=`, sched(7) | `ulimit -r` ≥ 2; `scheduler.time_constraint_result` of `./runbridge status` is 0 |
| Serial port | connect to the Pixhawk (USB CDC-ACM) | add the user to the `dialout` group; disable ModemManager (it probes newly plugged serial ports): `sudo systemctl disable --now ModemManager` | `ls -l /dev/ttyACM*`, `groups` |
| QGC | the human watches and operates the FC (3.1) | the AppImage released on the official GitHub (validation machine: v5.1.5 in `~/Applications/`, checked against the published SHA-256); system packages per QGC's official Linux instructions (the validation machine added `libfuse2t64 gstreamer1.0-plugins-bad gstreamer1.0-libav libxcb-cursor0`). **Turn USB auto-connect off** and use only UDP 14550 to the runtime, or QGC competes with the owner for the FC serial port: in `~/.config/QGroundControl/QGroundControl.ini`, section `[AutoConnect]`, set `autoConnectPixhawk`, `autoConnectSiKRadio`, `autoConnectRTKGPS`, `autoConnectLibrePilot`, `autoConnectZeroConf` to `false` and `autoConnectUDP=true` (after QGC's first start has created the file and QGC is closed; or untick them in QGC's Application Settings → Comm Links) | with QGC open, `lsof -p <QGC PID>` shows only UDP 14550 and no `/dev/ttyACM*` |

## Common commands

```sh
./runbridge --help                    # all actions
./runbridge update-model --generate   # stage one: MATLAB code generation -> model/generated (needs MATLAB)
./runbridge update-model              # stage two: build, four gates, publish the model release (no MATLAB connection needed)
./runbridge bridge                    # start the owner (holds the model and the serial port); QGC connects over UDP
./runbridge status                    # owner status
./runbridge takeoff --altitude 100 --after template_offboard   # 3.1: with the model running on the ground, automatic takeoff -> Hold -> OFFBOARD (the template; the FC must run 02_template) -> Hold (QGC's menu cannot switch a fixed-wing to Offboard)
./runbridge deploy-test --release deploy/<recipe>           # stage 3: plan only (what is on the FC now, what would be done)
./runbridge deploy-test --release deploy/<recipe> --flash   # the usual one: build if needed -> flash -> parameters -> boot file -> hitl-run
./runbridge deploy-test --release deploy/<recipe> --reuse   # only when the human asks for it: keep the FC's firmware, parameters -> boot file -> hitl-run
```

## Known issues

- **Model and PX4 parameters do not match (airspeed too high)**: PX4's `FW_THR_TRIM=0.6`, while this aircraft model needs only about 0.115 throttle for level flight at 15 m/s. As a result the native loiter and SITL airspeeds are 20–30 m/s (target 15 m/s), and in HITL, when TECS climbs, the airspeed shoots up and the altitude overshoots (which is why the template's altitude check FAILs). Following the principles in [AGENTS](AGENTS.md), check the model first (thrust, drag, mass), then decide whether the model needs fixing or this aircraft's PX4 parameters must be set to match the real aircraft.
- **The 3.2 exit check is not done**: the baseline parameters of `deploy/00_native` assign no physical servo outputs (`PWM_MAIN_FUNC*`, `PWM_AUX_FUNC*` all 0), `GPS_1_CONFIG=0`, the airspeed sensor driver is off; with HITL turned off there is no output at all. It needs the real aircraft's wiring and parameters.
- **Real-time permission for ordinary users**: see the real-time scheduling item in "Environment setup"; without it things run, but with little timing margin.

## Validation record (2026-10-18, Ubuntu 24.04)

| Item | Result |
|---|---|
| Model release `skysurfer-6d1cf7a3…` (after the rename; before it `f53eee94…`) | four gates PASS; the core's and C Truth's errors against the reference data are identical to the last digit with before the rename; against the reference data recorded on macOS, apart from the angle of attack / sideslip that are undefined at rest, the difference is ≤ 6.2e-15 |
| Offline tests | all 14 files OK (2026-10-18, after the rename). The recovery test of `test_runbridge_fake` used to misjudge on a very busy machine (its status polling could not catch the fake FC's 2.3 s reboot); after it was changed to send QGC traffic for the whole recovery, it PASSes even with all 28 cores busy |
| 600 s load (no window) | PASS; at most 0.47 ms late with the real-time permission |
| SITL | build PASS; the metrics of the reference scenario `stabilized_steps` are the same as the macOS record; speed: 1000 runs (60 s simulated each) measured 140.8 s, about 55 s with larger batches; the template `guidance_template` PASSes |
| ULog and MATLAB | both SITL and HITL ULogs can be plotted with MATLAB `ulogreader` (`analysis/matlab/ulog_overview_plot.m`, no Java needed) and converted to CSV (`analysis/ulog_export.py`) |
| HITL (real FC) | 00_native baseline `hitl-run` PASS (2026-10-17 UTC): 60 s loiter, 2.78 turns; 23,039 steps, 0 late, at most 0.79 ms; USB writes at most 0.26 ms; the FC measured the sensors at 250.009 Hz |
| Stage 3 in one go | `deploy/01_sdfix` (native + SD-card fix) flashed and run through with `deploy-test`: the FC reports NuttX `8d3ed2a2…` (the expected one); 0 parameters written; `hitl-run` all seven parts PASS, 60.13 s loiter, 2.78 turns, 23,104 steps, 0 late, at most 0.19 ms; flight log (10.9 MB) downloaded twice identical, strict parse PASS |
| Template `02_template` (HITL, 2026-10-18) | the whole pipeline PASS (rebuild, flash, identity, parameters, boot file); **the FC accepts the OFFBOARD signal the module sends from inside the firmware**. Sequence changed to: 15 s after entering OFFBOARD turn 30°, at 35 s climb 10 m, 60 s in all; the loiter altitude check now uses the altitude at the start of the loiter ±15 m: flight PASS; course +29.1° (no overshoot, settles in 15.2 s), max bank 14°; **altitude overshoot 33%** (SITL 0%), not back within ±0.5 m before OFFBOARD ends, check FAIL. At the same time the airspeed went from 21 to 28 m/s: too much throttle when TECS adds energy (`FW_THR_TRIM=0.6` against the model's about 0.115), part of the model/PX4 parameter mismatch, to be investigated |
| 3.1 manual HITL (2026-10-18, FC on `02_template`) | QGC on UDP only; QGC's mode menu cannot switch a fixed-wing to Offboard, so `./runbridge takeoff --altitude 100 --after template_offboard` was used. Results almost the same as the automatic test: course +29.0° (settles in 15.4 s), max bank 14.2°, altitude overshoot 31% → template check FAIL (as above, model/parameter mismatch); 0 late; after model stop and `recover`: disarmed, `SYS_HITL=1`, nothing pending |
| FC at handover | 2026-10-18 07:22 UTC, `deploy-test --flash` from `02_template` back to `01_sdfix`: all PASS (60.0 s loiter, 2.79 turns, 0 late), boot file removed; record in [deploy/01_sdfix](deploy/01_sdfix/README.md) |
| Rename to `px4-llm-sim2hitl` (2026-10-18) | the kit no longer borrows the aircraft's name: full-name folders, environment variables `SIM2HITL_*`, PX4 modules `plant_sim` / `guidance_template`, plant function prefix `plant_`; records carry no paths of the local machine. MATLAB code regeneration differs only in time stamps and the temporary path; new model release four gates PASS; offline tests all pass; both SITL scenarios as before the rename (template PASS); after rebuilding `02_template` NuttX `8d3ed2a2…` is unchanged; FC (01) `hitl-run` all seven parts PASS: 60.07 s loiter, 2.77 turns, 0 late, at most 0.20 ms, log downloaded twice identical, strict parse PASS |
| Wind (2026-10-19) | The model's wind is an external input (steady wind, or shear + gust + turbulence; by default it starts after airborne); SITL and HITL share one `wind` format (`plant/wind.py`), explained in [plant README](plant/README.md) "風" (wind) and, for the AI, as a checklist in AGENTS. Source slx: the Dryden turbulence block un-commented (it had been switched off because zero airspeed on the ground divided by zero), a 5 m/s floor on its airspeed input, noise interval 0.1 s -> 4 ms. Without wind the results are bit-identical to before; the three Simulink comparisons (one with every wind component on) match source and core copy bit for bit; four gates PASS (`skysurfer-1c2b65fe…`, the HIL library's wind case equals Simulink); offline tests all pass; the SITL reference scenarios and the template as before, `wind_steady` and `wind_low_altitude` as expected |
| Wind HITL on the real FC (2026-10-19, FC on `01_sdfix`) | Scenario `hitl/scenarios/wind_steady_5.json` (ground start + steady wind 5 m/s from the north, starting 5 m above ground, ramped over 5 s); manual flow: `recover` → `model-start --scenario` → `takeoff --altitude 100` → 60 s loiter → `model-stop` → `recover --hil-force-disarm`. Flow: 60 s loiter, 1.87 turns, 0 late steps (worst 1.13 ms), 0 serial errors; after recovery unarmed, `SYS_HITL=1`, nothing pending; FC log (no. 53, newer than the newest before the flight, 52) downloaded twice identical, strict parse PASS. Wind: PX4's EKF (about one sample per second) reached 4.7 m/s about 20 s in, still climbing; above 100 m the mean was 5.01 m/s from 0° (truth 5.00 m/s from 0°); the airspeed selector's own wind estimate reached about 5 m/s after about 40 s. Side by side with the previous no-wind run (2026-10-18, 01): turns 1.87 / 2.77, radius 78 / 83 m, height 98–102 / 100–113 m, mean loiter airspeed 17.3 / 24.3 m/s (about 15.5 late in the windy run), a 24 ms gap in the FC log at the moment of arming / none; differences only, no rule agreed beforehand |
| Clean-clone run | 2026-10-18 (after the rename): cloned from git into a new folder, own cache, no MATLAB connection: `update-model` builds **the same build-id** `skysurfer-6d1cf7a3…`, four gates PASS; offline tests all pass; **`01_sdfix` rebuilt from scratch**: PX4 `d6f12ad1…`, NuttX `8d3ed2a2…` and the firmware size are the same as on the FC (the `.px4` contains the build time, so the file SHA differs); no local paths in the records |
| Wrap-up | the core spirit is in this README ("The spirit of this project"); clean-clone run done; on GitHub: https://github.com/rhyne1012/px4-llm-sim2hitl (2026-10-18) |
