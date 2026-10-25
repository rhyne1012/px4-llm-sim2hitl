#!/usr/bin/env python3
"""Review pictures of a flight from its ULog: the track on satellite imagery with the waypoints and the flight
modes, and the setpoints against the actual values over time. Other flights can be laid over the same map (e.g. a
batch of wind scenes). Exploratory pictures and numbers, never an acceptance verdict.

  "$PY" -B analysis/flight_review.py --ulog LOG.ulg [--mission MISSION.json] [--compare LOG.ulg ...] --out NEW_DIR
        [--zoom W,E,S,N] [--no-map] [--no-plots]

Positions are east/north metres from the mission's home (hitl/missions/mission.py definitions), or else from the FC's
home before takeoff. The waypoints are the mission's; without one, the distinct Mission targets of position_setpoint_triplet, i.e. what the FC
flew (waypoints moved in QGroundControl included). Times are the FC's (seconds since boot).

Imagery: Esri World Imagery tiles at zoom 19 (about 0.3 m per pixel at 23 deg latitude), fetched once into the
cache (<cache>/map_tiles/) and reused; the capture date is unknown and the alignment is a few metres at best.
--no-map draws without it (offline). The pictures need matplotlib and Pillow, which the project venv does not have:
run with a Python that has them (e.g. the PX4 venv); the numbers (--no-plots) need only numpy.

Writes track_map.png, setpoints.png and, with --zoom, zoom.png, and prints one JSON object: each flight's extent
(whole flight, and Mission plus Offboard only), the FC's waypoints against the mission's, and the home position
updates in the air (PX4 has been seen moving the home altitude by 1-2 m for the first ~2 minutes after arming).
"""
import argparse
import json
import math
from pathlib import Path
import sys
import urllib.request

import numpy as np

try:
    from . import ulog
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under python -I
    import ulog

PROJECT = Path(__file__).resolve().parents[1]
MISSION, OFFBOARD = 3, 14  # vehicle_status nav_state
MODES = {0: 'Manual', 1: 'Altitude', 2: 'Position', 3: 'Mission', 4: 'Loiter', 5: 'RTL', 10: 'Acro', 12: 'Descend',
         13: 'Termination', 14: 'Offboard', 15: 'Stabilized', 17: 'Takeoff', 18: 'Land'}
SETPOINT_POSITION = 0  # position_setpoint type
SAME_WAYPOINT_M = 2.0
TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
TILE_ZOOM = 19
ATTRIBUTION = 'Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community (capture date unknown)'
# Colours: the setpoint/plan and the actual flight keep their hue in every picture; on imagery the lighter steps.
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#898781'
ACTUAL, SETPOINT, OFFBOARD_COLOR, OTHER = '#2a78d6', '#eb6834', '#1baf7a', '#9a9891'
ACTUAL_MAP, SETPOINT_MAP, OFFBOARD_MAP, OTHER_MAP, ENVELOPE_MAP = '#6db8ff', '#ff8a50', '#3ff0b0', '#ecebe6', '#ffd23f'


def metres_per_degree(lat_deg):
    """WGS84 metres per degree of latitude and of longitude (as hitl/missions/racetrack.py)."""
    lat = math.radians(lat_deg)
    return (111132.92 - 559.82 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat),
            111412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat))


def east_north(origin, lat, lon):
    m_lat, m_lon = metres_per_degree(origin[0])
    return (np.asarray(lon, dtype=float) - origin[1]) * m_lon, (np.asarray(lat, dtype=float) - origin[0]) * m_lat


def euler_deg(q):
    w, x, y, z = np.asarray(q, dtype=float).T
    return np.degrees(np.column_stack((np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
                                       np.arcsin(np.clip(2 * (w * y - z * x), -1, 1)))))


def mode_runs(t, nav, t_end):
    """[(start, end, nav_state)] up to t_end."""
    starts = np.r_[0, np.flatnonzero(np.diff(nav)) + 1]
    ends = np.r_[t[starts[1:]], t_end]
    return [(float(t[i]), float(min(e, t_end)), int(nav[i])) for i, e in zip(starts, ends) if t[i] < t_end]


def mode_at(t, runs):
    starts = np.array([a for a, _, _ in runs])
    modes = np.array([m for _, _, m in runs])
    return modes[np.clip(np.searchsorted(starts, t, side='right') - 1, 0, None)]


def fc_waypoints(cur, e, n):
    """The FC's distinct Mission targets (position_setpoint_triplet.current, type POSITION, valid) in the order it
    first flew to them, and each sample's index into them (-1: none)."""
    usable = (cur['valid'] == 1) & (cur['type'] == SETPOINT_POSITION) & np.isfinite(e) & np.isfinite(n)
    points, index = [], np.full(len(e), -1)
    for i in np.flatnonzero(usable):
        near = [k for k, p in enumerate(points) if math.hypot(p[0] - e[i], p[1] - n[i]) < SAME_WAYPOINT_M]
        if not near:
            points.append((float(e[i]), float(n[i])))
            near = [len(points) - 1]
        index[i] = near[0]
    return points, index


def match(points, waypoints):
    """For each FC point the waypoint it is (1-based) and the distance; 0 when none is within SAME_WAYPOINT_M."""
    out = []
    for p in points:
        d = [math.dist(p, w) for w in waypoints]
        k = int(np.argmin(d)) if d else -1
        out.append((k + 1 if k >= 0 and d[k] < SAME_WAYPOINT_M else 0, d[k] if k >= 0 else math.inf))
    return out


class Flight:
    """One FC log as east/north arrays about an origin; the arrays the pictures and the numbers use."""

    def __init__(self, log, origin=None, name=''):
        self.log, self.name = log, name
        t = lambda rows: rows['timestamp'].astype(np.float64) * 1e-6  # noqa: E731  FC time
        st = log.topics[('vehicle_status', 0)]
        self.st_t, nav = t(st), st['nav_state'].astype(int)
        armed = np.flatnonzero(st['arming_state'] == 2)
        self.armed_from = float(self.st_t[armed[0]]) if armed.size else float(self.st_t[0])
        self.t_end = float(self.st_t[armed[-1]]) + 2 if armed.size else float(self.st_t[-1])
        self.runs = mode_runs(self.st_t, nav, self.t_end)
        hp = log.topics.get(('home_position', 0))
        self.home_t = t(hp) if hp is not None else np.array([])
        self.home = hp
        if origin is None:
            if hp is None or not len(hp):
                raise ValueError(f'{name}: no mission and no home_position for an origin')
            origin = (float(hp['lat'][0]), float(hp['lon'][0]))
        self.origin = origin
        gp = log.topics[('vehicle_global_position', 0)]
        keep = t(gp) <= self.t_end
        self.gp, self.t = gp[keep], t(gp)[keep]
        self.e, self.n = east_north(origin, self.gp['lat'], self.gp['lon'])
        self.mode = mode_at(self.t, self.runs)
        trip = log.topics.get(('position_setpoint_triplet', 0))
        if trip is not None and len(trip):
            cur = trip['current']
            ce, cn = east_north(origin, cur['lat'], cur['lon'])
            self.trip_t = t(trip)
            self.fc_points, self.trip_index = fc_waypoints(cur, ce, cn)
            usable = self.trip_index >= 0
            self.acceptance_m = float(np.median(cur['acceptance_radius'][usable])) if usable.any() else None
        else:
            self.trip_t, self.fc_points, self.trip_index, self.acceptance_m = np.array([]), [], np.array([]), None

    def offboard(self):
        return [(a, b) for a, b, m in self.runs if m == OFFBOARD]

    def extent(self, mask=None):
        m = np.ones(len(self.e), dtype=bool) if mask is None else mask
        if not m.any():
            return None
        e, n = self.e[m], self.n[m]
        return {'west_m': round(float(e.min()), 1), 'east_m': round(float(e.max()), 1),
                'south_m': round(float(n.min()), 1), 'north_m': round(float(n.max()), 1),
                'farthest_m': round(float(np.hypot(e, n).max()), 1)}

    def on_track(self):
        return (self.mode == MISSION) | (self.mode == OFFBOARD)

    def home_updates_in_air(self):
        """home_position samples published after takeoff (the first one comes with arming)."""
        if self.home is None or not len(self.home):
            return None
        later = (self.home_t > self.armed_from + 5) & (self.home_t < self.t_end - 2)
        if not later.any():
            return {'count': 0}
        alt = self.home['alt'][later]
        return {'count': int(later.sum()), 'alt_m': [round(float(alt.min()), 2), round(float(alt.max()), 2)],
                'last_s': round(float(self.home_t[later][-1]), 1), 'armed_s': round(self.armed_from, 1)}


def numbers(main, others, waypoints):
    out = {'origin': list(main.origin), 'flights': {}}
    for f in [main] + others:
        out['flights'][f.name] = {'whole': f.extent(), 'mission_and_offboard': f.extent(f.on_track()),
                                  'offboard_s': [[round(a, 1), round(b, 1)] for a, b in f.offboard()],
                                  'home_updates_in_air': f.home_updates_in_air()}
    if waypoints:
        matched = match(main.fc_points, waypoints)
        out['fc_waypoints'] = {'count': len(main.fc_points), 'not_in_mission': sum(1 for k, _ in matched if not k),
                               'max_offset_m': round(max((d for k, d in matched if k), default=0.0), 3)}
    else:
        out['fc_waypoints'] = {'count': len(main.fc_points)}
    return out


def tile_cache():
    try:
        sys.path.insert(0, str(PROJECT / 'plant' / 'core'))
        import toolchain
        return Path(toolchain.cache_root()) / 'map_tiles'
    except Exception:  # noqa: BLE001  any failure: the user's cache folder
        return Path.home() / '.cache' / 'px4-llm-sim2hitl' / 'map_tiles'


def imagery(origin, e_lim, n_lim, cache):
    """Stitched tiles covering the east/north box: (RGB array, (west, east, south, north) in metres, tiles fetched)."""
    from PIL import Image
    m_lat, m_lon = metres_per_degree(origin[0])
    n_tiles = 2 ** TILE_ZOOM

    def tile(lat, lon):
        return (int((lon + 180) / 360 * n_tiles),
                int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n_tiles))

    def lat_of(y):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n_tiles))))

    (x0, y0) = tile(origin[0] + n_lim[1] / m_lat, origin[1] + e_lim[0] / m_lon)
    (x1, y1) = tile(origin[0] + n_lim[0] / m_lat, origin[1] + e_lim[1] / m_lon)
    folder = cache / f'esri_z{TILE_ZOOM}'
    folder.mkdir(parents=True, exist_ok=True)
    image, fetched = Image.new('RGB', (256 * (x1 - x0 + 1), 256 * (y1 - y0 + 1))), 0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            f = folder / f'{y}_{x}.jpg'
            if not f.is_file():
                request = urllib.request.Request(TILE_URL.format(z=TILE_ZOOM, y=y, x=x),
                                                 headers={'User-Agent': 'px4-llm-sim2hitl flight_review'})
                data = urllib.request.urlopen(request, timeout=30).read()
                f.write_bytes(data)
                fetched += 1
            image.paste(Image.open(f).convert('RGB'), (256 * (x - x0), 256 * (y - y0)))
    west, north = east_north(origin, lat_of(y0), x0 / n_tiles * 360 - 180)
    east, south = east_north(origin, lat_of(y1 + 1), (x1 + 1) / n_tiles * 360 - 180)
    return np.asarray(image), (float(west), float(east), float(south), float(north)), fetched


def style():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for path in ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/System/Library/Fonts/PingFang.ttc'):
        if Path(path).is_file():
            font_manager.fontManager.addfont(path)
    installed = {f.name for f in font_manager.fontManager.ttflist}
    families = [f for f in ('Noto Sans CJK TC', 'PingFang TC', 'Microsoft JhengHei') if f in installed]
    plt.rcParams.update({'font.family': families + ['DejaVu Sans'],
                         'font.size': 10, 'axes.edgecolor': '#c3c2b7', 'axes.labelcolor': INK2,
                         'xtick.color': MUTED, 'ytick.color': MUTED, 'axes.grid': True, 'grid.color': '#e1e0d9',
                         'grid.linewidth': .6, 'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb',
                         'savefig.facecolor': '#fcfcfb', 'legend.frameon': False, 'axes.spines.top': False,
                         'axes.spines.right': False})
    return plt


def draw_map(ax, main, others, waypoints, envelope, labels, image=None, extent=None, box=None):
    import matplotlib.patheffects as pe
    from matplotlib.patches import Circle, Rectangle

    def halo(width, alpha=.6):
        return [pe.Stroke(linewidth=width, foreground='black', alpha=alpha), pe.Normal()]
    text_halo = [pe.withStroke(linewidth=2.6, foreground='black', alpha=.75)]
    on_image = image is not None
    if on_image:
        ax.imshow((image * .88).astype(np.uint8), extent=extent, zorder=0, interpolation='lanczos')
        ax.grid(False)
    text_color = 'white' if on_image else INK
    text_effects = text_halo if on_image else None
    colors = (ACTUAL_MAP, OFFBOARD_MAP, OTHER_MAP) if on_image else (ACTUAL, OFFBOARD_COLOR, OTHER)
    plan = SETPOINT_MAP if on_image else SETPOINT
    pts = np.array(waypoints) if waypoints else None
    if pts is not None:
        if main.acceptance_m:
            for x, y in pts:
                ax.add_patch(Circle((x, y), main.acceptance_m, fill=False, ls=(0, (1, 2)), lw=.8,
                                    ec='white' if on_image else MUTED, alpha=.75, zorder=1))
        loop = np.vstack([pts, pts[:1]])
        ax.plot(loop[:, 0], loop[:, 1], ls=(0, (5, 3)), lw=2.0, color=plan, zorder=3, path_effects=halo(3.8))
    for other in others:  # only on the track: their takeoffs and end orbits would hide the loop
        on = other.on_track()
        ax.plot(np.where(on, other.e, np.nan), np.where(on, other.n, np.nan), color=OTHER_MAP if on_image else OTHER,
                lw=.9, zorder=2, path_effects=halo(2.6, .45))
    phase = np.where(main.mode == MISSION, 0, np.where(main.mode == OFFBOARD, 1, 2))
    starts = np.r_[0, np.flatnonzero(np.diff(phase)) + 1]
    for a, b in zip(starts, np.r_[starts[1:], len(phase)]):
        p = phase[a]
        sl = slice(a, min(b + 1, len(phase)))
        ax.plot(main.e[sl], main.n[sl], color=colors[p], lw=(1.8, 3.4, 1.0)[p], zorder=(4, 5, 2)[p],
                solid_capstyle='round', path_effects=halo((3.6, 5.2, 2.8)[p], (.6, .6, .45)[p]))
    if pts is not None:
        ax.plot(pts[:, 0], pts[:, 1], 'o', ms=7.5, mfc='white', mec=plan, mew=2, zorder=6, path_effects=halo(4))
        center = pts.mean(axis=0)
        for i, (x, y) in enumerate(pts, start=1):
            if box and not (box[0] < x < box[1] and box[2] < y < box[3]):
                continue
            u = np.array([x, y]) - center
            u = u / (np.linalg.norm(u) or 1)
            ax.annotate(f'WP{i}', (x, y), xytext=(u[0] * 18, u[1] * 18), textcoords='offset points', ha='center',
                        va='center', fontsize=9.5, color=text_color, zorder=7, path_effects=text_effects)
    mid_n = float(np.median(main.n[main.on_track()])) if main.on_track().any() else 0.0
    for k, (a, b) in enumerate(main.offboard(), start=1):
        sel = (main.t >= a) & (main.t <= b)
        if sel.any():
            x, y = main.e[sel].mean(), main.n[sel].mean()
            if box and not (box[0] < x < box[1] and box[2] < y < box[3]):
                continue
            ax.annotate(f'#{k}', (x, y), xytext=(0, 14 if y >= mid_n else -14), textcoords='offset points',
                        ha='center', va='center', fontsize=10.5, fontweight='bold', color=text_color, zorder=7,
                        path_effects=text_effects)
    if envelope:
        w, e, s, n = envelope['west_m'], envelope['east_m'], envelope['south_m'], envelope['north_m']
        ax.add_patch(Rectangle((w, s), e - w, n - s, fill=False, ls=(0, (2, 2)), lw=1.4,
                               ec=ENVELOPE_MAP if on_image else INK2, zorder=3, path_effects=halo(3.2)))
        for x, y, text, ha, va in ((w, (s + n) / 2, f'{w:.0f}', 'right', 'center'), (e, (s + n) / 2, f'{e:.0f}', 'left', 'center'),
                                   ((w + e) / 2, s, f'{s:.0f}', 'center', 'top'), ((w + e) / 2, n, f'{n:.0f}', 'center', 'bottom')):
            ax.annotate(text.replace('-', '−') + ' m', (x, y), xytext=({'right': -4, 'left': 4}.get(ha, 0),
                        {'top': -4, 'bottom': 4}.get(va, 0)), textcoords='offset points', ha=ha, va=va, fontsize=8.5,
                        color=text_color, zorder=7, path_effects=text_effects)
    ax.plot(0, 0, marker='^', ms=10, mfc='white', mec='black', mew=1.2, zorder=8)
    ax.annotate(labels['origin'], (0, 0), xytext=(9, -3), textcoords='offset points', fontsize=10, va='top',
                color=text_color, zorder=8, path_effects=text_effects)
    if on_image:
        ax.text(.995, .008, ATTRIBUTION, transform=ax.transAxes, ha='right', va='bottom', fontsize=6.5, color='white',
                path_effects=text_halo)
    ax.set_aspect('equal')
    ax.set_xlabel('東 (m)')
    ax.set_ylabel('北 (m)')


def legend_handles(main, others, waypoints, envelope, note):
    import matplotlib.patheffects as pe
    from matplotlib.lines import Line2D

    def halo(width, alpha=.6):
        return [pe.Stroke(linewidth=width, foreground='black', alpha=alpha), pe.Normal()]
    handles = []
    if waypoints:
        handles.append(Line2D([], [], ls=(0, (5, 3)), lw=2, color=SETPOINT_MAP, marker='o', ms=6.5, mfc='white',
                              mec=SETPOINT_MAP, mew=1.8, path_effects=halo(3.8), label='航線與航點（FC 的位置 setpoint）'))
    if main.acceptance_m:
        handles.append(Line2D([], [], ls=(0, (1, 2)), lw=1, color=MUTED, label=f'航點接受半徑 {main.acceptance_m:.0f} m'))
    handles += [Line2D([], [], lw=1.8, color=ACTUAL_MAP, path_effects=halo(3.6), label=f'{main.name}：Mission'),
                Line2D([], [], lw=3.4, color=OFFBOARD_MAP, path_effects=halo(5.2),
                       label=f'{main.name}：Offboard（依序 #1…）' + (f'　{note}' if note else '')),
                Line2D([], [], lw=1.0, color=OTHER_MAP, path_effects=halo(2.8, .45), label=f'{main.name}：其他模式')]
    if others:
        names = [o.name for o in others]
        rows = ['、'.join(names[i:i + 4]) for i in range(0, len(names), 4)]
        handles.append(Line2D([], [], lw=.9, color=OTHER_MAP, path_effects=halo(2.6, .45),
                              label=f'其他 {len(others)} 趟（Mission／Offboard 時）：' + '\n'.join(rows)))
    if envelope:
        handles.append(Line2D([], [], ls=(0, (2, 2)), lw=1.4, color=ENVELOPE_MAP, path_effects=halo(3.2),
                              label=f'{"所有" if others else "這"}趟 Mission／Offboard 時的範圍（公尺）'))
    return handles


def plot_setpoints(plt, path, main, waypoints, title, note):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.transforms import blended_transform_factory
    log = main.log
    t = lambda rows: rows['timestamp'].astype(np.float64) * 1e-6  # noqa: E731
    asp, att = log.topics[('vehicle_attitude_setpoint', 0)], log.topics[('vehicle_attitude', 0)]
    sp, at = euler_deg(asp['q_d']), euler_deg(att['q'])
    ground = float(main.home['alt'][0]) if main.home is not None and len(main.home) else 0.0
    panels = [('滾轉 (°)', (t(asp), sp[:, 0]), (t(att), at[:, 0])), ('俯仰 (°)', (t(asp), sp[:, 1]), (t(att), at[:, 1]))]
    tecs = log.topics.get(('tecs_status', 0))
    aspd = log.topics.get(('airspeed_validated', 0))

    def gaps(tt, y, gap=1.0):
        cut = np.flatnonzero(np.diff(tt) > gap) + 1
        return np.insert(tt, cut, np.nan), np.insert(np.asarray(y, dtype=float), cut, np.nan)
    if tecs is not None:
        panels.append(('高度 (m，相對起飛點)', gaps(t(tecs), tecs['altitude_sp'] - ground), (main.t, main.gp['alt'] - ground)))
    if tecs is not None and aspd is not None:
        panels.append(('空速 (m/s)', gaps(t(tecs), tecs['equivalent_airspeed_sp']),
                       (t(aspd), aspd['calibrated_airspeed_m_s'])))
    rows = len(panels) + 1
    fig, axes = plt.subplots(rows, 1, figsize=(12, 2.3 * rows), sharex=True,
                             gridspec_kw={'height_ratios': [1] * len(panels) + [.8]})
    for ax, (label, (ts, ys), (ta, ya)) in zip(axes, panels):
        ax.plot(ta, ya, color=ACTUAL, lw=1.1, zorder=3)
        ax.plot(ts, ys, color=SETPOINT, lw=1.1, zorder=4)
        ax.set_ylabel(label)
        if label.startswith('高度'):
            on = main.on_track()
            if on.any():
                lo, hi = np.percentile(main.gp['alt'][on] - ground, [1, 99])
                ax.set_ylim(lo - 15, hi + 15)
    wp_ax = axes[-1]
    if main.fc_points:
        target = np.full(len(main.trip_index), np.nan)
        number = [k for k, _ in match(main.fc_points, waypoints)] if waypoints else list(range(1, len(main.fc_points) + 1))
        for i, k in enumerate(main.trip_index):
            if k >= 0 and number[k]:
                target[i] = number[k]
        wp_ax.step(np.r_[main.trip_t, main.t_end], np.r_[target, target[-1]], where='post', color=SETPOINT, lw=1.6)
        top = int(np.nanmax(target)) if np.isfinite(target).any() else 1
        wp_ax.set_yticks(range(1, top + 1))
        wp_ax.set_ylim(.3, top + .7)
    wp_ax.set_ylabel('目標航點 (WP)')
    for ax in axes:
        for a, b, m in main.runs:
            if m == OFFBOARD:
                ax.axvspan(a, b, color=OFFBOARD_COLOR, alpha=.22, lw=0, zorder=1)
            elif m != MISSION:
                ax.axvspan(a, b, color=OTHER, alpha=.14, lw=0, zorder=1)
    top_axis = blended_transform_factory(axes[0].transData, axes[0].transAxes)
    for k, (a, b) in enumerate(main.offboard(), start=1):
        axes[0].text((a + b) / 2, 1.03, f'#{k}', transform=top_axis, ha='center', va='bottom', fontsize=9.5,
                     fontweight='bold', color=INK)
    bottom_axis = blended_transform_factory(wp_ax.transData, wp_ax.transAxes)
    for a, b, m in main.runs:
        if m not in (MISSION, OFFBOARD) and b - a >= 4:
            wp_ax.text((a + b) / 2, .5, MODES.get(m, str(m)), transform=bottom_axis, rotation=90, ha='center',
                       va='center', fontsize=8.5, color=INK2)
    wp_ax.set_xlabel('FC 時間 (s)')
    wp_ax.set_xlim(main.st_t[0], main.t_end)
    fig.suptitle('Setpoint 與實際值', x=.012, ha='left', fontsize=13, color=INK, y=.995)
    fig.text(.012, .97, title + (f'・{note}' if note else ''), fontsize=9, color=MUTED)
    fig.legend(handles=[Line2D([], [], color=SETPOINT, lw=1.6, label='setpoint（姿態 vehicle_attitude_setpoint；高度、空速 TECS；航點 position_setpoint_triplet）'),
                        Line2D([], [], color=ACTUAL, lw=1.6, label='實際（姿態 EKF、高度 global position、空速 CAS）'),
                        Patch(color=OFFBOARD_COLOR, alpha=.35, label='Offboard'),
                        Patch(color=OTHER, alpha=.3, label='Mission 以外的模式')],
               loc='upper left', bbox_to_anchor=(.006, .962), ncol=2, fontsize=9, labelcolor=INK2)
    fig.tight_layout(rect=(0, 0, 1, .935))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def pictures(out, main, others, waypoints, title, note, zoom=None, use_map=True):
    plt = style()
    envelope_mask = [f.on_track() for f in [main] + others]
    ext = [f.extent(m) for f, m in zip([main] + others, envelope_mask)]
    ext = [x for x in ext if x]
    envelope = ({'west_m': min(x['west_m'] for x in ext), 'east_m': max(x['east_m'] for x in ext),
                 'south_m': min(x['south_m'] for x in ext), 'north_m': max(x['north_m'] for x in ext)}
                if ext else None)
    every_e = np.concatenate([f.e for f in [main] + others] + ([np.array(waypoints)[:, 0]] if waypoints else []))
    every_n = np.concatenate([f.n for f in [main] + others] + ([np.array(waypoints)[:, 1]] if waypoints else []))
    e_lim = (float(every_e.min()) - 40, float(every_e.max()) + 25)
    n_lim = (float(min(every_n.min(), 0)) - 20, float(every_n.max()) + 25)
    image = extent = None
    fetched = 0
    if use_map:
        boxes = [e_lim + n_lim] + ([zoom] if zoom else [])
        image, extent, fetched = imagery(main.origin, (min(b[0] for b in boxes), max(b[1] for b in boxes)),
                                         (min(b[2] for b in boxes), max(b[3] for b in boxes)), tile_cache())
    labels = {'origin': 'Home'}
    written = []
    for name, lims, size in (('track_map.png', (e_lim, n_lim), (12, 8.6)),
                             ('zoom.png', ((zoom[0], zoom[1]), (zoom[2], zoom[3])) if zoom else None, (8, 8.6))):
        if lims is None:
            continue
        fig, ax = plt.subplots(figsize=size)
        draw_map(ax, main, others, waypoints, envelope, labels, image, extent,
                 box=(lims[0] + lims[1]) if name == 'zoom.png' else None)
        ax.set_xlim(*lims[0])
        ax.set_ylim(*lims[1])
        ax.set_title('航線與位置 setpoint' if name == 'track_map.png' else '放大', loc='left', fontsize=13, color=INK,
                     pad=24)
        ax.text(0, 1.015, title, transform=ax.transAxes, fontsize=9, color=MUTED)
        ax.legend(handles=legend_handles(main, others, waypoints, envelope, note), loc='upper left',
                  bbox_to_anchor=(0, -0.075), ncol=1, fontsize=9, labelcolor=INK2)
        fig.savefig(out / name, dpi=150, bbox_inches='tight', pad_inches=.15)
        plt.close(fig)
        written.append(name)
    plot_setpoints(plt, out / 'setpoints.png', main, waypoints, title, note)
    return written + ['setpoints.png'], fetched


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ulog', type=Path, required=True, help='FC log')
    parser.add_argument('--mission', type=Path, help='mission JSON (home, waypoints_east_north_m)')
    parser.add_argument('--compare', nargs='*', type=Path, default=[], help='other FC logs drawn on the same map')
    parser.add_argument('--out', type=Path, required=True, help='new or empty folder for the pictures')
    parser.add_argument('--zoom', help='W,E,S,N in metres: also a zoomed map (zoom.png)')
    parser.add_argument('--no-map', action='store_true', help='no imagery (offline)')
    parser.add_argument('--no-plots', action='store_true', help='numbers only (numpy only)')
    args = parser.parse_args()
    name = args.ulog.stem
    mission = json.loads(args.mission.read_text()) if args.mission else None
    origin = tuple(mission['home']) if mission else None
    main_flight = Flight(ulog.read(args.ulog), origin, name)
    others = [Flight(ulog.read(p), main_flight.origin, p.stem) for p in args.compare]
    waypoints = [tuple(p) for p in mission['waypoints_east_north_m']] if mission else main_flight.fc_points
    report = numbers(main_flight, others, waypoints if mission else None)
    if not args.no_plots:
        args.out.mkdir(parents=True, exist_ok=True)
        if any(args.out.iterdir()):
            raise SystemExit(f'{args.out} is not empty')
        zoom = [float(v) for v in args.zoom.split(',')] if args.zoom else None
        written, fetched = pictures(args.out, main_flight, others, waypoints, name, '', zoom, not args.no_map)
        report.update(pictures=written, tiles_fetched=fetched)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
