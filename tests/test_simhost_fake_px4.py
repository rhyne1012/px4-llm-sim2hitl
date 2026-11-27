#!/usr/bin/env python3
"""simhost against a fake PX4: connect like simulator_mavlink, answer every HIL_SENSOR in lockstep, check the sensors.

    <python with pymavlink> tests/test_simhost_fake_px4.py build/simhost/simhost vehicles/testbird

Checks, with Testbird at rest on the ground and then at full throttle with the brakes off:
  - HIL_SENSOR every 4 ms of simulated time, HIL_GPS every 0.1 s
  - at rest: accelerometer about (0, 0, -9.81) m/s2, gyro about 0, barometer about 1013 hPa, airspeed about 0
  - a magnetometer field from PX4's World Magnetic Model tables (printed; checked by eye against PX4's own value)
  - the throttle channel reaches JSBSim: the vehicle accelerates along the runway
"""
import math
import socket
import subprocess
import sys
import time

from pymavlink.dialects.v20 import common as mav

PORT = 4599


def main():
    exe, vehicle = sys.argv[1], sys.argv[2]
    proc = subprocess.Popen([exe, '--vehicle', vehicle, '--sitl-port', str(PORT), '--lockstep', '--duration', '20',
                             '--actuator', '4:fcs/throttle-cmd-norm:1'], stderr=subprocess.PIPE, text=True)
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
        sensors, gps, rest = [], [], None
        buf = b''
        sent_first = False
        while True:
            data = sock.recv(65536)
            if not data:
                break
            for m in link.parse_buffer(data) or []:
                if m.get_type() == 'HIL_SENSOR':
                    sensors.append(m)
                    t = m.time_usec / 1e6
                    throttle = 1.0 if t >= 10.0 else 0.0
                    controls = [0.0] * 16
                    controls[4] = throttle
                    out = mav.MAVLink_hil_actuator_controls_message(m.time_usec, controls, mav.MAV_MODE_FLAG_SAFETY_ARMED, 1)
                    sock.sendall(out.pack(link))
                    sent_first = True
                    if abs(t - 5.0) < 1e-6:
                        rest = m
                elif m.get_type() == 'HIL_GPS':
                    gps.append(m)
        del buf, sent_first
    finally:
        _, err = proc.communicate(timeout=30)
    print(err.strip().splitlines()[-1])
    assert proc.returncode == 0, err

    times = [s.time_usec for s in sensors]
    steps = {b - a for a, b in zip(times, times[1:])}
    assert steps == {4000}, f'HIL_SENSOR steps {sorted(steps)[:5]}'
    gps_steps = {b.time_usec - a.time_usec for a, b in zip(gps, gps[1:])}
    assert gps_steps == {100000}, f'HIL_GPS steps {sorted(gps_steps)[:5]}'
    r = rest
    print(f'at rest (5 s): acc ({r.xacc:.3f}, {r.yacc:.3f}, {r.zacc:.3f}) gyro ({r.xgyro:.4f}, {r.ygyro:.4f}, {r.zgyro:.4f}) '
          f'mag ({r.xmag:.4f}, {r.ymag:.4f}, {r.zmag:.4f}) |B| {math.sqrt(r.xmag**2 + r.ymag**2 + r.zmag**2):.4f} G '
          f'baro {r.abs_pressure:.2f} hPa diff {r.diff_pressure:.4f} hPa temp {r.temperature:.1f} C')
    assert abs(r.zacc + 9.81) < 0.3 and abs(r.xacc) < 0.3 and abs(r.yacc) < 0.3
    assert max(abs(r.xgyro), abs(r.ygyro), abs(r.zgyro)) < 0.02
    assert abs(r.abs_pressure - 1013.25) < 1.0
    assert abs(r.diff_pressure) < 0.05
    g0, g1 = gps[0], gps[-1]
    speed = math.hypot(g1.vn, g1.ve) / 100.0
    print(f'GPS: {g0.lat / 1e7:.6f}, {g0.lon / 1e7:.6f}, alt {g0.alt / 1000:.2f} m; after 10 s at full throttle: ground speed '
          f'{speed:.1f} m/s, moved {math.hypot((g1.lat - g0.lat) * 0.0111, (g1.lon - g0.lon) * 0.0111 * math.cos(math.radians(22.91))):.0f} m')
    assert speed > 5.0, 'full throttle did not move the vehicle'
    print('PASS')


if __name__ == '__main__':
    main()
