#!/usr/bin/env python3
"""Download a flight-controller log (ULog) over MAVLink's log protocol.

    <python with pymavlink> tools/fc_log.py --serial /dev/serial/by-id/<the FC> --out <file.ulg> [--id N]

Without --id the newest log is taken. Missing chunks are requested again until the file is complete; the download is
then read a second time and compared, so a corrupt transfer is not mistaken for a good one.
"""
import argparse
import hashlib
import sys
import time

from pymavlink import mavutil

CHUNK = 90


def log_list(m):
    m.mav.log_request_list_send(m.target_system, m.target_component, 0, 0xFFFF)
    logs, end = {}, time.monotonic() + 5
    while time.monotonic() < end:
        e = m.recv_match(type='LOG_ENTRY', blocking=True, timeout=1)
        if e is None:
            continue
        logs[e.id] = {'id': e.id, 'size': e.size, 'time_utc': e.time_utc}
        if e.num_logs and len(logs) >= e.num_logs:
            break
    return logs


def fetch(m, log_id, size):
    data = bytearray(size)
    have = bytearray(-(-size // CHUNK))
    start = time.monotonic()
    while not all(have) and time.monotonic() - start < 600:
        first = have.index(0)
        last = first
        while last + 1 < len(have) and not have[last + 1]:
            last += 1
        m.mav.log_request_data_send(m.target_system, m.target_component, log_id, first * CHUNK, (last - first + 1) * CHUNK)
        idle = time.monotonic()
        while time.monotonic() - idle < 1.0:
            d = m.recv_match(type='LOG_DATA', blocking=True, timeout=0.2)
            if d is None or d.id != log_id:
                continue
            idle = time.monotonic()
            k = d.ofs // CHUNK
            if k < len(have) and not have[k]:
                data[d.ofs:d.ofs + d.count] = bytes(d.data[:d.count])
                have[k] = 1
            if d.ofs // CHUNK >= last:
                break
    m.mav.log_request_end_send(m.target_system, m.target_component)
    if not all(have):
        raise RuntimeError(f'log {log_id}: {have.count(0)} chunks missing after 600 s')
    return bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--serial', required=True)
    p.add_argument('--baud', type=int, default=2000000)
    p.add_argument('--out', required=True)
    p.add_argument('--id', type=int)
    a = p.parse_args()
    m = mavutil.mavlink_connection(a.serial, baud=a.baud, source_system=254, source_component=190)
    if not m.wait_heartbeat(timeout=10):
        sys.exit('no heartbeat')
    logs = log_list(m)
    if not logs:
        sys.exit('no logs listed')
    entry = logs[a.id] if a.id is not None else logs[max(logs)]
    t0 = time.monotonic()
    first = fetch(m, entry['id'], entry['size'])
    second = fetch(m, entry['id'], entry['size'])
    same = first == second
    with open(a.out, 'wb') as f:
        f.write(first)
    print({'id': entry['id'], 'size': entry['size'], 'time_utc': entry['time_utc'], 'logs_on_fc': len(logs),
           'sha256': hashlib.sha256(first).hexdigest(), 'read_twice_identical': same, 'seconds': round(time.monotonic() - t0, 1)})
    sys.exit(0 if same else 1)


if __name__ == '__main__':
    main()
