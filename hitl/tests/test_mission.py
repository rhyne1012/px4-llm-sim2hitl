"""The looping Mission tool (hitl/missions/mission.py): the definition file's layout, the QGroundControl plan both
ways (written from the definition, and a plan edited in QGC imported back), and what an import refuses. No FC."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1]
SCRIPT = RUNTIME / 'missions' / 'mission.py'
sys.path.insert(0, str(SCRIPT.parent))
import mission  # noqa: E402

WAYPOINT = mission.MAV_CMD_NAV_WAYPOINT


class MissionToolTests(unittest.TestCase):
    def setUp(self):
        self.definition = mission.load(mission.DEFINITION)
        self.plan = mission.qgc_plan(self.definition)

    def waypoint_items(self, plan):
        return [item for item in plan['mission']['items'] if item['command'] == WAYPOINT]

    def test_definition_file_layout(self):
        self.assertEqual(mission.dump(self.definition), mission.DEFINITION.read_text())

    def test_repo_plan_is_written_from_the_definition(self):
        self.assertEqual(json.loads(mission.DEFINITION.with_suffix('.plan').read_text()), self.plan)

    def test_unchanged_plan_imports_to_the_same_definition(self):
        new = mission.from_plan(self.plan, self.definition)
        self.assertEqual(new, self.definition)
        self.assertEqual(mission.changes(self.definition, new, self.plan),
                         {'qgc_planned_home_from_definition_home_m': 0.0})

    def test_moved_waypoint_comes_back_in_metres(self):
        plan = copy.deepcopy(self.plan)
        self.waypoint_items(plan)[3]['params'][4:6] = mission.offset(self.definition['home'], -210.6, 150.6)
        new = mission.from_plan(plan, self.definition)
        expected = copy.deepcopy(self.definition['waypoints_east_north_m'])
        expected[3] = [-210.6, 150.6]  # WP4 10 m east and 10 m north
        self.assertEqual(new['waypoints_east_north_m'], expected)
        moved = mission.changes(self.definition, new, plan)['moved']
        self.assertEqual([(m['wp'], m['moved_m']) for m in moved], [(4, 14.14)])
        self.assertEqual(mission.mavlink_items(new)[4][3:5], tuple(self.waypoint_items(plan)[3]['params'][4:6]))

    def test_qgc_renumbering_and_planned_home(self):
        """QGC renumbers doJumpIds when it saves; the jump has to follow the first waypoint."""
        plan = copy.deepcopy(self.plan)
        items = plan['mission']['items']
        for number, item in enumerate(items, start=11):
            item['doJumpId'] = number
        items[-1]['params'][0] = items[1]['doJumpId']
        plan['mission']['plannedHomePosition'] = [*mission.offset(self.definition['home'], 5, 2), 12.0]
        new = mission.from_plan(plan, self.definition)
        self.assertEqual(new, self.definition)
        self.assertEqual(mission.changes(self.definition, new, plan)['qgc_planned_home_from_definition_home_m'], 5.4)

    def test_altitude_speed_and_loop_count(self):
        plan = copy.deepcopy(self.plan)
        for item in self.waypoint_items(plan):
            item['params'][6] = 80.0
        plan['mission']['items'][0]['params'][1] = 17.0
        plan['mission']['items'][-1]['params'][1] = 10
        new = mission.from_plan(plan, self.definition)
        self.assertEqual((new['altitude_m'], new['airspeed_mps'], new['loop_repeat']), (80.0, 17.0, 10))

    def test_no_airspeed_keeps_the_trim_airspeed(self):
        definition = {k: v for k, v in self.definition.items() if k != 'airspeed_mps'}
        items = mission.mavlink_items(definition)
        self.assertEqual([item[1] for item in items].count(mission.MAV_CMD_DO_CHANGE_SPEED), 0)
        self.assertEqual(items[-1][2][0], 0)  # DO_JUMP back to the first waypoint, now sequence 0
        plan = mission.qgc_plan(definition)
        self.assertNotIn('cruiseSpeed', plan['mission'])
        self.assertEqual(plan['mission']['items'][-1]['params'][0], 1)  # its doJumpId
        self.assertEqual(mission.from_plan(plan, definition), definition)

    def test_refused_plans_name_the_item(self):
        def refused(edit, needle):
            plan = copy.deepcopy(self.plan)
            edit(plan['mission']['items'])
            with self.assertRaises(ValueError) as caught:
                mission.from_plan(plan, self.definition)
            self.assertIn(needle, str(caught.exception))

        wp3 = 3  # list index of WP3; QGC numbers it item 4 (the speed item is item 1)
        refused(lambda items: items.insert(1, dict(items[1], command=22)), 'item 2: command 22')  # a takeoff item
        refused(lambda items: items[wp3].update(frame=0), 'item 4: altitude frame 0')
        refused(lambda items: items[wp3]['params'].__setitem__(0, 5), 'item 4: hold 5')
        refused(lambda items: items[wp3]['params'].__setitem__(1, 10), 'acceptance radius 10')
        refused(lambda items: items[wp3]['params'].__setitem__(6, 90), 'altitudes differ')
        refused(lambda items: items[wp3].update(type='ComplexItem'), 'item 4: ComplexItem')
        refused(lambda items: items[wp3].update(autoContinue=False), 'item 4: autoContinue is off')
        refused(lambda items: items[-1]['params'].__setitem__(0, 4), 'DO_JUMP goes to doJumpId 4')
        refused(lambda items: items.pop(), 'must end with DO_JUMP')
        refused(lambda items: items.pop(0), 'no DO_CHANGE_SPEED')
        refused(lambda items: items[0]['params'].__setitem__(0, 1), 'airspeed (type 0)')
        with self.assertRaises(ValueError):
            mission.from_plan({'fileType': 'GeoFence'}, self.definition)

    def test_command_line_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            definition = Path(tmp) / 'track.json'
            definition.write_text(mission.DEFINITION.read_text())
            plan = copy.deepcopy(self.plan)
            self.waypoint_items(plan)[0]['params'][4:6] = mission.offset(self.definition['home'], 155.0, 70.0)
            source = Path(tmp) / 'field.plan'
            source.write_text(json.dumps(plan))

            def run(*args):
                return subprocess.run([sys.executable, '-B', str(SCRIPT), '--definition', str(definition),
                                       '--import', str(source), *args], capture_output=True, text=True)

            dry = run('--dry-run')
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(json.loads(dry.stdout)['changes']['moved'][0]['wp'], 1)
            self.assertEqual(definition.read_text(), mission.DEFINITION.read_text())  # nothing written
            done = run()
            self.assertEqual(done.returncode, 0, done.stderr)
            new = mission.load(definition)
            self.assertEqual(new['waypoints_east_north_m'][0], [155.0, 70.0])
            self.assertEqual(definition.read_text(), mission.dump(new))
            self.assertEqual(json.loads(definition.with_suffix('.plan').read_text()), mission.qgc_plan(new))
            plan['mission']['items'][4]['frame'] = 0
            source.write_text(json.dumps(plan))
            bad = run()
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('not imported', bad.stderr)
            self.assertEqual(mission.load(definition), new)  # left as it was


if __name__ == '__main__':
    unittest.main()
