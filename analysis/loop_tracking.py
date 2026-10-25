#!/usr/bin/env python3
"""How a looping Mission (e.g. a racetrack) was flown, from one ULog: track error, turn roll commands, ground speed
per leg, airspeed and height ranges. Exploratory numbers, never an acceptance verdict.

  "$PY" -B analysis/loop_tracking.py --ulog LOG.ulg --mission hitl/missions/example_loop.json [--all]

Window (default): the second Mission stretch (after the flight first left Mission, e.g. for a test in another mode),
10 s after entering it: on the loop already. The first Mission stretch holds the run-in from the climb, which flies
to whatever item the FC had as current (kept on the FC across reboots and re-uploads of the same mission), so it may
cross the field and turn back. --all: every Mission stretch, 10 s after each entry.
Positions are east/north metres from the mission's home (vehicle_global_position, equirectangular). The mission
JSON (hitl/missions/mission.py) gives the home and the waypoints (waypoints_east_north_m) of the closed loop. The legs
are the loop's two longest segments, whatever the waypoints (they may be moved in QGroundControl and imported): on a
leg means 25 m clear of both its ends and within 50 m of it. A leg is named by its side of the loop and its direction
of flight (e.g. south_westbound); the turns by the end of the loop they are at (e.g. west: beyond the legs' western
ends). Times are seconds since the log start, as in analysis/ulog_export.py. Prints one JSON object.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

try:
    from . import ulog
except ImportError:
    import ulog

MISSION = 3  # vehicle_status nav_state AUTO_MISSION
SETTLE_S = 10.0
LEG_END_MARGIN_M = 25.0   # leg samples stay this far from the leg's waypoints (turn entry and exit)
LEG_HALF_WIDTH_M = 50.0   # and this close to the leg's line


def euler_deg(q):
    """Roll, pitch, yaw in degrees from PX4 quaternions (w, x, y, z)."""
    w, x, y, z = np.asarray(q, dtype=float).T
    return np.degrees(np.column_stack((np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
                                       np.arcsin(np.clip(2 * (w * y - z * x), -1, 1)),
                                       np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))))


def mission_intervals(t, nav_state):
    """[(start + SETTLE_S, end)] of every Mission stretch; empty ones dropped."""
    out, start = [], None
    for ti, m in zip(t, nav_state):
        if m == MISSION and start is None:
            start = ti
        elif m != MISSION and start is not None:
            out.append((start + SETTLE_S, ti))
            start = None
    if start is not None:
        out.append((start + SETTLE_S, t[-1]))
    return [(float(a), float(b)) for a, b in out if b > a]


def path_distance(e, n, loop):
    """Distance to the closed polyline loop (rows east, north; first point repeated at the end): positive outside
    the loop, negative inside."""
    best = np.full(np.shape(e), np.inf)
    inside = np.zeros(np.shape(e), dtype=bool)
    for (e1, n1), (e2, n2) in zip(loop[:-1], loop[1:]):
        de, dn = e2 - e1, n2 - n1
        s = np.clip(((e - e1) * de + (n - n1) * dn) / (de * de + dn * dn), 0, 1)
        best = np.minimum(best, np.hypot(e - (e1 + s * de), n - (n1 + s * dn)))
        if n1 != n2:  # ray casting toward +east
            inside ^= ((n1 > n) != (n2 > n)) & (e < (e2 - e1) * (n - n1) / (n2 - n1) + e1)
    return np.where(inside, -best, best)


def compass(v):
    return ('east' if v[0] > 0 else 'west') if abs(v[0]) >= abs(v[1]) else ('north' if v[1] > 0 else 'south')


def legs(wps):
    """The loop's geometry from its waypoints: the two straight legs (the loop's two longest segments) in
    flying order as dicts (name, start, end, length, unit direction, bearing in compass degrees), and the two ends of
    the loop along the legs as (name, boundary): a point is at that end's turn when its coordinate along the legs
    (see along()) is below the first boundary or above the second. ValueError when no two segments stand out."""
    wps = np.asarray(wps, dtype=float)
    seg = np.diff(np.vstack([wps, wps[:1]]), axis=0)
    length = np.hypot(seg[:, 0], seg[:, 1])
    order = np.argsort(-length, kind='stable')
    if len(wps) < 4 or length[order[1]] < 2 * length[order[2]]:
        raise ValueError('no two clear straight legs: the two longest segments are not twice the next one')
    out = []
    for i in sorted(order[:2]):
        u = seg[i] / length[i]
        out.append({'start': wps[i], 'end': wps[(i + 1) % len(wps)], 'length': float(length[i]), 'unit': u,
                    'bearing': float(np.degrees(np.arctan2(u[0], u[1])) % 360)})
    axis = out[0]['unit'] if compass(out[0]['unit']) in ('east', 'north') else -out[0]['unit']
    side = np.array([-axis[1], axis[0]])  # axis turned 90 deg to the left: north when the legs run east
    for leg, other in ((out[0], out[1]), (out[1], out[0])):
        across = (leg['start'] + leg['end']) @ side - (other['start'] + other['end']) @ side
        leg['name'] = f"{compass(side if across > 0 else -side)}_{compass(leg['unit'])}bound"
    if out[0]['name'] == out[1]['name']:
        raise ValueError(f"both legs are {out[0]['name']}: not a loop")
    low = np.mean([min(leg['start'] @ axis, leg['end'] @ axis) for leg in out])
    high = np.mean([max(leg['start'] @ axis, leg['end'] @ axis) for leg in out])
    return out, {'axis': axis, 'ends': ((compass(-axis), float(low)), (compass(axis), float(high)))}


def on_leg(e, n, leg):
    """Samples on this leg: clear of its ends by LEG_END_MARGIN_M and within LEG_HALF_WIDTH_M of its line."""
    de, dn = e - leg['start'][0], n - leg['start'][1]
    along = de * leg['unit'][0] + dn * leg['unit'][1]
    across = de * leg['unit'][1] - dn * leg['unit'][0]
    return ((along >= LEG_END_MARGIN_M) & (along <= leg['length'] - LEG_END_MARGIN_M)
            & (np.abs(across) <= LEG_HALF_WIDTH_M))


def rounded(x, digits=1):
    return round(float(x), digits)


def metrics(log, mission, every=False):
    lat0, lon0 = mission['home']
    wps = np.asarray(mission['waypoints_east_north_m'], dtype=float)
    loop = np.vstack([wps, wps[:1]])
    track_legs, shape = legs(wps)
    t0 = log.start_us * 1e-6

    def rows(name, multi=0):
        r = log.topics[(name, multi)]
        return r, r['timestamp'].astype(np.float64) * 1e-6 - t0

    st, st_t = rows('vehicle_status')
    windows = mission_intervals(st_t, st['nav_state'])
    if not every:
        windows = windows[1:2]
    if not windows:
        raise ValueError('no Mission stretch to measure (the default needs a second one: --all takes every stretch)')

    def inside(t):
        mask = np.zeros(t.shape, dtype=bool)
        for a, b in windows:
            mask |= (t >= a) & (t <= b)
        return mask

    gp, gp_t = rows('vehicle_global_position')
    k = 6371000.0
    e_all = np.radians(gp['lon'] - lon0) * k * math.cos(math.radians(lat0))
    n_all = np.radians(gp['lat'] - lat0) * k
    lp, lp_t = rows('vehicle_local_position')
    m = inside(gp_t)
    e, n = e_all[m], n_all[m]
    d = path_distance(e, n, loop)
    vx, vy = np.interp(gp_t[m], lp_t, lp['vx']), np.interp(gp_t[m], lp_t, lp['vy'])
    gs = np.hypot(vx, vy)
    course = np.degrees(np.arctan2(vy, vx)) % 360
    leg_mask = {leg['name']: on_leg(e, n, leg) for leg in track_legs}
    straight = np.logical_or.reduce(list(leg_mask.values()))

    def off(c, ref):
        return np.abs((c - ref + 180) % 360 - 180)

    wrong = np.logical_or.reduce([leg_mask[leg['name']] & (off(course, leg['bearing']) > 90) for leg in track_legs])
    dt = float(np.median(np.diff(gp_t))) if len(gp_t) > 1 else 0.0

    sp, sp_t = rows('vehicle_attitude_setpoint')
    roll_sp = np.abs(euler_deg(sp['q_d'])[:, 0])
    rs = roll_sp[inside(sp_t)]
    along_all = e_all * shape['axis'][0] + n_all * shape['axis'][1]
    (low_name, low), (high_name, high) = shape['ends']
    turns = {}
    for end, sel in ((low_name, along_all < low), (high_name, along_all > high)):
        idx = np.flatnonzero(sel & inside(gp_t))
        peaks = []
        for p in (np.split(idx, np.flatnonzero(np.diff(idx) > 5) + 1) if idx.size else []):
            if p.size >= 20:
                w = (sp_t >= gp_t[p[0]]) & (sp_t <= gp_t[p[-1]])
                peaks.append(rounded(roll_sp[w].max()))
        turns[end] = peaks
    aspd, aspd_t = rows('airspeed_validated')
    cas = aspd['calibrated_airspeed_m_s'][inside(aspd_t)]
    alt = -lp['z'][inside(lp_t)]
    airborne = np.interp(gp_t, lp_t, (-lp['z'] > 20).astype(float)) > .5
    out = {
        'window_s': [[rounded(a), rounded(b)] for a, b in windows],
        'mission_s': rounded(sum(b - a for a, b in windows)),
        'legs': {leg['name']: {'from_m': [rounded(v) for v in leg['start']], 'to_m': [rounded(v) for v in leg['end']],
                               'length_m': rounded(leg['length'])} for leg in track_legs},
        'track_error_m': {'mean_abs': rounded(np.abs(d).mean()), 'p95_abs': rounded(np.percentile(np.abs(d), 95)),
                          'max_outside': rounded(d.max()), 'max_inside': rounded(max(0.0, -d.min())),
                          'straight_mean_abs': rounded(np.abs(d[straight]).mean()) if straight.any() else None,
                          'straight_max_abs': rounded(np.abs(d[straight]).max()) if straight.any() else None},
        'roll_command_deg': {'max': rounded(rs.max()), 'fraction_over_45': rounded((rs > 45).mean(), 3),
                             'fraction_at_limit_49_5': rounded((rs > 49.5).mean(), 3)},
        'turn_roll_command_peaks_deg': turns,
        'ground_speed_m_s': {**{name: rounded(gs[mask].mean()) if mask.any() else None for name, mask in leg_mask.items()},
                             'min': rounded(gs.min()), 'max': rounded(gs.max())},
        'wrong_way_on_leg_s': rounded(wrong.sum() * dt),
        'cas_m_s': [rounded(cas.min()), rounded(cas.max())],
        'altitude_m': [rounded(alt.min()), rounded(alt.max())],
        'max_distance_from_home_m': rounded(np.hypot(e_all, n_all)[airborne].max()) if airborne.any() else None,
    }
    if ('fixed_wing_lateral_guidance_status', 0) in log.topics:
        g, g_t = rows('fixed_wing_lateral_guidance_status')
        w = inside(g_t)
        out['npfg'] = {'track_error_mean_abs_m': rounded(np.abs(g['signed_track_error'][w]).mean()),
                       'track_error_max_abs_m': rounded(np.abs(g['signed_track_error'][w]).max()),
                       'bearing_feas_min': rounded(g['bearing_feas'][w].min(), 2)}
    if ('wind', 0) in log.topics:
        g, g_t = rows('wind')
        w = inside(g_t)
        out['ekf_wind_ne_m_s'] = [rounded(g['windspeed_north'][w].mean()), rounded(g['windspeed_east'][w].mean())]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ulog', type=Path, required=True)
    parser.add_argument('--mission', type=Path, required=True, help='mission JSON (home, waypoints_east_north_m)')
    parser.add_argument('--all', action='store_true', help='every Mission stretch, not only the second')
    args = parser.parse_args()
    print(json.dumps(metrics(ulog.read(args.ulog), json.loads(args.mission.read_text()), args.all)))


if __name__ == '__main__':
    main()
