#!/usr/bin/env python3
"""Judge a Testbird loiter flight (the recipe's command script vehicles/testbird/commands/loiter.py) from its ULog.

    <python with pyulog> vehicles/testbird/checks/loiter_check.py <ulog> --out <check.json>

Limits, set on 2026-11-27 before the first flight with this check, from Testbird's earlier flights (loiter at 30.5 m
within 29.9-35.5 m, airspeed mean 16.5 m/s, trim 17 m/s, stall about 10.1 m/s):
  - PX4 in AUTO_LOITER (vehicle_status nav_state 4) for at least 55 s without a break;
  - in that interval the altitude stays within 15 m of the altitude at its start (vehicle_global_position alt);
  - the calibrated airspeed (airspeed_validated) averages 17 ± 3 m/s and never drops below 10.5 m/s (FW_AIRSPD_STALL);
  - no failsafe (vehicle_status failsafe) from the first arming to the end of the loiter.
Writes {"verdict": PASS | FAIL | INSUFFICIENT_EVIDENCE, "problems", "missing", "info"}; a missing topic or interval is
INSUFFICIENT_EVIDENCE, never PASS. Exit 0 when a result was written.
"""
import argparse
import json

import numpy as np
from pyulog import ULog

LOITER = 4
MIN_LOITER_S = 55.0
ALT_BAND_M = 15.0
TRIM_M_S, TRIM_BAND_M_S = 17.0, 3.0
STALL_M_S = 10.5


def topic(log, name):
    found = [d for d in log.data_list if d.name == name and d.multi_id == 0]
    return found[0].data if found else None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('ulog')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    log = ULog(a.ulog)
    problems, missing, info = [], [], {}
    status = topic(log, 'vehicle_status')
    if status is None:
        missing.append('vehicle_status')
    else:
        t = status['timestamp'] * 1e-6
        nav, armed = status['nav_state'], status['arming_state'] == 2
        loiter = np.flatnonzero(nav == LOITER)
        if not len(loiter):
            problems.append('never in AUTO_LOITER')
        else:
            # the longest unbroken stretch of AUTO_LOITER samples
            breaks = np.flatnonzero(np.diff(loiter) > 1)
            starts, ends = np.r_[loiter[0], loiter[breaks + 1]], np.r_[loiter[breaks], loiter[-1]]
            k = int(np.argmax(t[ends] - t[starts]))
            t0, t1 = float(t[starts[k]]), float(t[ends[k]])
            info['loiter_s'] = round(t1 - t0, 1)
            if t1 - t0 < MIN_LOITER_S:
                problems.append(f'loiter {t1 - t0:.1f} s, less than {MIN_LOITER_S:.0f} s')
            if not armed.any():
                problems.append('never armed')
            else:
                t_arm = float(t[np.flatnonzero(armed)[0]])
                window = (t >= t_arm) & (t <= t1)
                fs = status['failsafe'][window].astype(bool)
                info['failsafe'] = bool(fs.any())
                if fs.any():
                    problems.append(f'failsafe at {float(t[window][np.flatnonzero(fs)[0]] - t_arm):.1f} s after arming')
            gpos = topic(log, 'vehicle_global_position')
            if gpos is None:
                missing.append('vehicle_global_position')
            else:
                tg = gpos['timestamp'] * 1e-6
                alt = np.asarray(gpos['alt'][(tg >= t0) & (tg <= t1)], float)
                if len(alt) < 2 or not np.isfinite(alt).all():
                    missing.append('altitude samples in the loiter')
                else:
                    dev = float(np.max(np.abs(alt - alt[0])))
                    info['altitude_start_min_max_m'] = [round(float(alt[0]), 1), round(float(alt.min()), 1),
                                                        round(float(alt.max()), 1)]
                    if dev > ALT_BAND_M:
                        problems.append(f'altitude left the {ALT_BAND_M:.0f} m band by {dev - ALT_BAND_M:.1f} m')
            aspd = topic(log, 'airspeed_validated')
            if aspd is None:
                missing.append('airspeed_validated')
            else:
                ta = aspd['timestamp'] * 1e-6
                cas = np.asarray(aspd['calibrated_airspeed_m_s'][(ta >= t0) & (ta <= t1)], float)
                cas = cas[np.isfinite(cas)]
                if len(cas) < 2:
                    missing.append('airspeed samples in the loiter')
                else:
                    info['airspeed_mean_min_m_s'] = [round(float(cas.mean()), 2), round(float(cas.min()), 2)]
                    if abs(cas.mean() - TRIM_M_S) > TRIM_BAND_M_S:
                        problems.append(f'mean airspeed {cas.mean():.1f} m/s, outside {TRIM_M_S} ± {TRIM_BAND_M_S}')
                    if cas.min() < STALL_M_S:
                        problems.append(f'airspeed down to {cas.min():.1f} m/s, below {STALL_M_S}')
    verdict = 'FAIL' if problems else 'INSUFFICIENT_EVIDENCE' if missing else 'PASS'
    with open(a.out, 'w') as f:
        json.dump({'verdict': verdict, 'problems': problems, 'missing': missing, 'info': info}, f, indent=2)
    print(verdict, problems, missing, info)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
