# Deploy recipes

A deploy recipe is everything one flight controller runs: firmware, parameters, the SD card's boot file and logger topics, and what a test flight flies and how it is judged. Recipes live in a vehicle repository; the toolkit builds them (`tools/px4build.py`), puts them on a flight controller (`tools/deploy.py`) or a SITL FC (`tools/sitl_fc.py`, [sitl_fc.md](sitl_fc.md)), and flies them (`tools/fly.py`).

## The vehicle repository

```
<repository>/
  sim2hitl.lock                 the toolkit version it uses, and the keys below
  modules/src/<module>/         PX4 external modules (CMakeLists.txt, sources)
  <patches>                     PX4 patches, at paths a recipe names
  <commands>/<script>.py        command scripts for the pilot (docs/pilot.md)
  <recipe>/                     any folder holding a recipe
```

`sim2hitl.lock` (JSON) names the toolkit (`path`, `commit`) and can hold:

| Key | Meaning |
|---|---|
| `firmware_build.committer` | `{"name", "email"}`: the committer of the recipe patches. `git am` commits each patch with this committer and the author's date, so the same patches give the same commits and the flight controller reports the same PX4 and NuttX hashes. Changing it changes the hash every recipe with a patch records. Default `sim2hitl build <build@sim2hitl.invalid>`. |
| `commands` | The folder of command scripts, for a `hitl.json` `after` given as a name. Default `commands`. |

## The recipe folder

```
<recipe>/firmware/firmware.json     build recipe, outputs, identity, last flash
<recipe>/firmware/<target>.px4      the built image
<recipe>/firmware/parameters.json.xz  the firmware's parameter list (PX4 build output, unmodified)
<recipe>/params.json                parameter values and the flight controller's own parameters
<recipe>/sd/etc/extras.txt          optional boot file
<recipe>/sd/etc/logging/logger_topics.txt   optional logger topic list
<recipe>/hitl.json                  optional test flight
```

### firmware.json

```json
{
  "recipe": {"make_target": "cubepilot_cubeorangeplus_hil",
             "patches": [{"file": "px4/patches/<name>.patch", "repo": "."}],
             "modules": ["<module>"]},
  "px4": {"tag": "v1.18.0", "commit": "935addf1d6bec6e955b155494a52e7eb4b750eb3"},
  "outputs": {...}, "embedded": {...}, "build": {...}, "flashed": {...}
}
```

- `recipe`: `make_target` is PX4's; each patch's `file` is a path in the vehicle repository and `repo` a folder of the PX4 tree (`.` for PX4 itself, `platforms/nuttx/NuttX/nuttx` for NuttX); `modules` are folders of `modules/src`. A recipe without `recipe` holds a prebuilt image.
- `px4.commit` must be the commit of the toolkit's `px4/lock.toml`.
- `px4build.py` writes `outputs` (SHA-256 of the image, the binary inside it and the parameter list), `embedded` (what the flight controller will report: board id, `board_version`, PX4 and NuttX commit) and `build` (command, committer, patch commits, the SHA-256 of every module file, toolchain), and clears `flashed`. `deploy.py --flash` writes `flashed`.
- `board_version` is what PX4 reports in AUTOPILOT_VERSION: the USB product id (`CONFIG_CDCACM_PRODUCTID`), which differs from the image's board id on some boards (Cube Orange+: 4184 against 1063).

The image is reproducible from the recipe only as far as the identity: the same PX4 and NuttX hashes and the same parameter list. Its bytes also depend on the build tree's path, because PX4 compiles a few source paths into the binary (`__FILE__` in assertions).

### params.json

```json
{
  "firmware_params": {"file": "firmware/parameters.json.xz", "sha256": "..."},
  "fc_owned": {"patterns": ["^CAL_", "^RC\\d+_", ...], "resolved_names": [...]},
  "airframe":    {"NAME": {"value": 1, "why": "..."}},
  "boot":        {...},
  "verify_only": {...},
  "set":         {...}
}
```

The expected value of every parameter is the firmware's default, overlaid with:

| Section | Who sets it | The toolkit |
|---|---|---|
| `airframe` | PX4's airframe script | checks, never writes |
| `boot` | the board scripts or the boot file | checks, never writes |
| `verify_only` | someone else (a person, a calibration) | checks, never writes |
| `set` | the toolkit | writes, checks |

A HITL recipe states `GPS_1_CONFIG` 0 in `boot`: PX4's `rcS` sets it at every boot when `SYS_HITL` > 0 (it disables the real GPS), so otherwise the final check finds it off its default. `--reset-unmanaged` also writes the airframe values another recipe changed (see below).

A name may be in one section only. Parameters matching `fc_owned.patterns` belong to the physical flight controller (calibration, counters, the operator's RC): they are read but neither compared nor written. `resolved_names` is the list the patterns gave when the recipe was reviewed; a firmware whose names give another list makes the check INCOMPLETE until the list is reviewed again.

The check (`tools/recipe.py`, `Recipe.check`) compares a full readback with these values. Int32 values compare exactly, Float values as float32 bits. Its verdict:

- **PASS**: the flight controller reports the recipe's firmware, every parameter was read, and each has its expected value.
- **FAIL**: a value differs (`wrong_value` for a stated one, `not_default` for any other), or the flight controller or the local files are not the recipe's firmware.
- **INCOMPLETE**: the readback is incomplete or inconsistent, a name is unknown to the firmware, or `fc_owned` resolves to another list.

A `set` value equal to the firmware default is reported as `redundant` (harmless).

PX4 itself writes some parameters that a recipe does not state. EKF2 writes `EKF2_SENS_EN` at every disarm and sets only the GNSS 0 bit for GPS, so the default 8191 becomes 8189 after the first flight (PX4 v1.18 `EKF2::syncSensEnParam`); the check reports exactly that value as `px4_rewritten`, not as a failure (`PX4_REWRITES` in `tools/recipe.py`). An output function change sets that output's PWM limits; `deploy.py` writes `set` values again when PX4 changed them. `--reset-unmanaged` writes any other parameter that differs back to its default.

**Moving a flight controller between recipes or vehicles.** PX4's airframe script sets only defaults, so a parameter an earlier recipe set keeps its value, also one of the new recipe's `airframe` values; and the earlier recipe's `set` values stay where the new one is silent. The deploy reports both and stops; `--reset-unmanaged` writes the unstated ones back to their defaults and the airframe ones to the airframe's values. The readback before the deploy is kept (`params_before.json`; `tools/fc.py params-restore --from` puts it back).

### SD files

The boot file runs at the end of PX4's boot (ROMFS `rcS`, `/fs/microsd/etc/extras.txt`); it is how an external module starts without a change to PX4. The logger reads its topic list at start (`/fs/microsd/etc/logging/logger_topics.txt`); since v1.18 the list is added to the topics of `SDLOG_PROFILE`. Both are checked as their readers take them (`tools/mavftp.py`): nsh runs at most 15 words and 127 bytes per line, the logger reads 78 bytes per line and has 255 topic slots. A recipe without a file means the flight controller must not have one.

### hitl.json

```json
{"after": "pitch_steps", "check": "checks/pitch_steps_check.py", "climb_bank": 30, "flight_timeout": 1500}
```

| Key | Meaning |
|---|---|
| `after` | the command script the pilot runs once the aircraft flies level: a path in the repository ending in `.py`, or a name in the commands folder |
| `check` | a program in the repository, run as `<python> -B <check> <ulog> --out <check.json>`; it writes `{"verdict": "PASS" or ...}` |
| `climb_bank` | degrees: climb in a banked circle, for a script whose area a straight climb-out would leave |
| `flight_timeout` | seconds of the whole flight, 900 by default, plus 300 for the takeoff: wall time in HITL, simulated time in SITL (lockstep runs many times faster than real time) |

A vehicle repository may add its own keys (which model configuration a recipe flies, for example); the toolkit ignores them.

## Building

```sh
PATH=<PX4 Python environment>/bin:$PATH python3 tools/px4build.py <recipe> [--if-needed] [--px4-root <PX4 tree>]
```

The user's PX4 tree (`--px4-root`, `SIM2HITL_PX4_ROOT` or `~/.config/px4-llm-sim2hitl/px4_root`) is only the source of a copy. Builds run in `<tree>-build-sim2hitl` (or `SIM2HITL_PX4_BUILD_TREE`), reset to the recipe's commit with clean submodules before every build; the external modules are linked from the repository into `~/.cache/px4-llm-sim2hitl/v2/firmware/<repository>/<recipe>/ext`. `--if-needed` builds only when the image does not match `firmware.json` or the patches or modules changed since.

## Deploying

```sh
<python with pymavlink> tools/deploy.py <recipe> --link /dev/serial/by-id/<the FC>            # plan: nothing written
<python with pymavlink> tools/deploy.py <recipe> --link ... --reuse [--reset-unmanaged]       # parameters, SD files
<python with pymavlink> tools/deploy.py <recipe> --link ... --flash                           # build if needed, flash, then the same
```

The plan reads the flight controller (identity, every parameter, both SD files) and says what would change. `--reuse` needs proof that the flight controller already runs the recipe's image: the identity it reports is not enough (it names the PX4 and NuttX commits only, so recipes that differ only in their external modules report the same), so the image must be current and the board record of this board (`~/.cache/px4-llm-sim2hitl/v2/boards/<uid>.json`, written by every `--flash`) must name the image's SHA-256; a board flashed by another tool needs one `--flash` first; `--flash` writes it first with PX4's uploader. Then the `set` values that differ are written, each confirmed by the flight controller with the same bytes; the SD files are made to hold the recipe's (written to a temporary file, read back, renamed); one reboot; and the proof: every parameter read and checked again (PASS), both SD files read again. It refuses an armed flight controller, and one whose `SYS_HITL` differs from the recipe's unless `--allow-hitl-change` says a person has made the aircraft safe. Nothing is rolled back on a failure; the report keeps the readback from before (`~/.cache/px4-llm-sim2hitl/v2/deploy/<UTC>_<recipe>/`).

`tools/fc.py` does single operations: `identity`, `params-read`, `sd-list`, `sd-get`, `sd-put`, `sd-rm`, `logs`, `log-get`, `recover`.

## Flying

```sh
<python with pymavlink> tools/fly.py sitl <recipe> --vehicle <vehicle folder> [--config C.toml] --instance N
<python with pymavlink> tools/fly.py hitl <recipe> --vehicle <vehicle folder> [--config C.toml] --link /dev/serial/by-id/<the FC>
```

See the docstring of `tools/fly.py` for the steps. A HITL flight needs the aircraft made safe by a person first: propellers off, ESCs unpowered.
