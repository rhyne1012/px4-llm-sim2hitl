#!/usr/bin/env python3
"""The pure parts of the model tools: what counts as a numeric change, and the AVL joint lint. No MATLAB, no solver."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hitl'))
import model_cycle  # noqa: E402

spec = importlib.util.spec_from_file_location('run_table', ROOT / 'aircraft/avl/run_table.py')
run_table = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_table)

SPLIT_WING = """Title
0.1
0 0 0
0.2 0.2 1.0
0 0 0
SURFACE
Left
4 1 10 1
SECTION
0 -0.5 0 0.2 0
SECTION
0 0 0 0.2 0
SURFACE
Right
4 1 10 1
SECTION
0 0 0 0.2 0
SECTION
0 0.5 0 0.2 0
"""


class GeneratedDifference(unittest.TestCase):
    def folders(self, before, after):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a, b = Path(tmp.name) / 'a', Path(tmp.name) / 'b'
        for root, files in ((a, before), (b, after)):
            (root / 'codegen').mkdir(parents=True)
            for name, text in files.items():
                (root / 'codegen' / name).write_text(text)
        return a, b

    def test_a_comment_is_not_a_change(self):
        a, b = self.folders({'x.c': '/* Model version 1\n generated Monday */\nint a;\n'}, {'x.c': '/* Model version 2\n generated Tuesday */\nint a;\n'})
        d = model_cycle.generated_difference(a, b)
        self.assertEqual(d['code_changed'], [])
        self.assertEqual(d['code_files_with_only_comment_changes'], 1)

    def test_a_number_is_a_change(self):
        a, b = self.folders({'x_data.c': 'double p = 0.05;\n'}, {'x_data.c': 'double p = 0.04;\n'})
        self.assertEqual(model_cycle.generated_difference(a, b)['code_changed'], ['codegen/x_data.c'])

    def test_results_compare_bytes_and_the_manifest_is_ignored(self):
        a, b = self.folders({'r.csv': '1,2\n', 'manifest.json': '{"t": 1}'}, {'r.csv': '1,3\n', 'manifest.json': '{"t": 2}'})
        d = model_cycle.generated_difference(a, b)
        self.assertEqual(d['results_changed'], ['codegen/r.csv'])

    def test_the_generating_checkout_and_matlab_are_not_a_change(self):
        # results/reuse_policy.json and core_build.json carry the checkout path and the MATLAB version
        a, b = self.folders({'policy.json': '{"policy_file": "/home/a/x/.satk/r.json", "libraries": 0}',
                             'build.json': '{"matlab": "26.1", "dt": 0.004}'},
                            {'policy.json': '{"policy_file": "/home/b/y/.satk/r.json", "libraries": 0}',
                             'build.json': '{"matlab": "26.2", "dt": 0.004}'})
        self.assertEqual(model_cycle.generated_difference(a, b)['results_changed'], [])
        a, b = self.folders({'build.json': '{"matlab": "26.1", "dt": 0.004}'}, {'build.json': '{"matlab": "26.1", "dt": 0.002}'})
        self.assertEqual(model_cycle.generated_difference(a, b)['results_changed'], ['codegen/build.json'])

    def test_a_removed_file_is_a_change(self):
        a, b = self.folders({'x.c': 'int a;\n', 'y.c': 'int b;\n'}, {'x.c': 'int a;\n'})
        self.assertEqual(model_cycle.generated_difference(a, b)['code_changed'], ['codegen/y.c'])


class ArraysDifference(unittest.TestCase):
    def test_finds_the_changed_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.npz', Path(tmp) / 'b.npz'
            np.savez(a, x=np.arange(3.0), y=np.ones(2))
            np.savez(b, x=np.arange(3.0), y=np.array([1.0, 1.0 + 1e-15]))
            self.assertEqual(model_cycle.arrays_difference(a, b), {'arrays': 2, 'changed': ['y']})


class AvlJointLint(unittest.TestCase):
    def test_split_wing_without_component_is_found(self):
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(SPLIT_WING)), [('Left', 'Right')])

    def test_one_component_passes(self):
        text = SPLIT_WING.replace('4 1 10 1\n', '4 1 10 1\nCOMPONENT\n1\n')
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(text)), [])

    def test_keywords_count_by_their_first_four_characters(self):
        # AVL reads only the first four characters of a keyword
        short = SPLIT_WING.replace('SURFACE', 'SURF').replace('SECTION', 'SECT')
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(short)), [('Left', 'Right')])
        joined = short.replace('4 1 10 1\n', '4 1 10 1\nCOMP\n1\n')
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(joined)), [])

    def test_translate_and_duplicate_count(self):
        text = """T
0.1
0 0 0
0.2 0.2 1.0
0 0 0
SURFACE
Tail
8 1 10 1
YDUPLICATE
0.0
TRANSLATE
0.55 0 -0.05
SECTION
0 0 0 0.1 0
SECTION
0 0.2 0 0.1 0
SURFACE
Fin
8 1 10 1
TRANSLATE
0.51 0 -0.05
SECTION
0 0 0 0.12 0
SECTION
0 0 0.2 0.1 0
"""
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(text)), [('Tail', 'Fin')])

    def test_apart_surfaces_pass(self):
        text = SPLIT_WING.replace('0 0 0 0.2 0\nSECTION\n0 0.5 0 0.2 0', '0 0.1 0 0.2 0\nSECTION\n0 0.5 0 0.2 0')
        self.assertEqual(run_table.unjoined(run_table.parse_surfaces(text)), [])

    def test_the_project_geometry_is_clean(self):
        text = (ROOT / 'aircraft/avl/SkySurfer_wing2410_NDU.avl').read_text()
        surfaces = run_table.parse_surfaces(text)
        self.assertEqual(len(surfaces), 4)
        self.assertEqual(run_table.unjoined(surfaces), [])


if __name__ == '__main__':
    unittest.main()
