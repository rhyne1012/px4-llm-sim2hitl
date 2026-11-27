# Verification

What has been run, on what, with what result. A row means only what it says: an unlisted combination is not verified.

| Date | What | Versions | Result | Evidence |
|---|---|---|---|---|
| 2026-11-27 | Testbird checks: rest on the ground, static thrust, level flight 12–23 m/s (`tools/vehicle_check.py`) | JSBSim 1.3.3 (Python module), Ubuntu 24.04 x86-64 | PASS: steady at every speed, 17 m/s matches the hand calculation (`vehicles/testbird/README.md`) | the table in `vehicles/testbird/README.md` |
| 2026-11-27 | simhost against a fake PX4 (`tests/test_simhost_fake_px4.py`): lockstep, sensor periods, sensors at rest, throttle path | simhost built against JSBSim 1.3.3, MAVLink from PX4 v1.18.0 | PASS: HIL_SENSOR every 4 ms, HIL_GPS every 0.1 s; at rest acc (−0.01, −0.02, −9.79) m/s², 1013.2 hPa, field 0.449 G; full throttle 17.5 m/s after 10 s | test output |
| 2026-11-27 | Testbird SITL flight with stock PX4 (`tools/sitl_flight.py`): parameters set and read back, runway takeoff, 60 s loiter | PX4 v1.18.0 `px4_sitl_default` unmodified, airframe 1033, instance 9; simhost lockstep | PASS: 11/11 parameters read back; lift-off after 3.7 s and 18.8 m at 14.8 m/s; loiter at 30 m (29.2–34.6), airspeed mean 16.6 m/s (trim 17), throttle 0.625 (offline trim 0.635); 0 lockstep timeouts; 414 s simulated in 9 s | `~/.cache/px4-llm-sim2hitl/v2/runs/20261127-1407_sitl_testbird/` (summary.json, simhost.csv, ULog) on the 3090 |
| 2026-11-27 | Testbird HITL on a Cube Orange+ (`tools/hitl_flight.py`): identity, parameters written, stored and read back after reboot, runway takeoff, 60 s loiter, force-disarm, parameters restored | PX4 v1.18.0 + `px4/patches/cubeorangeplus_hil_variant.patch` (pwm_out_sim), no external modules, 97.7 % flash; airframe 2100 with control allocation and HIL outputs set as in 1033; simhost real time over USB at 2 Mbaud, no real-time priority | PASS: 38/38 parameters read back; lift-off at 17.6 s simulated; loiter at 30.5 m (29.9–35.5), airspeed mean 16.5 m/s, throttle 0.61; 21,000 steps over 84 s with 0 late and max lateness 1.37 ms; ULog (9.0 MB, read twice identical) shows takeoff → loiter, no failsafe; 27 parameters restored to their pre-flash values, read back after reboot | `~/.cache/px4-llm-sim2hitl/v2/runs/20261127-1440_hitl_testbird/`, `.../20261127-1432_flash_cube_testbird/` on the 3090 |

Failed runs kept as evidence (same day, `~/.cache/px4-llm-sim2hitl/v2/runs/`):

- `1434_hitl_testbird`: after the reboot the Cube came back as `/dev/ttyACM1`. The scripts now take the `/dev/serial/by-id/` path.
- `1435_hitl_testbird`: half of the parameters did not survive the reboot. They had been sent without waiting for each echo, and the reboot came before PX4 stored them. Each parameter is now confirmed, stored (`MAV_CMD_PREFLIGHT_STORAGE`), and only then is the board rebooted.
- `1436_hitl_testbird`: the flight passed, but a failsafe fired 10 s after the takeoff (ULog: `global_position_invalid` stayed set for the first 14 s). PX4 accepted arming before GPS was fused (`COM_ARM_WO_GPS 1`), and the switch to loiter then needed a global position. The scripts now arm only after an absolute horizontal position and a home position.

Known differences between the HITL and SITL rows: the Cube keeps 46 non-default parameters from SkySurfer recipes (fixed-wing gains, `FW_PSP_OFF`, geofence, EKF gates), so its roll in the loiter reached 43.6° against 34.7° in SITL. PX4 also commits in-flight accelerometer offsets at disarm, in HITL too; the restore puts them back.
