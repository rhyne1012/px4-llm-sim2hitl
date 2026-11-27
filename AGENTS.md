# Rules for AI agents

Status: v2 draft. These rules apply to any agent working in this repository. The design is in [docs/architecture.md](docs/architecture.md).

## Language

- Write everything in this repository in English: code, comments, commit messages, documentation. `README.zh-TW.md` is a translation of `README.md`, which is authoritative.
- Talk to people in their own language.

## Upstream projects

- Use PX4 and JSBSim as released, at the locked versions. Do not fork or patch them. If something is missing, add it beside them: in the simulation host, in the avionics layer or in a vehicle definition.
- The fast core (`fastcore/`) is generated from a vehicle's JSBSim definition. Do not edit a generated core; change the definition or the generator. Train only on a core whose `fastcore/check.py` passed for the same vehicle files.
- Before writing a component, check whether the upstream project already has one. Use it if it fits, and record why if it does not; for example, `vehicles/testbird/README.md` records why AeromatiC++ and FGTrim were not used.

## Evidence

- Every conclusion states its basis (which run, which record) and its scope (versions, vehicle, recipe, flight controller, mode). With less evidence, make a smaller claim.
- When a test fails, keep the failing run's evidence. Store the fixed run separately; do not overwrite the failure.
- Agreement between SITL and HITL does not show that the model matches the real vehicle.

## People decide

- People decide goals, the choice between approaches, success criteria, and anything that cannot be undone or that reaches outside this machine: pushing, publishing, merging, flashing a flight controller, downloads.
- A vehicle's anchor changes only with a person's approval.
- Hardware tests need the propellers removed and the ESCs unpowered, confirmed by a person before each session.

## Safety checks

Flight-controller identity, disarmed state, parameter read-back and recovery are mandatory and cannot be bypassed. Other non-default settings run as given and are recorded; report anything that looks wrong.
