# px4-llm-sim2hitl

[繁體中文](README.md) | **English**

> **This is a translation.** The authoritative README is [README.md](README.md) (Traditional Chinese); where the two differ, follow README.md. Translated from README.md with SHA-256 `399f4544ad6ed503a870096513ddd9646228beb9624ca0f301515566ef359f7c`: if `sha256sum README.md` prints something else, this translation is behind. The AI rules ([AGENTS.md](AGENTS.md)) and the folder READMEs are in Traditional Chinese only; an AI agent reads them without trouble.

Flight-control development kit: MATLAB/Simulink aircraft model → C → SITL (minimal PX4) → custom PX4 firmware → HITL on a real flight controller (Pixhawk). When you develop with an AI, its working rules are in [AGENTS.md](AGENTS.md).

![Overview: requirements & spec → SITL → HITL on the real flight controller; the human picks the next step, the AI does the work](images/overview.svg)

**The example aircraft is SkySurfer** (fixed-wing): `model/`, `hitl/aircraft/skysurfer/`, the model release names `skysurfer-…` and `SkySurfer_Core` belong to the aircraft. The kit is called `px4-llm-sim2hitl`: folders use the full name (on Linux `~/.cache/px4-llm-sim2hitl`, `~/.local/share/px4-llm-sim2hitl/venv`, `~/.config/px4-llm-sim2hitl`; `./runbridge where` shows this machine's actual locations), environment variables the short name `SIM2HITL_*` (environment variables cannot contain a hyphen). To use your own aircraft, see stage 1.1.

> Status: the move from the old macOS project to Ubuntu is done and the whole pipeline runs (see "Verification matrix" and [records/verification.md](records/verification.md), in Traditional Chinese). On 2026-10-20 a second flight controller, the Cube Orange+, also went through one full round; what to check when changing flight controllers is in [fc/](fc/README.md).

## Getting started

**Just paste this link to your AI.** It reads this README and [AGENTS](AGENTS.md); from then on you only say what you want to do.

- **Only want to understand it**: any AI that can read web pages will do; ask it "what is this and what can it do for me".
- **Want to develop**: use an AI that can run commands on your computer (for example Claude Code or Codex). Paste the link the same way and ask it to download the repo to a fixed folder on your computer (do not move it later; to move it, recover first as AGENTS says).
  - The first time: say "set this computer up following the README's environment setup". It checks item by item and asks you to paste once when it needs sudo or a permission. **The whole pipeline is verified only on Ubuntu 24.04 (x86-64)**; macOS (Apple silicon) is verified up to SITL (see "Verification matrix" and [platforms/macos.md](platforms/macos.md), in Traditional Chinese); other systems are untested, the AI will try following the official docs, but expect extra time on pitfalls.
  - After that: just say what you want, for example "I want to switch to my own aircraft" or "I want to build a new guidance algorithm". It starts the conversation at stage 1, "Requirements and spec".
- **Use a capable AI**: it has to read long documents, write code, run commands and understand the results. A model that is too small, or set to low reasoning, tends to skip the docs and guess. Tested and works: GPT-6.1 sol (reasoning: medium).

Example opening: "Please download https://github.com/rhyne1012/px4-llm-sim2hitl to ~/Developer, read the README and AGENTS first, then talk with me about stage 1: I want to ..."

## The spirit of this project

**This is not an automation toolkit, and it should not grow into one that tries to cover every development case; it is a handover that lets your AI understand this pipeline from the start.** How the path goes from the aircraft model, the PX4 source, SITL, building and flashing to the real flight controller, where the traps are, what has already been verified and what counts as right are all written down in the docs (this README, [AGENTS.md](AGENTS.md), the folder READMEs) and in the existing checks. Once your AI has read them it can pick up where things stand without working out the whole pipeline from scratch each time, and spend its time and tokens on the real work: debugging and developing with you.

An analogy: every new conversation, your AI is like a colleague on their first day at work. This package is the handover left by the people before: how the system works, where the traps are, what has already been verified, the house rules, and one basic route that has actually been run end to end (model → SITL → flashing → HITL). A handover does not do the work for the newcomer, nor does it list every situation they will meet; it lets them put their mind on your problem from day one, and know where to start when something new comes up. New lessons and the rules agreed with you go back into the handover, so the next newcomer gets up to speed faster.

- **Understanding first, tools second**: commands and scripts only fix steps that are already understood. The docs say why things are done this way and where the traps are, for example the SD-card read error, the ground model that never turns the aircraft, and when the wind starts. That way the AI knows where to look when something goes wrong, and does not force things through by bypassing a safety check.
- **A conclusion is as big as its evidence**: every conclusion can name its basis (which test, which record) and its scope (version, recipe, FC, mode); with little evidence, make the claim smaller rather than run more tests. Seeing no difference is not the same as there being none; SITL and HITL share one aircraft model, so agreement between them does not prove the model is like the real aircraft; when the conditions change, old conclusions are checked again. How the AI does this: [AGENTS](AGENTS.md) "下結論之前" (before concluding).
- **Purpose**: hand this package to someone else so that they and their AI can go from changing the aircraft model and developing flight control all the way to building, flashing and HITL.
- **Simple, light, one source**: everything lives in one place; reuse existing programs and checks; add nothing for cases that may never come.
- **The AI speaks plainly**: the AI looks up and handles the technical details; it asks the human only about goals, choices and success criteria.
- **Stage 1 matters most**: the AI first reads the PX4 source of the locked version, lays out the feasible ways to plug in in plain words, and the human chooses; then it suggests a "minimal end-to-end run" first, so the whole path works and is recorded, and later changes go through the automation.
- **Stage 3 in one go**: build → flash → identity check → parameters → boot file → HITL → flight log, in one command; before starting, tell the human what is on the FC now, then always flash again (when only an external module changed, the version hashes the FC reports may stay the same, so old and new cannot be told apart).
- **Automation grows with the development**: tools are a by-product of understanding. When the same thing has been done two or three times, the AI suggests turning it into a command or script in the project, and the human decides; fewer tokens the more it is used.
- **Environment not hard-coded, pass criteria hard-coded**: paths, compiler, MATLAB and the PX4 source tree are found automatically and can be set; when changing platform, ask the AI to check the official docs. The yardsticks (version lock, check tolerances, 4 ms, load thresholds) do not change with the environment.
- **No permission levels**: at the end of each stage ask "next step 1/2/3"; no item-by-item questions within a stage. The runtime safety checks (FC identity, disarmed, read-back, recovery) cannot be bypassed; see AGENTS section 3.
- **Remind, don't block**: non-default flight parameters run and are recorded; whatever looks wrong is told to the human, who decides.
- **SITL and HITL use the same yardstick**: the same scenario, the same judging program, the same kind of log (ULog); the difference between the two is itself the information you are after. "The same yardstick" means a requirement has the same definition, baseline and judgment on both sides; only requirements both sides can measure are compared side by side. For example the reduced SITL has no EKF and no Commander, so how OFFBOARD exits can only be answered in HITL.

## Pipeline

1. **Requirements and specification**: agree first on what to do and what counts as success.
   - 1.1 Aircraft model and trim (when changing the aircraft or the model)
   - 1.2 Algorithm, deployment and acceptance
2. **SITL (simulation on the computer)**: simulate repeatedly; results are saved as `trace.csv` + ULog (MATLAB reads it directly).
3. **HITL (automatic build, flash, test)**
   - 3.1 Manual HITL (`./runbridge` + QGC)
   - 3.2 Exit check: after QGC turns HITL off, confirm the control surfaces get outputs (not done yet)

## Environment setup (first time)

The whole pipeline is verified on **Ubuntu 24.04 x86-64** only (how far each platform is verified: "Verification matrix"; macOS platform differences: [platforms/macos.md](platforms/macos.md)). Below is what to prepare and how to check it; why each item is needed and how the validation machine (Ubuntu) did it are in [platforms/ubuntu.md](platforms/ubuntu.md) (Traditional Chinese). The how is only an example. When changing platform or version, **ask the AI to check the item's official documentation first** and confirm the right way before installing.

| Item | How to check |
|---|---|
| Python environment | `./runbridge --check-python` |
| MATLAB | `matlab` on PATH, or set `SIM2HITL_MATLAB_ROOT` |
| C compiler | `cc --version` |
| PX4 source and toolchain | `python3 px4/check_px4_tree.py` gives PASS |
| **Real-time scheduling limit** | `ulimit -r` ≥ 2; `scheduler.time_constraint_result` of `./runbridge status` is 0 |
| Serial port | `ls -l /dev/ttyACM*`, `groups` |
| QGC | with QGC open, `lsof -p <QGC PID>` shows only UDP 14550 and no `/dev/ttyACM*` |

**Two checkouts on one machine** (e.g. the kit and your own fork): the runtime state follows the folder path, so it is separate already; the following are shared by default, and an environment variable separates each. The cache folder (`SIM2HITL_CACHE`); the SITL build folder (`build/px4_sitl_default_sim2hitl` in the PX4 tree, `SIM2HITL_SITL_SUFFIX`) — if shared, a rebuild in one checkout makes the other one's SITL run this one's aircraft, without any error; the PX4 instance numbers of SITL runs at the same time (`run_sitl.py --instance-base`); the firmware build tree (`<PX4 tree>-build`, `SIM2HITL_PX4_BUILD_TREE`; when shared, do not build in both at once). There is one FC: only one checkout may run its owner at a time; before switching, `recover` and close the owner where it ran.

## Common commands

```sh
./runbridge --help                    # all actions
./runbridge where                     # this machine's actual locations (venv python, cache, PX4 tree, model release); where python prints just one
./runbridge update-model --generate   # stage one: MATLAB code generation -> model/generated (needs MATLAB)
./runbridge update-model              # stage two: build, four gates, publish the model release (no MATLAB connection needed)
./runbridge bridge                    # start the owner (holds the model and the serial port); QGC connects over UDP
./runbridge status                    # owner status
./runbridge model-start              # 3.1: start the model on the ground (first check nothing is pending and status shows empty missing_conditions); --scenario <scene> for another scene
./runbridge takeoff --altitude 100 --after template_offboard   # 3.1: with the model running on the ground, automatic takeoff -> Hold -> OFFBOARD (the template; the FC must run 02_template) -> Hold (QGC's menu cannot switch a fixed-wing to Offboard)
./runbridge deploy-test --release deploy/<recipe>           # stage 3: plan only (what is on the FC now, what would be done)
./runbridge deploy-test --release deploy/<recipe> --flash   # the usual one: build if needed -> flash -> parameters -> boot file -> hitl-run
./runbridge deploy-test --release deploy/<recipe> --reuse   # only when the human asks for it: keep the FC's firmware, parameters -> boot file -> hitl-run
```

Manual HITL (3.1) order: `bridge` starts the owner → `status` confirms recovery is complete and the start conditions are met → `model-start` → confirm the model runs on the ground → `takeoff` (then you can take over with the QGC joystick; where to click is in the [hitl README](hitl/README.md) section on flying with the QGC joystick). To finish: `model-stop`, then `recover` following the recovery rules in the [hitl README](hitl/README.md) (add `--hil-force-disarm` when the flight ended in the air), and finally `shutdown` to close the owner.

## Known issues

- **K1 Model and PX4 parameters do not match (airspeed too high)**: PX4's `FW_THR_TRIM=0.6`, while this aircraft model needs only about 0.115 throttle for level flight at 15 m/s. Observed so far: the native loiter and SITL airspeeds are 20–30 m/s (target 15 m/s); in HITL, when TECS climbs, the airspeed shoots up and the altitude overshoots, which is why the template's altitude check FAILs. The throttle-trim gap is one possible cause, but how the two are linked and how much it explains is not yet confirmed. Another clue: in the windy HITL of 2026-10-19 the FC happened to run firmware with a throttle trim of 0.115 (see the correction in [records/verification.md](records/verification.md) V13); the mean loiter airspeed was 17.3 m/s, about 15.5 late in the run, closer to the target than with a trim of 0.6. This supports the throttle-trim hypothesis, but that flight also had wind and different firmware, so it is not proof. Following the principles in [AGENTS](AGENTS.md), check the model first (thrust, drag, mass), then decide whether the model needs fixing or this aircraft's PX4 parameters must be set to match the real aircraft.
- **K2 The 3.2 exit check is not done**: the baseline parameters of `deploy/00_native` assign no physical servo outputs (`PWM_MAIN_FUNC*`, `PWM_AUX_FUNC*` all 0), `GPS_1_CONFIG=0`, the airspeed sensor driver is off; with HITL turned off there is no output at all. It needs the real aircraft's wiring and parameters.
- **K3 Real-time permission for ordinary users**: see the real-time scheduling item in "Environment setup"; without it things run, but with little timing margin.

## Verification matrix

Only which stage was verified on which platform and when; each cell is PASS, FAIL or untested, and untested does not count as supported.

| Stage | Linux (Ubuntu 24.04 x86-64) | macOS (27.0.1 arm64) |
|---|---|---|
| Source tree and environment check | PASS (2026-10-18; 2026-10-20 on a second machine) | PASS (2026-10-20) |
| Code generation (MATLAB R2026b) | PASS (2026-10-20, rerun without instruction-set extensions) | PASS (2026-10-20) |
| Model release (four gates, 60 s pacing) | PASS (2026-10-20; the same day a second machine without MATLAB also PASS with the project's minimal headers) | PASS (2026-10-20) |
| Trim | PASS (2026-10-20, identical to the previous release to the last digit) | PASS (2026-10-20, identical to the last digit) |
| SITL reference scenario and template | PASS (2026-10-20; also PASS on the second machine) | PASS (2026-10-20, same metrics) |
| SITL many instances | PASS (2026-10-18, 1000 runs) | PASS (2026-10-20, one hang in the first batch, see the macOS notes) |
| Offline runtime tests | PASS (2026-10-20; all 15 files on the second machine) | PASS (2026-10-20, 194 tests) |
| Firmware build | PASS (2026-10-18, 6C; 2026-10-20, Cube Orange+) | untested |
| Hardware in the loop (HITL) | PASS (2026-10-18, 6C; on 2026-10-20 the 6C had a timing FAIL without real-time privilege on a busy machine, see [records/verification.md](records/verification.md) V14; 2026-10-20 Cube Orange+ PASS for all three recipes, without real-time privilege on an idle machine) | untested |

How far each flight controller (Pixhawk 6C, Cube Orange+) is verified: see the [fc README](fc/README.md) table of verified flight controllers (Traditional Chinese).

The method, numbers, scope and corrections behind each cell are in [records/verification.md](records/verification.md) (one numbered entry each, e.g. V14; Traditional Chinese).

## Validation record

The run-by-run method, numbers, scope and corrections moved to [records/verification.md](records/verification.md) (one numbered entry each; Traditional Chinese).
