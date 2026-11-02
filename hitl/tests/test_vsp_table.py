#!/usr/bin/env python3
"""aircraft/vsp/run_table.py without OpenVSP: reading a .stab file, the importer's case order, the script it writes."""
import importlib.util
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('vsp_table', ROOT / 'aircraft/vsp/run_table.py')
vsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vsp)

GROUPS = ['ailR', 'ailL', 'ele', 'rud']


def stab_case(mach, alpha, beta, cl, cm):
    """One case as VSPAERO 7.2 writes it: flow block, perturbation rows, then the derivative table."""
    rows = []
    for k, name in enumerate(vsp.COEFFS):
        base = {'CL': cl, 'CFz': cl, 'CMm': cm, 'CMy': cm}.get(name, 0.001 * (k + 1))
        rows.append(f'{name:<6} ' + ' '.join(f'{base + 0.01 * j:12.7f}' for j in range(12)))
    return f'''*******************************************************************

# Name                   Value      Units
Sref_                   0.2380000 Lunit^2
Mach_                   {mach:.7f} no_unit
AoA_                    {alpha:.7f} deg
Beta_                   {beta:.7f} deg

#
Case                   Delta    Units         CFx          CFy
Base_Aero              +0.000 n/a          0.0267190    0.0000007
ailR                   +0.100 deg          0.0267312    0.0000135
#
Coef          Total        Alpha        Beta          p            q            r           Mach         U        ConGrp_1     ConGrp_2     ConGrp_3     ConGrp_4
#              -           per          per          per          per          per          per          per          per          per          per          per
{chr(10).join(rows)}
#
# Result                 Value      Units
SM                      0.2856516 no_unit
'''


class StabFile(unittest.TestCase):
    def test_every_case_and_column(self):
        text = stab_case(0.05, 0.0, 0.0, 0.16, -0.065) + stab_case(0.05, 5.0, 0.0, 0.59, -0.187)
        cases = vsp.parse_stab(text, GROUPS)
        self.assertEqual(len(cases), 2)
        self.assertEqual((cases[1]['mach'], cases[1]['alpha_deg'], cases[1]['beta_deg']), (0.05, 5.0, 0.0))
        self.assertEqual(len(cases[0]['rows']['CMm']), 12)
        self.assertAlmostEqual(cases[0]['rows']['CL'][0], 0.16)
        self.assertAlmostEqual(cases[0]['rows']['CL'][11], 0.27)  # the fourth control group

    def test_importer_order_and_summary(self):
        config = {'mach': [0.05], 'alpha_deg': [0, 5], 'beta_deg': [0], 'groups': [{'name': g} for g in GROUPS],
                  'reference': {'xcg': 0.05, 'cref': 0.2}}
        text = stab_case(0.05, 5.0, 0.0, 0.59, -0.187) + stab_case(0.05, 0.0, 0.0, 0.16, -0.065)
        data, suffixes = vsp.table(vsp.parse_stab(text, GROUPS), config)
        self.assertEqual(data['aoa'], [0.0, 5.0])  # beta outer, then Mach, then alpha, as data_out
        self.assertEqual(suffixes[-4:], ['dailR', 'dailL', 'dele', 'drud'])
        self.assertAlmostEqual(data['CMm']['dele'][0], -0.065 + 0.10)
        rows = vsp.summary(data, config)
        cla = (0.59 - 0.16) / math.radians(5)
        cma = (-0.187 + 0.065) / math.radians(5)
        self.assertAlmostEqual(rows['CL_alpha_per_rad'], cla)
        self.assertAlmostEqual(rows['neutral_point_x_m'], 0.05 - cma / cla * 0.2)

    def test_a_missing_case_stops(self):
        config = {'mach': [0.05], 'alpha_deg': [0, 5], 'beta_deg': [0], 'groups': [{'name': g} for g in GROUPS]}
        with self.assertRaises(SystemExit):
            vsp.table(vsp.parse_stab(stab_case(0.05, 0.0, 0.0, 0.16, -0.065), GROUPS), config)


class WindAxes(unittest.TestCase):
    def test_body_moments_rotate_with_alpha_and_beta(self):
        data = {'aoa': [10.0, 0.0], 'beta': [0.0, 5.0],
                'CMl': {'base': [0.1, 0.0], 'dp': [-0.4, -0.4]}, 'CMm': {'base': [-0.05, 0.2], 'dp': [0.0, 0.0]},
                'CMn': {'base': [0.02, 0.0], 'dp': [-0.01, -0.01]}}
        wind = vsp.wind_moments(data)
        a = math.radians(10.0)
        self.assertAlmostEqual(wind['CMl']['base'][0], math.cos(a) * 0.1 + math.sin(a) * 0.02)
        self.assertAlmostEqual(wind['CMn']['base'][0], -math.sin(a) * 0.1 + math.cos(a) * 0.02)
        self.assertAlmostEqual(wind['CMm']['base'][0], -0.05)
        self.assertAlmostEqual(wind['CMl']['dp'][0], math.cos(a) * -0.4 + math.sin(a) * -0.01)
        b = math.radians(5.0)  # at alpha 0 a sideslip mixes roll and pitch
        self.assertAlmostEqual(wind['CMl']['base'][1], math.sin(b) * 0.2)
        self.assertAlmostEqual(wind['CMm']['base'][1], math.cos(b) * 0.2)
        self.assertEqual(data['CMl']['base'][0], 0.1)  # the input is left as it was


class Script(unittest.TestCase):
    def test_groups_left_side_and_wake(self):
        config = vsp.json.loads((ROOT / 'aircraft/vsp/table.json').read_text())
        text = vsp.script(config, Path('/tmp/x.vsp3'))
        for group in config['groups']:
            self.assertIn(f'SetVSPAEROControlGroupName("{group["name"]}", g);', text)
        self.assertIn('"_1_Gain"', text)
        self.assertIn(f'SetI("FixedWakeFlag", {1 if config["solver"].get("fixed_wake") else 0});', text)
        self.assertIn(f'BuildSkySurfer({config["tail_incidence_deg"]});', text)
        self.assertIn('SetI("AlphaNpts", 6)', text)


class Grid(unittest.TestCase):
    def test_the_project_grid_is_evenly_spaced(self):
        config = vsp.json.loads((ROOT / 'aircraft/vsp/table.json').read_text())
        self.assertEqual(vsp.uneven(config), [])

    def test_an_uneven_or_unsorted_list_is_refused(self):
        # VSPAERO takes start, end and count: 0 2 5 would be solved at 0 2.5 5
        bad = vsp.uneven({'alpha_deg': [0, 2, 5], 'beta_deg': [5, 0, -5], 'mach': [0.05]})
        self.assertEqual([b.split()[0] for b in bad], ['alpha_deg', 'beta_deg'])

    def test_write_mat_needs_the_same_grid(self):
        full = {'alpha_deg': [-5, 0, 5], 'beta_deg': [-5, 0, 5], 'mach': [0.05, 0.1]}
        self.assertTrue(vsp.same_grid(dict(full), full))
        self.assertFalse(vsp.same_grid(dict(full, alpha_deg=[5, 10], beta_deg=[0], mach=[0.05]), full))

    def test_a_group_named_otherwise_is_left_out(self):
        data = {'mach': [0.05], 'aoa': [0.0], 'beta': [0.0], 'CMm': {'base': [0.1]}}
        self.assertIsNone(vsp.pick(data, 'CMm', 'dele', 0.05, 0, 0))
        self.assertEqual(vsp.pick(data, 'CMm', 'base', 0.05, 0, 0), 0.1)


if __name__ == '__main__':
    unittest.main()
