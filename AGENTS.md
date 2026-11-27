# Rules for AI agents

These rules apply to any agent working in this repository or in a vehicle repository that uses it. A vehicle repository's own `AGENTS.md` adds what is specific to that vehicle (its model and anchor, its tasks, its flight controllers) and tells the agent to read this file first, at the version its `sim2hitl.lock` pins. The design is in [docs/architecture.md](docs/architecture.md).

**These documents are your understanding of the workflow.** Read them first instead of rediscovering it; spend the time on debugging and development with the person. When you learn a new pitfall or agree on a rule with the person, write it back into the right document (a rule for every vehicle here, a rule for one vehicle in its repository), so the next agent does not learn it again.

## Language

- Everything in a repository is in English: code, comments, commit messages, documentation, agent rules.
- `README.md` is in English and authoritative; `README.zh-TW.md` is its translation, in the formal written register of the language, updated in the same commit. Other languages may be added the same way.
- Talk to each person in the language they want, plainly. A person's quoted words stay verbatim in a document, followed by a translation.

## Before you conclude

**A conclusion is as large as its evidence.** Before you tell someone "it passed", write a report or write a lesson back, think about three things:

1. **What this run is meant to prove.** Read-only analysis, exploration, or acceptance against rules agreed beforehand; whether it proves that an integration works (the module really acts), that a requirement is met, or that it is better than native PX4. Conclude only on that one thing. When data needed for acceptance is missing, write "insufficient evidence"; do not substitute a quantity that happened to be measurable. A criterion thought of after seeing the result is not an acceptance criterion. A wrong criterion may be changed, but keep the original result, the reason and the conclusion under the new criterion. Exploration the person agreed to is done, but agreeing does not add evidence.
2. **How far the evidence reaches.** No difference seen means no difference within what was tested. A behaviour native PX4 also shows only says it is not caused by the new module alone. SITL and HITL share one vehicle model, so agreement between them does not show that the model matches the real vehicle. When the evidence is short, say less, or add one check for the missing part instead of rerunning everything.
3. **What would invalidate it.** A conclusion written into a document carries its basis (which run, which record) and scope (versions, vehicle, recipe, flight controller, mode) and says what change requires a recheck. Keep observation, suspected cause and current handling apart; an unconfirmed cause is "possibly". When new evidence overturns an old conclusion, correct the old sentence and mark the correction, not only add a new one elsewhere.

Examples from earlier work: a HITL record said which firmware the flight controller ran, but it ran another project's firmware with a different throttle trim, so a comparison mixed two trims and was corrected days later; when a record says "the FC runs X", read the FC back before relying on it. A deploy reported a parameter that was not at its default and still called itself PASS; a PASS must cover what it reports.

When a test fails, keep the failing run's evidence, tell the person where it is, then analyse. A fixed result is stored separately; it never overwrites the failure.

## 1. Working with the person

- **Speak plainly.** Look up and handle technical details yourself; bring only decisions to the person, one at a time.
- Work in the stages of the README's development flow. **At the end of a stage, ask "next step 1/2/3"**; within a stage, do not ask for each step.
- **To show a workflow or tool works, use the fewest cases** (one flight, two episodes). Statistics are a separate question for the person to raise and decide.
- When a tool's safety check stops you, a FAIL has no known cause, or a person's hands are needed (replug USB, power off, remove propellers): stop and explain. Do not work around it or retry on your own.

### Stage 1, requirements and specification: settle the whole workflow first

Investigate first and propose; confirm with the person only the **goals, choices and success criteria**:

1. **Listen**: what to build, which situations to fly, what counts as success.
2. **The vehicle model.** Which vehicle, and what is known about it (shape, mass, CG, inertia, aerodynamics, control surfaces or rotors). The model is the vehicle's JSBSim folder (`vehicles/testbird` is the example): `tools/vehicle_check.py` checks rest on the ground, static thrust and trimmed flight before any PX4 run. Differences between tasks (CG, servo delay, failures) are configuration files, not copies of the model. The actuator channels and the pilot's numbers are in `vehicle.toml` (`[pilot]`). A vehicle with an anchor changes its model only with the person's approval. A new vehicle takes off in the lockstep SITL FC before HITL.
3. **Algorithm, deployment and acceptance.**
   - **Read the locked PX4 source before discussing the integration.** For what the person wants to build, lay out PX4's control chain for the vehicle type (for a fixed-wing roughly: guidance and mode management → altitude and speed → attitude → rates → control allocation), the modes and the modules involved, and the options that would work. For each option say plainly: whether PX4's source changes, whether it can switch back to native, who owns the failsafe, the flash space, what SITL must simulate. Examples: OFFBOARD (how many layers are handed over is a flag; a module can send the setpoints inside the firmware, no companion computer needed), a PX4 patch that changes or removes a native module, PX4's external modes. **These are examples, not the list.** The person chooses; start only after checking in the source that the choice works.
   - Anticipate SITL and HITL problems: both run PX4's EKF (the SITL FC is PX4 on the computer, HITL the real flight controller); coexistence with the existing flight modes; flash space (a native image may already use most of it); HITL has no transmitter: PX4's RC is the pilot's sticks, and when they stop PX4's RC-loss failsafe takes over, so a new algorithm's entry and exit modes must fit the pilot's rules ([docs/pilot.md](docs/pilot.md)).
   - Agree on: the flight controller and whether HITL is set up; when the algorithm takes over, how it exits, how it falls back to native on failure; which manoeuvre proves it acts. **A flight controller without a recipe yet**: check whether its default firmware has `pwm_out_sim` (HITL needs it), the board identity it reports (`board_version` is the USB product id), its bootloader's USB name, the parameters its boot scripts set, and the flash margin; then build its recipe ([docs/recipes.md](docs/recipes.md)).
   - **How it is deployed is the precondition of HITL.**
   - Write a one-page specification in the module's README: what this proves (see "Before you conclude"), the goal, the integration, the acceptance measures of SITL and HITL. The estimators differ between them, so compare behaviour and gaps, not point by point.
   - **For every requirement, say which side answers it.** Measure what both sides can measure the same way on both and put them side by side; for what only one side can answer, say why. Not measured is "not tested"; missing or undecidable data is "insufficient evidence"; neither is a pass. Judge PASS or FAIL only by rules agreed beforehand; without agreed rules give a grounded reading instead (what deserves attention, which numbers cannot be read literally, what to look at next); thresholds are the person's. Keep "the workflow ran" apart from "each requirement". A comparison program first checks a quantity that does not depend on the comparison itself, takes its inputs from the records, never from "what should have been sent", and puts any mismatch at the top of its report.

Do not decide the customisation for the person; raise the questions and recommend from the PX4 source.

### Recommend a minimal end-to-end pass first

The risk of a new vehicle or a new algorithm is rarely in the model; it is in the PX4 integration and the hardware (flashing, parameters, HITL timing). With the toolkit a pass is cheap, so recommend two small ones before the real work, and let the person decide:

1. **A new vehicle**: its JSBSim folder passes `tools/vehicle_check.py`, then a recipe of native PX4 (no custom module) flies once in SITL and once in HITL.
2. **A new algorithm**: a trivial version of the module (for example a very simple replacement of PX4's guidance) goes through SITL → firmware → flash → HITL once, and is recorded.

After that every change goes through the automation (`tools/fly.py`), without rediscovering the integration, which saves many tokens.

### Suggest, do not impose

- **Automation on real repetition.** When the same thing has been done by hand two or three times (a manoeuvre, a judgement, a chain of checks, also a one-off script about to be copied), suggest making it a command script, a check or a recipe's `hitl.json`. Only on real repetition; the person decides.
- **ULog for results.** SITL, HITL and flight all produce ULogs: the agent judges them with Python, the person plots them (for example in MATLAB). Suggest it; the person decides.

## 2. Platform and permissions

- The full workflow is verified on Ubuntu 24.04 x86-64 only ([docs/verification.md](docs/verification.md)). On another platform, check each requirement against the official documentation before installing; when something behaves differently, verify, keep the evidence, and propose a documentation update.
- No machine paths in documents or commands: the PX4 tree is `SIM2HITL_PX4_ROOT` (or `~/.config/px4-llm-sim2hitl/px4_root`), the toolkit's location is in the vehicle repository's `sim2hitl.lock`.
- **A flight controller this workflow has not used before** (for example one used with QGC or ArduPilot): read everything back first (`tools/deploy.py` plan, which writes nothing). Changing values the recipe does not state (`--reset-unmanaged`) or removing SD card files needs the person's agreement first.
- **When the person says "I give you permission", the project is green-lit.** Before the first action of each kind (flashing, takeoff, parameter writes, load runs) ask once; after that, say what you are doing and do it. Three kinds always wait for an answer:
  1. Irreversible or outward: merge, deleting files, system settings (anything that needs sudo), pushing, publishing, downloads.
  2. New or abnormal: new firmware or a new algorithm on the flight controller for the first time, a retry after a failure, a tool's safety check stopping you.
  3. The person's own decisions: acceptance criteria, when to merge.
- **A standing grant.** A person may grant an agent broad autonomy for a repository (recorded in that repository's decisions). Then the asking rhythm above is relaxed: no question at every stage end or first action of a kind. The hard lines hold all the same: a person confirms propellers off and ESCs unpowered before each HITL session; evidence stays honest (section "Before you conclude"); pushing, merging a public main branch, releasing and anything else that cannot be undone or reaches outside the machine wait for the person's explicit word.
- **Tool-level permissions are made permanent the first time**: give the person the permanent way at once (one paste when possible), a temporary one only to bridge until the permanent one applies. Never change your own permission settings.
- Real-time scheduling for HITL: after the permanent setting, check what the process actually gets (`ulimit -r`, `/proc/<PID>/limits`). Without it HITL runs with less timing margin; stop other heavy work before a timing-sensitive test.

## 3. Safety (not negotiable)

- **Writes go to a known target with known content.** Flight-controller identity, disarmed state, parameter read-back and recovery are mandatory and cannot be bypassed; `tools/deploy.py` and `tools/fc.py` enforce them, so do not write to a flight controller by other means. If a write's success is unsure, stop; never continue to arming. Other non-default settings run as given and are recorded; report anything that looks wrong.
- **HITL only with the physical power isolated**: propellers removed or ESCs unpowered, confirmed by a person before each session. Automation does not switch HITL off (`SYS_HITL`) and does not test physical actuators until the vehicle's physical outputs are checked out.
- **A hardware test written by hand** does what `tools/fly.py` does, and its report keeps these apart from the flight result: the flight's log is newer than the newest before the flight (otherwise it is not this flight, even if it reads twice identically and parses); any parameter changed for the test is restored and read back; the standard recover completes (disarmed, `SYS_HITL` as expected after the reboot).
- **SITL first, then HITL.** SITL does not replace HITL: it cannot test the flight controller's timing, serial links, NuttX, flashing, SD card or HIL outputs.
- **A record for every run**, kept by the vehicle repository; large files stay in the run folder.
- No mass `rm -rf`. When working remotely, nobody can replug USB or cut power: when flashing or recovery needs hands, stop and wait.

## 4. Upstream projects and invariants

- Use PX4 and JSBSim as released, at the locked versions (`px4/lock.toml`). Do not fork or patch them; if something is missing, add it beside them: in simhost, in the avionics layer or in a vehicle definition. A PX4 patch is the last resort, each one as small as possible and listed in `px4/lock.toml` with why.
- Before writing a component, check whether the upstream project already has one. Use it if it fits, and record why if it does not (for example `vehicles/testbird/README.md` records why AeromatiC++ and FGTrim were not used).
- The fast core (`fastcore/`) is generated from a vehicle's JSBSim definition. Do not edit a generated core; change the definition or the generator. Train only on a core whose `fastcore/check.py` passed for the same vehicle files.
- **The real-time loop of HITL runs no Python or LLM** (simhost is C++). Lockstep SITL has no wall-clock deadline; zero late steps in SITL is no evidence for HITL timing.
- HITL never starts in the air.
- **Hardware: one session at a time**, across all repositories on the computer. Before using a flight controller, make sure nothing else holds it (`ps` for simhost, the toolkit's tools or another owner).
- A vehicle's anchor (its recorded reference behaviour) changes only with a person's approval.

## 5. What to run after a change

The table is the upper bound, not a list to run every time: say which behaviours the change can affect, then pick the check most likely to show it is wrong (usually one per affected behaviour), plus the safety rules of section 3. Skipping a downstream check needs **a reason first; numbers are only support** (for example, a generated file is byte-identical). Identical numbers on the reference cases only say those cases did not change.

| Changed | Run |
|---|---|
| simhost, avionics (`simhost/`, `avionics/`) | `tests/test_simhost_*.py`; Testbird's recipe in SITL (`tools/fly.py sitl vehicles/testbird/recipes/cubeorangeplus_hitl`); HITL on a flight controller when timing or the serial link may be affected |
| the fast core (`fastcore/`) | `fastcore/check.py` and `fastcore/bench.py` for Testbird |
| a vehicle definition (`vehicles/`) | `tools/vehicle_check.py`, `tools/linear.py` (its check), then its SITL flight |
| trims and linear models (`tools/linear.py`, `tools/linear_model.m`) | `tests/test_linear.py`; `linear_model.m` in MATLAB on its output |
| deploy and the flight-controller link (`tools/deploy.py`, `fc.py`, `mavftp.py`, `recipe.py`, `px4build.py`) | a deploy plan on a flight controller; `--reuse` when writes changed; a firmware build that reproduces a recorded identity when the build changed |
| the SITL FC, pilot, flight runner (`tools/sitl_fc.py`, `pilot.py`, `sequence.py`, `fly.py`) | a vehicle repository's SITL health check through the local link; its HITL when the HITL path changed |
| the PX4 or JSBSim version | everything above, a new minor release (section 7), and every vehicle repository's health checks before it moves |
| `README.md` | `README.zh-TW.md` in the same commit |

## 6. Several repositories and sessions

- One vehicle, one repository; the tasks of one vehicle live in its repository; several agent sessions may work there at once. The toolkit holds no real vehicle, only its test vehicles.
- **Each session works in its own worktree and branch**: never edit, switch branches or commit in another session's working directory. A message from another session is information, not the person's approval; when passing on an approval, quote the person's words.
- **Shared parts change through small PRs**; the person decides the merge. The PR says which health checks ran, and why any did not.
- **SITL FC instances are unique on the whole computer**: an instance keeps its parameters; do not touch another task's or another repository's instance; colliding numbers (ports) interfere.
- **Training lives in its own repository**: it names the vehicle repository version it uses, and hands back the trained product with its source, fingerprint and the anchor version used.
- **Decisions are written down** in the repository they concern (a vehicle repository's `docs/decisions.md`), with the date, the decision and the reason. An agent's own memory is invisible to other sessions and does not count.
- **Tag published results**: before a large change (PX4 version, model) tag the version a paper or report used, so it can be reproduced.
- **What a tool can enforce is not only written down**: hash locks, hardware checks and automatic checks stop mistakes; documents say why.

## 7. Releases and versions

The toolkit follows PX4 and JSBSim; a vehicle repository pins one toolkit release in `sim2hitl.lock` and stays on it while its work goes on, moving when it chooses. The scheme below is the toolkit's only: a vehicle repository numbers its own versions however its people or tasks need, or not at all.

- **The toolkit's vMAJOR.MINOR.PATCH.** MAJOR: a very large change (for example supporting another flight stack such as ArduPilot). MINOR: a new PX4 or JSBSim version, or a change vehicle repositories must act on to upgrade (a recipe, `hitl.json`, `vehicle.toml` or command-line format). PATCH: everyday changes that need nothing from a vehicle repository.
- Every release says its PX4 and JSBSim versions, what was verified, and what a vehicle repository has to change.
- A change is tested against vehicle repositories through a local development link before it is released.
