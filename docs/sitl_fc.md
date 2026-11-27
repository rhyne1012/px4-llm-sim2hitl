# SITL FC

A SITL FC is PX4 on the computer standing in for the flight controller that runs a recipe: the same PX4 version, the recipe's external modules, its parameters, boot file and logger topics, and the flight controller's HITL startup instead of PX4's posix one. simhost drives it with `--sitl-udp` and `--mavlink-udp` (see [architecture.md](architecture.md), "Transports"). `tools/sitl_fc.py` builds and runs it; it needs only the Python standard library.

## Build

```sh
PATH="<PX4 Python environment>/bin:$PATH" python3 tools/sitl_fc.py build --recipe <vehicle repo>/deploy/<recipe> \
    [--patch <file in the vehicle repo>[:<repo in the PX4 tree>]]... [--committer "NAME <EMAIL>"]
```

- **Source.** PX4 at the commit of `px4/lock.toml`, target `px4_sitl_default` (lockstep), with the modules listed in the recipe's `firmware/firmware.json` (`recipe.modules`), taken from `<vehicle repo>/modules/src/<name>`.
- **Patches.** Only SITL patches: `--patch`, or else the vehicle repository's `sim2hitl.lock` `"sitl_build": {"patches": ["FILE[:REPO]", ...]}`, committed with `git am` in that order. The recipe's own patches are not applied: they change board files and NuttX, which the computer build does not use. The committer (`--committer`, else `sim2hitl.lock` `firmware_build.committer` as for the firmware, else `sim2hitl build <build@sim2hitl.invalid>`) is part of each patch commit, so it sets the git hash the SITL FC reports.
- **Build tree.** A tree of this tool's own (`--build-tree`, default `~/px4/PX4-Autopilot-<tag>-build-v2sitl`), copied once from `--copy-from` without its `build/` folder, and reset to the lock commit with clean submodules before every build. No other PX4 tree is written. One build runs at a time.
- **Record.** `~/.cache/px4-llm-sim2hitl/v2/sitl_fc/builds/<recipe>/build.json`: the recipe and vehicle repository, the PX4 lock and the resulting git hash, the patches (SHA-256 and commit), every module file's SHA-256, the binary's SHA-256 and the parameter list (copied next to it). `start` refuses a build whose inputs no longer match.

## Run

```sh
python3 tools/sitl_fc.py start --recipe <vehicle repo>/deploy/<recipe> --instance N [--fresh]
python3 tools/sitl_fc.py status --instance N
python3 tools/sitl_fc.py restart --instance N      # a reboot
python3 tools/sitl_fc.py stop --instance N
```

- **Instance folder** `~/.cache/px4-llm-sim2hitl/v2/sitl_fc/instances/N`. It keeps parameters, dataman and logs (`log/`) across restarts, as a flight controller keeps them across reboots; a recipe started in an instance that ran another one inherits its stored values. `--fresh` starts from an empty folder: a new flight controller.
- **Ports**, UDP on 127.0.0.1: simulator PX4 24740+N ↔ simhost 4560+N; MAVLink PX4 24640+N ↔ simhost 24540+N. simhost: `--sitl-udp 4560+N:24740+N --mavlink-udp 24540+N:24640+N --lockstep` (printed by `start`). The PX4 instance number is N as well (`/tmp/px4_lock-N`): `start` refuses an N that another PX4 on the computer uses.
- **Supervisor.** Runs PX4 and starts it again whenever it exits, until `stop`. PX4 on the computer denies MAVLink's reboot and shutdown commands (PX4 builds them only for boards that can reset), so a reboot is asked for from outside: `restart`, or the file `restart` in the instance folder, which a MAVLink user can create after it has answered a reboot command as the flight controller would. It does not start a binary that was rebuilt since `start`.
- **Lockstep.** `simulator_mavlink` holds the startup script until simhost's first `HIL_SENSOR`, so the boot (MAVLink, boot file, logger) completes only once simhost runs. Each simhost run starts its clock at zero: restart PX4 (`restart`) before the next one.
- **Derived recipe** `instances/N/recipe/`: the recipe as the SITL FC runs it, readable by `tools/recipe.py`. `HIL_ACT_FUNCn` and `HIL_ACT_REV` become `PWM_MAIN_FUNCn` and `PWM_MAIN_REV` (the SITL outputs) and win over the recipe's own `PWM_MAIN_*`; parameters the computer build lacks are left out and listed in `params.json` (`sitl.left_out`); the identity is the SITL build's (board version 1, no NuttX).

## Startup script

`instances/N/rcS` is written at every `start`, not taken from PX4's posix rcS, which sets SITL defaults that the flight controller does not have. In this order:

1. Stored parameters are imported. The recipe's `airframe`, `boot` and `verify_only` values become defaults (`param set-default`), as the flight controller's airframe and board scripts set them; so do the simulated sensors' device ids and the physical flight controller's own values (below), and `SYS_HITL 1`. The recipe's `set` values are written (`param set`) at every boot, so a fresh instance has the deployed parameters without a deploy step; a `set` value changed over MAVLink returns to the recipe's value at the next boot. `MAV_SYS_ID` is 1.
2. The flight controller's HITL apps: `simulator_mavlink` (UDP) in place of the HIL messages on the flight controller's MAVLink link, `system_power_simulator` for the board's power reading, `sensors`, `commander -h`, EKF2, `pwm_out_sim -m sim`, `rc.vehicle_setup` with `VEHICLE_TYPE` from the airframe's `rc.<type>_defaults` (or `--vehicle-type`), `navigator`.
3. MAVLink in mode `minimal` with a few streams (`--stream NAME=RATE` adds one): in lockstep the rates count simulated seconds, so the full set would grow with the speed-up.
4. The boot file (`sd/etc/extras.txt` of the recipe, at `fs/microsd/etc/extras.txt`), then the logger, then `mavlink boot_complete`, as in the flight controller's rcS. The recipe's logger topic list goes to `etc/logging/logger_topics.txt` of the instance: `etc` is a folder of links to the build's ROMFS, so the build is never written.

**The physical flight controller's own values.** A recipe does not state its `fc_owned` parameters (RC calibration and mapping, for example), but a SITL FC needs some of them to stand for a particular flight controller. The vehicle repository provides them in `sitl/sitl_fc_owned.json` (`{"values": {NAME: VALUE}}`; `--fc-owned-values` for another file). Every name must match the recipe's `fc_owned` patterns.

## Not covered

A SITL FC does not test the flight controller's timing, serial links, NuttX, flashing, SD card, the HIL output mapping or the HIL sensor input path. A change that passes in SITL still needs HITL on the flight controller.
