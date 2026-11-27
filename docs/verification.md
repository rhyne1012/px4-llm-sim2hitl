# Verification

What has been run, on what, with what result. A row means only what it says: an unlisted combination is not verified.

| Date | What | Versions | Result | Evidence |
|---|---|---|---|---|
| 2026-11-27 | Testbird checks: rest on the ground, static thrust, level flight 12–23 m/s (`tools/vehicle_check.py`) | JSBSim 1.3.3 (Python module), Ubuntu 24.04 x86-64 | PASS: steady at every speed, 17 m/s matches the hand calculation (`vehicles/testbird/README.md`) | the table in `vehicles/testbird/README.md` |
| 2026-11-27 | simhost against a fake PX4 (`tests/test_simhost_fake_px4.py`): lockstep, sensor periods, sensors at rest, throttle path | simhost built against JSBSim 1.3.3, MAVLink from PX4 v1.18.0 | PASS: HIL_SENSOR every 4 ms, HIL_GPS every 0.1 s; at rest acc (−0.01, −0.02, −9.79) m/s², 1013.2 hPa, field 0.449 G; full throttle 17.5 m/s after 10 s | test output |
| 2026-11-27 | Testbird SITL flight with stock PX4 (`tools/sitl_flight.py`): parameters set and read back, runway takeoff, 60 s loiter | PX4 v1.18.0 `px4_sitl_default` unmodified, airframe 1033, instance 9; simhost lockstep | PASS: 11/11 parameters read back; lift-off after 3.7 s and 18.8 m at 14.8 m/s; loiter at 30 m (29.2–34.6), airspeed mean 16.6 m/s (trim 17), throttle 0.625 (offline trim 0.635); 0 lockstep timeouts; 414 s simulated in 9 s | `~/.cache/px4-llm-sim2hitl/v2/runs/20261127-1407_sitl_testbird/` (summary.json, simhost.csv, ULog) on the 3090 |
