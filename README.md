# px4-llm-sim2hitl

An integration layer between PX4 and JSBSim for agent-driven flight-control development, from SITL to hardware-in-the-loop (HITL), for any vehicle type.

**English** | [繁體中文](README.zh-TW.md) (translation; this English version is authoritative)

> Status: v2 draft, under development. v1 (Simulink → C → HITL, example aircraft SkySurfer) is archived as tag `v1-final` and branch `legacy-v1`.

## Overview

This project sits between [PX4](https://px4.io) (flight control) and [JSBSim](https://github.com/JSBSim-Team/jsbsim) (flight dynamics). Both are used unmodified, at locked versions. This project implements only what lies between them:

- real-time HITL simulation
- a deployment pipeline
- a consistent verification method across SITL, HITL and flight
- development rules for AI agents

Each vehicle lives in its own repository and pins a version of this project. This project contains no real vehicles, only test vehicles.

## Design principles

- **Build on mature projects.** Do not reimplement what PX4 or JSBSim already provide. Use their existing modules where they fit, and extend only where they fall short.
- **The integration layer fills the gaps only.** It is responsible for HITL timing and hardware safety, the deployment pipeline, consistent SITL/HITL verification, and the agent rules.
- **Keep vehicles and tools apart.** Vehicle definitions, tasks and flight records belong to vehicle repositories. This project holds general tools and test vehicles.
- **A handover, not an automation suite.** Every new agent session is a new team member on their first day. The documentation states:
  - how the system works
  - known problems
  - what has been verified
  - which decisions belong to people

  With this, an agent that meets an anomaly can locate its cause instead of bypassing a check. Tools capture understanding that already exists: a procedure becomes a command only after it has been done two or three times.
- **Conclusions match their evidence.** Every conclusion states its basis (which test, which record) and its scope (versions, recipe, flight controller, mode). Less evidence means a narrower claim. Agreement between SITL and HITL does not show that the model matches the real vehicle.
- **One measuring stick.** SITL, HITL and flight use the same scenarios, the same checks and the same record format (ULog). Differences between levels are information to investigate.
- **One source.** Each piece of information lives in one place. Nothing is designed ahead for needs that have not appeared.
- **Environments are discovered; acceptance criteria are fixed.** Paths, compilers and PX4 source trees are detected and can be overridden. Version locks, tolerances and timing limits do not change with the environment.
- **Safety checks cannot be bypassed.** Flight-controller identity, disarmed state, parameter read-back and recovery are mandatory. Other non-default settings run as given and are recorded. The agent reports anomalies, and people decide.
- **People set direction; agents handle the technical work.** Goals, choices between approaches and success criteria are decided by people. Agents research and implement, and report in the user's language.

## Architecture

```
  PX4 (flight control)     JSBSim (flight dynamics)     upstream: locked versions, unmodified
            \                 /
        px4-llm-sim2hitl (integration layer)           this repository
                    |  pinned version
   vehicle repositories: SkySurfer, SkyTalon, ...      vehicle definition, tasks, records
```

## Supported vehicles

Any vehicle JSBSim can describe is in scope, for example fixed-wing aircraft, multirotors, VTOL aircraft and helicopters. Every interface is verified with two test vehicles, one fixed-wing and one quadrotor, so that no interface assumes a particular vehicle type. Actual support is what the verification matrix shows: an unverified combination is not supported.

## Features

- **Simulation host.** JSBSim plus an avionics model (sensors, servo signal chain), talking to PX4 through its standard HIL MAVLink messages. Connected to PX4 SITL it is SITL; connected to a flight controller it is HITL. It is the same program in both cases.
- **Deployment pipeline.** Build → flash → identity check → parameters → boot file → HITL → flight-controller log, in one command.
- **Test cases.** One format for scenarios, checks and records, used at the algorithm level, in SITL, in HITL and in flight.
- **Anchor.** The recorded reference behaviour of a vehicle, locked; changing it requires a person's approval.
- **Machine resources.** When several vehicle repositories share one computer, flight controllers, SITL instances and PX4 source trees are coordinated between them.
- **Vehicle generator.** Creates a new vehicle repository.

## Development flow

1. **Requirements and specification.** Define the goal and the success criteria. The agent first reads the locked PX4 source, presents the feasible integration approaches for a person to choose, and recommends a minimal end-to-end pass first.
2. **SITL.** Iterate on the computer.
3. **HITL.** Verify on a real flight controller through the deployment pipeline.
4. **Flight and feedback** (planned). Flight data corrects the vehicle model; the anchor is updated after a person approves.

## Getting started

Give the URL of this repository to an AI agent (for example Claude Code or Codex) and state your goal.

- **New vehicle:** create a vehicle repository with the vehicle generator, then take the test vehicle through SITL → HITL first.
- **Existing vehicle:** work in that vehicle's repository; this project does not need to be modified directly.

## Language

- This README is in English, and it is the authoritative version. [README.zh-TW.md](README.zh-TW.md) is a translation; where the two disagree, this version wins.
- All other documentation (`AGENTS.md`, folder READMEs, code comments, commit messages) is in English only, in a single version.
- Agents talk to people in each person's own language, using the terms in the glossary (planned).

## License

BSD 3-Clause, see [LICENSE](LICENSE). PX4 (BSD 3-Clause) and JSBSim (LGPL-2.1) are used unmodified under their own licenses; JSBSim is built from its locked source release.
