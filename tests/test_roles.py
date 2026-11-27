#!/usr/bin/env python3
"""Offline checks of the recipe and board roles (tools/deploy.py role_gate, tools/recipe.py role_problems): which recipe
goes onto which board, and the person's --flight. No flight controller is used.

    <python with pymavlink> -B tests/test_roles.py
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import deploy  # noqa: E402
import recipe as R  # noqa: E402


class FakeRecipe:
    def __init__(self, role, hitl):
        self.params = {'role': role}
        self._hitl = hitl

    def managed(self):
        return {} if self._hitl is None else {'SYS_HITL': (self._hitl, 'set')}

    role_problems = R.Recipe.role_problems
    ROLES = R.Recipe.ROLES


def gate(role, hitl, board, flight=False):
    """None when the deploy may go on, else the error."""
    with tempfile.TemporaryDirectory() as d:
        deploy.BOARDS = Path(d)
        if board:
            (Path(d) / '7.role.json').write_text(json.dumps({'role': board}))
        steps = []
        fake = types.SimpleNamespace(recipe=FakeRecipe(role, hitl), a=types.SimpleNamespace(flight=flight),
                                     step=lambda *x, **k: steps.append((x, k)))
        try:
            deploy.Deploy.role_gate(fake, {'uid': 7})
            return None
        except RuntimeError as e:
            return str(e)


class Roles(unittest.TestCase):
    def test_allowed(self):
        self.assertIsNone(gate('hitl', 1, 'hitl'))
        self.assertIsNone(gate('bench', 1, 'hitl'))
        self.assertIsNone(gate('bench', 1, 'aircraft'))
        self.assertIsNone(gate('flight', None, 'aircraft', flight=True))

    def test_refused(self):
        self.assertIn('no role', gate('hitl', 1, None))
        self.assertIn('does not go onto', gate('hitl', 1, 'aircraft'))        # simulated faults never on an aircraft
        self.assertIn('does not go onto', gate('flight', None, 'hitl', True))  # a bench board never flies
        self.assertIn('--flight', gate('flight', None, 'aircraft'))            # the person's flag
        self.assertIn('SYS_HITL', gate('flight', 1, 'aircraft', True))         # a flight recipe in HITL
        self.assertIn('SYS_HITL', gate('hitl', None, 'hitl'))                  # a HITL recipe without SYS_HITL 1
        self.assertIn('"role"', gate(None, 1, 'hitl'))                         # no role stated


if __name__ == '__main__':
    unittest.main(verbosity=2)
