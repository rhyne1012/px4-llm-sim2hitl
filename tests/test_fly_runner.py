#!/usr/bin/env python3
"""Offline checks of tools/fly.py: a flight's PASS needs this run's own check result, and the runner never stops a
SITL FC instance it did not start. No PX4, simhost or flight controller is used.

    <python with pymavlink> -B tests/test_fly_runner.py
"""
import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT / 'tools'))
import fly  # noqa: E402


def make_repo(root, check_code):
    """A vehicle repository with one recipe whose check is check_code (Python source)."""
    repo = root / 'repo'
    (repo / 'recipe' / 'firmware').mkdir(parents=True)
    (repo / 'sim2hitl.lock').write_text('{}')
    (repo / 'recipe' / 'firmware' / 'firmware.json').write_text(json.dumps({'embedded': {'board_id': 1}}))
    (repo / 'recipe' / 'params.json').write_text(json.dumps({'firmware_params': {'file': 'x'}, 'fc_owned': {'patterns': []}}))
    (repo / 'recipe' / 'hitl.json').write_text(json.dumps({'check': 'check.py'}))
    (repo / 'check.py').write_text(check_code)
    return repo


def args(repo, out, mode='sitl', instance=5):
    return argparse.Namespace(mode=mode, recipe=str(repo / 'recipe'), repo=str(repo), out=str(out), instance=instance,
                              vehicle='unused', config=[], at=[], link=None, baud=2000000, deploy='reuse',
                              reset_unmanaged=False, log_once=False, keep_state=False)


WRITE = "import json, sys\njson.dump({{'verdict': '{v}'}}, open(sys.argv[sys.argv.index('--out') + 1], 'w'))\n"


class CheckResult(unittest.TestCase):
    def verdict_of(self, check_code):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = make_repo(root, check_code)
            run = fly.Run(args(repo, root / 'run'))
            ulog = root / 'run' / 'fc_log.ulg'
            ulog.write_bytes(b'')
            return run.check(ulog)

    def test_pass(self):
        r = self.verdict_of(WRITE.format(v='PASS'))
        self.assertEqual((r['verdict'], r['checker_exit']), ('PASS', 0))

    def test_no_result_is_an_error(self):
        r = self.verdict_of('import sys\nsys.exit(7)\n')
        self.assertEqual(r['verdict'], 'ERROR')

    def test_pass_with_a_failed_exit_is_an_error(self):
        r = self.verdict_of(WRITE.format(v='PASS') + 'sys.exit(7)\n')
        self.assertEqual(r['verdict'], 'ERROR')

    def test_fail_keeps_its_details(self):
        r = self.verdict_of(WRITE.format(v='FAIL') + 'sys.exit(1)\n')
        self.assertEqual((r['verdict'], r['checker_exit']), ('FAIL', 1))

    def test_an_earlier_result_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = make_repo(root, 'import sys\nsys.exit(7)\n')
            (root / 'run').mkdir()
            (root / 'run' / 'check.json').write_text(json.dumps({'verdict': 'PASS'}))
            with self.assertRaises(SystemExit):   # a used run folder is refused before anything runs
                fly.Run(args(repo, root / 'run'))


class Verdict(unittest.TestCase):
    GOOD = {'check': {'verdict': 'PASS', 'checker_exit': 0}, 'pilot_exit': 0, 'after_state': 'complete'}

    def test_pass(self):
        s = dict(self.GOOD, simhost_problems=fly.simhost_problems({'lockstep_waits_timed_out': 0, 'late_steps': 0}, 'sitl'))
        self.assertEqual(fly.verdict(s), 'PASS')

    def test_simhost_timing_fails_the_flight(self):
        for sim, mode in (({'lockstep_waits_timed_out': 1}, 'sitl'), ({'late_steps': 2, 'max_lateness_ms': 6.1}, 'hitl'),
                          (None, 'sitl')):
            s = dict(self.GOOD, simhost_problems=fly.simhost_problems(sim, mode))
            self.assertEqual(fly.verdict(s), 'FAIL', (sim, mode))


class SitlInstance(unittest.TestCase):
    def test_a_running_instance_is_refused_and_not_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = make_repo(root, '')
            run = fly.Run(args(repo, root / 'run'))
            calls = []

            def sh(cmd, **_):
                calls.append([str(c) for c in cmd])
                return subprocess.CompletedProcess(cmd, 1, '', 'SITL FC instance 5 is running (supervisor 123): stop it first')
            run.sh = sh
            with self.assertRaises(RuntimeError):
                run.prepare_sitl()
            self.assertFalse(run.started_sitl)
            self.assertFalse(any('stop' in c for c in calls), calls)
            self.assertIn('--fresh', calls[0])

    def test_no_earlier_log_after_a_failed_start(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = make_repo(root, '')
            run = fly.Run(args(repo, root / 'run'))
            old = root / 'old.ulg'
            old.write_bytes(b'an earlier flight')
            run.sh = lambda cmd, **_: subprocess.CompletedProcess(cmd, 1, '', 'sitl_fc start: refused')
            run.sitl_logs = lambda: {old}
            with self.assertRaises(RuntimeError):
                run.prepare_sitl()
            self.assertIsNone(run.sitl_log())   # the earlier log is not taken for this run
            self.assertFalse((root / 'run' / 'fc_log.ulg').exists())


class HitlAfterDeploy(unittest.TestCase):
    def test_an_image_built_by_the_deploy_is_the_one_checked(self):
        """deploy --flash may build first (a new firmware.json): the FC check must compare with that, not the old one."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = make_repo(root, '')
            info = repo / 'recipe' / 'firmware' / 'firmware.json'
            git = 'a' * 40
            info.write_text(json.dumps({'embedded': {'board_id': 1, 'git_hash': git},
                                        'outputs': {'firmware': {'sha256': 'old'}}}))
            run = fly.Run(args(repo, root / 'run', mode='hitl', instance=None))
            run.a.link, run.a.deploy = 'fake', 'flash'
            boards = root / 'boards'
            boards.mkdir()

            def sh(cmd, **_):   # the deploy builds (a new image) and flashes it, as tools/deploy.py --flash does
                info.write_text(json.dumps({'embedded': {'board_id': 1, 'git_hash': git},
                                            'outputs': {'firmware': {'sha256': 'new'}}}))
                (boards / '7.json').write_text(json.dumps({'uid': 7, 'image_sha256': 'new'}))
                return subprocess.CompletedProcess(cmd, 0, json.dumps({'verdict': 'PASS'}) + '\n', '')

            class FakeFC:
                def __init__(self, *_): pass
                def connect(self): return self
                def identity(self): return {'uid': 7, 'armed': False, 'git_hash_prefix': git[:10], 'board_version': 1}
                def get(self, name): return 1
                def logs(self): return {}
                def close(self): pass
            run.sh = sh
            saved = fly.FC, fly.BOARDS
            fly.FC, fly.BOARDS = FakeFC, boards
            try:
                ready = run.prepare_hitl()
            finally:
                fly.FC, fly.BOARDS = saved
            self.assertEqual(ready['board_record']['image_sha256'], 'new')


if __name__ == '__main__':
    unittest.main(verbosity=2)
