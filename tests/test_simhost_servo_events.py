#!/usr/bin/env python3
"""simhost's servo chain, scenario events and setting checks, against a fake PX4 in lockstep.

    <python with pymavlink> tests/test_simhost_servo_events.py build/simhost/simhost vehicles/testbird <scratch dir>

Testbird rests on the ground; the fake PX4 steps the elevator output (channel 7) to 0.5 at t = 1.000 s.
  - Without the servo chain the elevator starts to move in the first physics frame after the step (visible in the
    record row at 1.020 s).
  - With a 50 Hz PWM frame sampled 8 ms into the frame and a 40 ms delay, the command is sampled in frame 1008 and comes
    out in frame 1048: the row at 1.040 s still shows 0, the row at 1.060 s shows the motion.
  - --at 2.0:fcs/elevator-servo/malfunction/fail_zero=1 brings the elevator back to 0 after 2.0 s.
  - --set with a property the vehicle does not have stops simhost before it starts.
"""
import csv
import socket
import subprocess
import sys
import time
from pathlib import Path

from pymavlink.dialects.v20 import common as mav

PORT = 4598


def fly(exe, vehicle, record, extra, seconds=2.6):
    cmd = [exe, '--vehicle', vehicle, '--sitl-port', str(PORT), '--lockstep', '--duration', str(seconds), '--record', record,
           '--actuator', '7:fcs/elevator-cmd-norm:-1', '--servo-channel', '7', *extra]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    try:
        sock = None
        for _ in range(100):
            try:
                sock = socket.create_connection(('127.0.0.1', PORT), timeout=5)
                break
            except OSError:
                time.sleep(0.1)
        assert sock, 'simhost did not listen'
        link = mav.MAVLink(None, srcSystem=1, srcComponent=1)
        while True:
            data = sock.recv(65536)
            if not data:
                break
            for m in link.parse_buffer(data) or []:
                if m.get_type() == 'HIL_SENSOR':
                    controls = [0.0] * 16
                    controls[7] = 0.5 if m.time_usec >= 1_000_000 else 0.0
                    sock.sendall(mav.MAVLink_hil_actuator_controls_message(m.time_usec, controls, mav.MAV_MODE_FLAG_SAFETY_ARMED,
                                                                           1).pack(link))
    finally:
        _, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err
    with open(record) as f:
        rows = {round(float(r['t_s']), 3): abs(float(r['elevator_rad'])) for r in csv.DictReader(f)}
    return rows, err


def main():
    exe, vehicle, scratch = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    scratch.mkdir(parents=True, exist_ok=True)
    plain, _ = fly(exe, vehicle, str(scratch / 'plain.csv'), [])
    chain, log = fly(exe, vehicle, str(scratch / 'chain.csv'),
                     ['--set', 'avionics/servo/pwm-period-s=0.02', '--set', 'avionics/servo/pwm-phase-s=0.008',
                      '--set', 'avionics/servo/delay-s=0.04', '--at', '2.0:fcs/elevator-servo/malfunction/fail_zero=1'])
    print('elevator |rad| at 1.000/1.020/1.040/1.060 s: plain', [round(plain[t], 4) for t in (1.0, 1.02, 1.04, 1.06)],
          'chain', [round(chain[t], 4) for t in (1.0, 1.02, 1.04, 1.06)])
    assert plain[1.0] == 0.0 and plain[1.02] > 0.01, 'without the chain the elevator should move right after the step'
    assert chain[1.04] == 0.0 and chain[1.06] > 0.01, 'with the chain the elevator should move between 1.040 and 1.060 s'
    print(f'elevator |rad| at 1.9 s {chain[1.9]:.4f}, 2.3 s {chain[2.3]:.5f} (fail_zero from 2.0 s)')
    assert chain[1.9] > 0.2 and chain[2.3] < 0.002, 'fail_zero at 2.0 s should bring the elevator back to 0'
    assert 'fcs/elevator-servo/malfunction/fail_zero = 1' in log, 'the event is not in the log'
    bad = subprocess.run([exe, '--vehicle', vehicle, '--sitl-port', str(PORT), '--set', 'fcs/no-such-property=1'],
                         capture_output=True, text=True, timeout=30)
    print('unknown property:', bad.stderr.strip().splitlines()[-1])
    assert bad.returncode != 0 and 'no property fcs/no-such-property' in bad.stderr
    print('PASS')


if __name__ == '__main__':
    main()
