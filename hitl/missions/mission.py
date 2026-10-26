#!/usr/bin/env python3
"""A looping Mission (e.g. a racetrack) as data: one definition, two outputs, and the way back from QGroundControl.

  "$PY" -B hitl/missions/mission.py [--definition D.json] --plan <file.plan>              # QGC plan, uploaded by hand
  "$PY" -B hitl/missions/mission.py [--definition D.json] --import <qgc.plan> [--dry-run]  # loop edited in QGC, back

A definition (hitl/missions/README.md; example_loop.json) has a home, the waypoints in east/north metres from it, one
altitude above home, an optional airspeed and the loop count. An after-takeoff script can import mavlink_items() and
upload the same items over MAVLink (no script in the framework does yet). Items: DO_CHANGE_SPEED (when the definition
has an airspeed), the waypoints at the relative altitude, then DO_JUMP back to the first waypoint. There is no takeoff or landing item, so the FC needs
MIS_TKO_LAND_REQ=0. A DO_JUMP target is a mission sequence number on the MAVLink link; in a .plan file it is the
target's doJumpId, which QGroundControl turns into the sequence number when it uploads.

--import reads a plan saved by QGroundControl (e.g. waypoints moved on the field) back into the definition: waypoints,
altitude, speed and loop count; name, note and home stay. It takes only what --plan writes and refuses anything else
(another item, AMSL altitude, a hold time or radius, a jump elsewhere), so nothing is dropped silently. Then it rewrites
the .plan beside the definition from the new definition. --dry-run only prints the changes.
"""
import argparse
import json
import math
import os
from pathlib import Path

DEFINITION = Path(__file__).resolve().parent / 'example_loop.json'
MAV_FRAME_MISSION = 2
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_DO_JUMP = 177
MAV_CMD_DO_CHANGE_SPEED = 178
SPEED_TYPE_AIRSPEED = 0
DECIMALS_M = 2  # imported east/north metres; 1 cm is far below what dragging a waypoint on a map can place


def load(path=None):
    """A definition: path, else the file SIM2HITL_MISSION names (e.g. for a script's run), else the example."""
    return json.loads(Path(path or os.environ.get('SIM2HITL_MISSION') or DEFINITION).read_text())


def dump(definition):
    """The definition file's layout: one key per line, one waypoint per line."""
    lines = [f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}'
             for k, v in definition.items() if k != 'waypoints_east_north_m']
    points = ',\n'.join(f'    {json.dumps(p)}' for p in definition['waypoints_east_north_m'])
    return '{\n' + ',\n'.join(lines + [f'  "waypoints_east_north_m": [\n{points}\n  ]']) + '\n}\n'


def metres_per_degree(lat_deg):
    """WGS84 metres per degree of latitude and of longitude at this latitude; plenty for a few hundred metres."""
    lat = math.radians(lat_deg)
    return (111132.92 - 559.82 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat),
            111412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat))


def offset(home, east, north):
    m_lat, m_lon = metres_per_degree(home[0])
    return home[0] + north / m_lat, home[1] + east / m_lon


def east_north(home, lat, lon):
    """Inverse of offset()."""
    m_lat, m_lon = metres_per_degree(home[0])
    return (lon - home[1]) * m_lon, (lat - home[0]) * m_lat


def waypoints(definition):
    return [offset(definition['home'], e, n) for e, n in definition['waypoints_east_north_m']]


def mavlink_items(definition, first_seq=0, change_speed=True):
    """(frame, command, (param1..4), lat, lon, alt) in upload order; DO_JUMP targets the first waypoint's sequence.
    first_seq: items already uploaded before these (e.g. a SITL takeoff item). change_speed=False, or no airspeed_mps
    in the definition, keeps the FC's trim airspeed (e.g. an airplane that cannot fly the definition's speed)."""
    speed = definition.get('airspeed_mps') if change_speed else None
    items = [(MAV_FRAME_MISSION, MAV_CMD_DO_CHANGE_SPEED, (SPEED_TYPE_AIRSPEED, speed, -1, 0), 0.0, 0.0, 0.0)] if speed else []
    first_waypoint = first_seq + len(items)
    items += [(MAV_FRAME_GLOBAL_RELATIVE_ALT, MAV_CMD_NAV_WAYPOINT, (0, 0, 0, math.nan), lat, lon, definition['altitude_m'])
              for lat, lon in waypoints(definition)]
    items.append((MAV_FRAME_MISSION, MAV_CMD_DO_JUMP, (first_waypoint, definition['loop_repeat'], 0, 0), 0.0, 0.0, 0.0))
    return items


def qgc_plan(definition):
    """QGroundControl .plan (file version 1, mission version 2). DO_JUMP param1 is a doJumpId (1-based item number)."""
    items = []
    for jump_id, (frame, command, params, lat, lon, alt) in enumerate(mavlink_items(definition), start=1):
        if command == MAV_CMD_DO_JUMP:
            params = (params[0] + 1,) + tuple(params[1:])  # sequence 1 is doJumpId 2
        item = {'autoContinue': True, 'command': command, 'doJumpId': jump_id, 'frame': frame, 'type': 'SimpleItem',
                'params': [None if isinstance(p, float) and math.isnan(p) else p for p in params]
                + ([lat, lon, alt] if frame == MAV_FRAME_GLOBAL_RELATIVE_ALT else [0, 0, 0])}
        if frame == MAV_FRAME_GLOBAL_RELATIVE_ALT:
            item.update(AMSLAltAboveTerrain=None, Altitude=alt, AltitudeMode=1)
        items.append(item)
    home, speed = definition['home'], definition.get('airspeed_mps')
    return {'fileType': 'Plan', 'groundStation': 'QGroundControl', 'version': 1,
            'mission': dict({'cruiseSpeed': speed} if speed else {},  # no airspeed: no cruiseSpeed either
                            firmwareType=12, globalPlanAltitudeMode=1, hoverSpeed=5, items=items,
                            plannedHomePosition=[home[0], home[1], 0], vehicleType=1, version=2),
            'geoFence': {'circles': [], 'polygons': [], 'version': 2},
            'rallyPoints': {'points': [], 'version': 2}}


def _params(item):
    """A plan item's seven params as floats; null (QGC's NaN) and missing ones are NaN."""
    params = [float('nan') if p is None else float(p) for p in item.get('params') or []]
    return params + [float('nan')] * (7 - len(params))


def from_plan(plan, definition):
    """definition with the loop of a QGroundControl plan; ValueError naming every item that is not what qgc_plan()
    writes. Items are numbered as QGC lists them (the first mission item is 1)."""
    mission = plan.get('mission') if isinstance(plan, dict) and plan.get('fileType') == 'Plan' else None
    if not isinstance(mission, dict) or not isinstance(mission.get('items'), list) or not mission['items']:
        raise ValueError('not a QGroundControl plan with mission items (fileType "Plan", mission.items)')
    numbered = list(enumerate(mission['items'], start=1))
    problems = [f'item {i}: {item.get("type")} (only simple items: waypoints, change speed, jump)'
                for i, item in numbered if item.get('type') != 'SimpleItem']
    problems += [f'item {i}: autoContinue is off (the loop would stop there)'
                 for i, item in numbered if item.get('type') == 'SimpleItem' and item.get('autoContinue') is False]
    if problems:
        raise ValueError('; '.join(problems))
    speed = None
    if numbered[0][1].get('command') == MAV_CMD_DO_CHANGE_SPEED:
        params = _params(numbered[0][1])
        if params[0] != SPEED_TYPE_AIRSPEED or not params[1] > 0:
            raise ValueError(f'item 1: DO_CHANGE_SPEED must set an airspeed (type 0) above 0, got type {params[0]:g}, '
                             f'speed {params[1]:g}')
        speed = params[1]
        numbered = numbered[1:]
    if not numbered or numbered[-1][1].get('command') != MAV_CMD_DO_JUMP:
        raise ValueError('the plan must end with DO_JUMP back to the first waypoint (the endless loop)')
    (jump_i, jump), points = numbered[-1], numbered[:-1]
    altitudes, east_north_m = [], []
    for i, item in points:
        params = _params(item)
        if item.get('command') != MAV_CMD_NAV_WAYPOINT:
            problems.append(f'item {i}: command {item.get("command")} (only waypoints between the speed item and the jump)')
        elif item.get('frame') != MAV_FRAME_GLOBAL_RELATIVE_ALT:
            problems.append(f'item {i}: altitude frame {item.get("frame")} (only relative to home, frame 3)')
        elif any(params[k] != 0 for k in range(3)):
            problems.append(f'item {i}: hold {params[0]} s, acceptance radius {params[1]} m, pass radius {params[2]} m '
                            '(all must be 0: NAV_ACC_RAD applies)')
        elif not all(math.isfinite(v) for v in params[4:7]):
            problems.append(f'item {i}: no position or altitude')
        else:
            altitudes.append(params[6])
            east, north = east_north(definition['home'], params[4], params[5])
            east_north_m.append([round(east, DECIMALS_M), round(north, DECIMALS_M)])
    if speed is None and definition.get('airspeed_mps'):
        problems.append(f'no DO_CHANGE_SPEED as the first item (the definition flies {definition["airspeed_mps"]:g} m/s: '
                        'put it back first in QGC, or change airspeed_mps in the definition by hand)')
    if len(points) < 4:
        problems.append(f'{len(points)} waypoints (a loop needs at least 4)')
    if altitudes and max(altitudes) - min(altitudes) > 0.01:
        problems.append(f'altitudes differ ({", ".join(f"{a:g}" for a in altitudes)} m): the loop has one altitude')
    jump_params = _params(jump)
    if points and jump_params[0] != points[0][1].get('doJumpId'):
        problems.append(f'item {jump_i}: DO_JUMP goes to doJumpId {jump_params[0]:g}, '
                        f'not to the first waypoint (doJumpId {points[0][1].get("doJumpId")})')
    if not jump_params[1] >= 1:
        problems.append(f'item {jump_i}: DO_JUMP repeats {jump_params[1]:g} times (at least 1)')
    if problems:
        raise ValueError('; '.join(problems))
    new = dict(definition, altitude_m=round(altitudes[0], DECIMALS_M), loop_repeat=int(jump_params[1]),
               waypoints_east_north_m=east_north_m)
    if speed is not None or 'airspeed_mps' in definition:
        new['airspeed_mps'] = speed
    return new


def changes(old, new, plan):
    """What an import changes, for the person to check before trusting it."""
    out = {key: {'from': old.get(key), 'to': new.get(key)} for key in ('altitude_m', 'airspeed_mps', 'loop_repeat')
           if old.get(key) != new.get(key)}
    a, b = old['waypoints_east_north_m'], new['waypoints_east_north_m']
    if len(a) != len(b):
        out['waypoints'] = {'from': len(a), 'to': len(b)}
    moved = [{'wp': i, 'from': p, 'to': q, 'moved_m': round(math.dist(p, q), 2)}
             for i, (p, q) in enumerate(zip(a, b), start=1) if math.dist(p, q) >= 0.01]
    if moved:
        out['moved'] = moved
    home = (plan.get('mission') or {}).get('plannedHomePosition')
    if home and len(home) >= 2 and home[0] is not None and home[1] is not None:
        east, north = east_north(old['home'], home[0], home[1])
        out['qgc_planned_home_from_definition_home_m'] = round(math.hypot(east, north), 1)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--definition', type=Path, default=DEFINITION)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--plan', type=Path, help='QGroundControl .plan file to write')
    action.add_argument('--import', dest='source', type=Path,
                        help='QGroundControl .plan to take the loop from; rewrites the definition and its .plan')
    parser.add_argument('--dry-run', action='store_true', help='with --import: print the changes, write nothing')
    args = parser.parse_args()
    if args.plan:
        args.plan.write_text(json.dumps(qgc_plan(load(args.definition)), indent=2) + '\n')
        print(json.dumps({'plan': str(args.plan), 'items': len(mavlink_items(load(args.definition)))}))
        return
    plan = json.loads(args.source.read_text())
    old = load(args.definition)
    try:
        new = from_plan(plan, old)
    except ValueError as exc:
        raise SystemExit(f'{args.source}: not imported: {exc}')
    report = {'source': str(args.source), 'changes': changes(old, new, plan) or 'none'}
    if not args.dry_run:
        out_plan = args.definition.with_suffix('.plan')
        args.definition.write_text(dump(new))
        out_plan.write_text(json.dumps(qgc_plan(new), indent=2) + '\n')
        report['written'] = [str(args.definition), str(out_plan)]
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
