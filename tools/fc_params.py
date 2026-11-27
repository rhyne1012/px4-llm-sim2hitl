#!/usr/bin/env python3
"""Save a flight controller's parameters, or put them back as a saved file had them.

    <python with pymavlink> tools/fc_params.py save    --serial /dev/serial/by-id/<the FC> --file before.params
    <python with pymavlink> tools/fc_params.py restore --serial /dev/serial/by-id/<the FC> --file before.params

restore writes only the parameters whose value differs from the file (each one confirmed by the flight controller),
stores them, reboots, and reads every one back. It reports what it changed. Parameters the file does not have are left
alone. Note that PX4 commits in-flight sensor bias estimates (CAL_ACC0_*, ...) at disarm, also in HITL, so a HITL run
changes calibration parameters that a restore puts back.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from pymavlink import mavutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitl_flight import decode_param, encode_param  # noqa: E402


def connect(port, baud):
    for _ in range(60):
        try:
            m = mavutil.mavlink_connection(port, baud=baud, source_system=254, source_component=190)
            if m.wait_heartbeat(timeout=5):
                return m
            m.close()
        except Exception:  # noqa: BLE001  (port not back yet after a reboot)
            pass
        time.sleep(1)
    sys.exit(f'no heartbeat on {port}')


def read_all(m):
    m.mav.param_request_list_send(m.target_system, m.target_component)
    params, last = {}, time.monotonic()
    while time.monotonic() - last < 3.0:
        p = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
        if p is None:
            continue
        last = time.monotonic()
        params[p.param_id] = (decode_param(p.param_value, p.param_type), p.param_type)
        if p.param_count and len(params) >= p.param_count:
            break
    return params


def load(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if '\t' in line:
            k, v = line.split('\t')
            out[k] = float(v)
    return out


def same(a, b):
    return a is not None and b is not None and abs(a - b) <= 1e-6 * max(1.0, abs(b))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['save', 'restore'])
    p.add_argument('--serial', required=True)
    p.add_argument('--baud', type=int, default=2000000)
    p.add_argument('--file', required=True)
    a = p.parse_args()
    m = connect(a.serial, a.baud)
    hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
    if hb is None or hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        sys.exit('flight controller armed or silent; refusing')
    now = read_all(m)
    if a.action == 'save':
        with open(a.file, 'w') as f:
            for k in sorted(now):
                f.write(f'{k}\t{now[k][0]:.9g}\n')
        print(json.dumps({'saved': len(now), 'file': a.file}))
        return
    want = load(a.file)
    todo = {k: v for k, v in want.items() if k in now and not same(now[k][0], v) and not k.startswith('_')}
    changed = {}
    for k, v in todo.items():
        ptype = now[k][1]
        echo = None
        for _ in range(5):
            m.mav.param_set_send(m.target_system, m.target_component, k.encode(), encode_param(v, ptype), ptype)
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                pv = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.3)
                if pv is not None and pv.param_id == k:
                    echo = decode_param(pv.param_value, pv.param_type)
                    break
            if same(echo, v):
                break
        changed[k] = {'from': now[k][0], 'to': v, 'echo': echo}
    m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE, 0, 1, 0, 0, 0, 0, 0, 0)
    m.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
    time.sleep(3)
    m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0)
    m.close()
    time.sleep(5)
    m = connect(a.serial, a.baud)
    after = read_all(m)
    still = {k: (want[k], after.get(k, (None,))[0]) for k in todo if not same(after.get(k, (None,))[0], want[k])}
    print(json.dumps({'differed': len(todo), 'changed': changed, 'after_reboot_mismatch': still}, indent=1))
    sys.exit(1 if still else 0)


if __name__ == '__main__':
    main()
