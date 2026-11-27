#!/usr/bin/env python3
"""Generate a fast C core from a JSBSim vehicle folder.

    python3 fastcore/gen.py vehicles/testbird [--out build/fastcore/testbird] [--cc cc] [--native]

The vehicle's own parts are translated from its JSBSim files: aerodynamic functions and tables, flight-control
components, mass and inertia, engine and propeller constants. The shared physics (equations of motion, atmosphere,
interpolation) comes from fastcore/runtime/fastcore.h. The output is <name>_core.c/.h, lib<name>_core.so and
<name>_core.json (the layout of the state, input, environment and output arrays, and what the core leaves out).

Only the JSBSim elements listed in fastcore/README.md are translated. Anything else stops the generator with the file
and the element, so a core never silently differs from its JSBSim definition.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime'


class Unsupported(Exception):
    pass


# --- JSBSim 1.3.3 unit conversions (src/input_output/FGXMLElement.cpp), so values come out exactly as JSBSim stores them
def _units():
    c = {}
    c['M', 'FT'] = 3.2808399
    c['FT', 'M'] = 1.0 / c['M', 'FT']
    c['CM', 'FT'] = 0.032808399
    c['FT', 'CM'] = 1.0 / c['CM', 'FT']
    c['FT', 'IN'] = 12.0
    c['IN', 'FT'] = 1.0 / c['FT', 'IN']
    c['IN', 'M'] = c['IN', 'FT'] * c['FT', 'M']
    c['M', 'IN'] = c['M', 'FT'] * c['FT', 'IN']
    c['CM', 'IN'] = c['CM', 'FT'] * c['FT', 'IN']
    c['M2', 'FT2'] = c['M', 'FT'] * c['M', 'FT']
    c['FT2', 'M2'] = 1.0 / c['M2', 'FT2']
    c['CM2', 'FT2'] = c['CM', 'FT'] * c['CM', 'FT']
    c['M2', 'IN2'] = c['M', 'IN'] * c['M', 'IN']
    c['FT2', 'IN2'] = 144.0
    c['IN2', 'FT2'] = 1.0 / c['FT2', 'IN2']
    c['LBS', 'KG'] = 0.45359237
    c['KG', 'LBS'] = 1.0 / c['LBS', 'KG']
    c['SLUG', 'KG'] = 14.59390
    c['KG', 'SLUG'] = 1.0 / c['SLUG', 'KG']
    c['SLUG', 'LBS'] = c['SLUG', 'KG'] / c['LBS', 'KG']
    c['LBS', 'SLUG'] = 1.0 / c['SLUG', 'LBS']
    c['SLUG*FT2', 'KG*M2'] = 1.35594
    c['KG*M2', 'SLUG*FT2'] = 1.0 / c['SLUG*FT2', 'KG*M2']
    c['RAD', 'DEG'] = 180.0 / math.pi
    c['DEG', 'RAD'] = 1.0 / c['RAD', 'DEG']
    c['RAD/SEC', 'DEG/SEC'] = c['RAD', 'DEG']
    c['DEG/SEC', 'RAD/SEC'] = 1.0 / c['RAD/SEC', 'DEG/SEC']
    c['WATTS', 'HP'] = 0.001341022
    c['HP', 'WATTS'] = 1.0 / c['WATTS', 'HP']
    return c


UNITS = _units()
LBTOSLUG = 1.0 / 32.174049          # FGJSBBase::lbtoslug
RADTODEG = 180.0 / math.pi
NM_TO_FTLB = 1.3558                 # FGBrushLessDCMotor.h NMtoftpound
WATT_PER_RPM_TO_FTLB = 60.0 / (2.0 * math.pi * NM_TO_FTLB)


def num(text, where):
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        raise Unsupported(f'{where}: expected a number, got {text!r} (properties as parameters are not supported)')


def value_to(el, target, where):
    """FGXMLElement::FindElementValueAsNumberConvertTo on an element itself."""
    v = num(el.text, where)
    unit = el.get('unit')
    if unit is None or unit == target:
        return v
    if (unit, target) not in UNITS:
        raise Unsupported(f'{where}: no JSBSim conversion from {unit} to {target}')
    return v * UNITS[unit, target]


def child_to(parent, tag, target, where, default=None):
    el = parent.find(tag)
    if el is None:
        if default is None:
            raise Unsupported(f'{where}: <{tag}> is missing')
        return default
    return value_to(el, target, f'{where}/<{tag}>')


def triplet_to(el, target, where):
    """FGXMLElement::FindElementTripletConvertTo: x|roll, y|pitch, z|yaw, the unit of the element applies to all."""
    unit = el.get('unit')
    out = []
    for names in (('x', 'roll'), ('y', 'pitch'), ('z', 'yaw')):
        c = next((el.find(n) for n in names if el.find(n) is not None), None)
        v = 0.0 if c is None else num(c.text, f'{where}/<{names[0]}>')
        cu = (c.get('unit') if c is not None else None) or unit
        if cu is not None and cu != target:
            if (cu, target) not in UNITS:
                raise Unsupported(f'{where}: no JSBSim conversion from {cu} to {target}')
            v *= UNITS[cu, target]
        out.append(v)
    return out


def table_rows(text):
    return [[float(t) for t in line.split()] for line in text.strip().splitlines() if line.strip()]


def cname(prop):
    return 'p_' + re.sub(r'[^A-Za-z0-9]', '_', prop)


def cnum(v):
    if v == math.inf:
        return 'HUGE_VAL'
    return repr(float(v))


# --- the vehicle -----------------------------------------------------------------------------------------------------

class Vehicle:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.name = self.folder.name
        self.main = self.folder / f'{self.name}.xml'
        self.files = [self.main]
        self.root = self.parse(self.main)
        self.notes = []

    def parse(self, path):
        if not path.exists():
            raise Unsupported(f'{path}: missing')
        return ET.parse(path).getroot()

    def include(self, sub, name):
        path = self.folder / sub / (name if name.endswith('.xml') else name + '.xml')
        self.files.append(path)
        return self.parse(path)


class Gen:
    """Collects C declarations and statements for one vehicle."""

    def __init__(self, v):
        self.v = v
        self.where = str(v.main.relative_to(v.folder.parent))
        self.tables = []            # C definitions of tables
        self.props = {}             # JSBSim property -> C expression (JSBSim units), for what is available
        self.inputs = []            # FCS input properties, in input order
        self.held = []              # (property, C var) held from the FCS update into the continuous part
        self.fcs_states = []        # names of discrete FCS states
        self.fcs_code = []
        self.aero_code = []
        self.aero_funcs = []        # (property, C var) of every aero function, for the outputs
        self.contacts = []
        self.engines = []

    # -- expressions ---------------------------------------------------------------------------------------------------
    def prop(self, text, where):
        p = text.strip()
        sign = ''
        if p.startswith('-'):
            sign, p = '-', p[1:]
        if p not in self.props:
            raise Unsupported(f'{where}: property {p} is not available in the fast core (supported: fastcore/README.md)')
        return f'({sign}{self.props[p]})'

    def table(self, el, where, keys=None):
        """A <table>: 1D (row) or 2D (row, column). keys: C expressions for the independent variables when the table
        has no <independentVar> (propeller tables)."""
        if keys is None:
            ivs = el.findall('independentVar')
            byk = {iv.get('lookup', 'row'): self.prop(iv.text, where) for iv in ivs}
            if 'table' in byk or len(ivs) > 2:
                raise Unsupported(f'{where}: 3D tables are not supported')
            keys = [byk.get('row')] + ([byk['column']] if 'column' in byk else [])
            if keys[0] is None:
                raise Unsupported(f'{where}: table without a row variable')
        datas = el.findall('tableData')
        if len(datas) != 1:
            raise Unsupported(f'{where}: table with {len(datas)} <tableData> blocks')
        rows = table_rows(datas[0].text)
        i = len(self.tables)
        if len(keys) == 1:
            if any(len(r) != 2 for r in rows):
                raise Unsupported(f'{where}: 1D table rows must have two numbers')
            xs, ys = [r[0] for r in rows], [r[1] for r in rows]
            self.check_increasing(xs, where)
            self.tables.append(f'static const double T{i}x[{len(xs)}] = {{{", ".join(map(cnum, xs))}}};\n'
                               f'static const double T{i}y[{len(ys)}] = {{{", ".join(map(cnum, ys))}}};')
            return f'fc_table1({keys[0]}, T{i}x, T{i}y, {len(xs)})'
        cols = rows[0]
        body = rows[1:]
        if any(len(r) != len(cols) + 1 for r in body):
            raise Unsupported(f'{where}: 2D table rows must have {len(cols) + 1} numbers')
        rk = [r[0] for r in body]
        self.check_increasing(rk, where)
        self.check_increasing(cols, where)
        data = [v for r in body for v in r[1:]]
        self.tables.append(f'static const double T{i}r[{len(rk)}] = {{{", ".join(map(cnum, rk))}}};\n'
                           f'static const double T{i}c[{len(cols)}] = {{{", ".join(map(cnum, cols))}}};\n'
                           f'static const double T{i}d[{len(data)}] = {{{", ".join(map(cnum, data))}}};')
        return f'fc_table2({keys[0]}, {keys[1]}, T{i}r, {len(rk)}, T{i}c, {len(cols)}, T{i}d)'

    @staticmethod
    def check_increasing(xs, where):
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise Unsupported(f'{where}: table breakpoints must increase')

    UNARY = {'abs': 'fabs', 'sqrt': 'sqrt', 'sin': 'sin', 'cos': 'cos', 'tan': 'tan', 'asin': 'asin', 'acos': 'acos',
             'atan': 'atan', 'exp': 'exp', 'ln': 'log', 'log10': 'log10', 'integer': 'trunc'}
    COMPARE = {'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>=', 'eq': '==', 'nq': '!='}

    def expr(self, el, where):
        """One element of a JSBSim <function> as a C expression (FGFunction semantics)."""
        tag = el.tag
        here = f'{where}/<{tag}>'
        kids = [k for k in el if k.tag != 'description']
        args = lambda: [self.expr(k, here) for k in kids]  # noqa: E731
        if tag in ('value', 'v'):
            return cnum(num(el.text, here))
        if tag in ('property', 'p'):
            return self.prop(el.text, here)
        if tag in ('table', 't'):
            return self.table(el, here)
        if tag == 'product':
            return '(' + ' * '.join(args()) + ')'
        if tag == 'sum':
            return '(' + ' + '.join(args()) + ')'
        if tag == 'difference':
            a = args()
            return '(' + ' - '.join(a) + ')'
        if tag == 'quotient':
            a = args()
            if len(a) != 2:
                raise Unsupported(f'{here}: needs two arguments')
            return f'fc_div({a[0]}, {a[1]})'
        if tag == 'pow':
            a = args()
            if len(a) != 2:
                raise Unsupported(f'{here}: needs two arguments')
            return f'pow({a[0]}, {a[1]})'
        if tag == 'atan2':
            a = args()
            return f'atan2({a[0]}, {a[1]})'
        if tag in self.UNARY:
            a = args()
            if len(a) != 1:
                raise Unsupported(f'{here}: needs one argument')
            return f'{self.UNARY[tag]}({a[0]})'
        if tag in ('min', 'max'):
            a = args()
            out = a[0]
            for b in a[1:]:
                out = f'f{tag}({out}, {b})'
            return out
        if tag == 'avg':
            a = args()
            return '((' + ' + '.join(a) + f') / {len(a)}.0)'
        if tag == 'fraction':
            a = args()
            return f'({a[0]} - trunc({a[0]}))'
        if tag == 'mod':
            a = args()
            return f'fmod({a[0]}, {a[1]})'
        if tag in self.COMPARE:
            a = args()
            return f'(({a[0]}) {self.COMPARE[tag]} ({a[1]}) ? 1.0 : 0.0)'
        if tag in ('and', 'or'):
            op = ' && ' if tag == 'and' else ' || '
            return '((' + op.join(f'({x}) != 0.0' for x in args()) + ') ? 1.0 : 0.0)'
        if tag == 'not':
            return f'(({args()[0]}) == 0.0 ? 1.0 : 0.0)'
        if tag == 'ifthen':
            a = args()
            if len(a) != 3:
                raise Unsupported(f'{here}: needs three arguments')
            return f'(({a[0]}) != 0.0 ? ({a[1]}) : ({a[2]}))'
        raise Unsupported(f'{here}: function element <{tag}> is not supported')

    def function(self, el, where):
        kids = [k for k in el if k.tag != 'description']
        if len(kids) != 1:
            raise Unsupported(f'{where}: a <function> needs exactly one element')
        return self.expr(kids[0], where)

    # -- vehicle parts -------------------------------------------------------------------------------------------------
    def metrics(self):
        m = self.v.root.find('metrics')
        w = f'{self.where}/<metrics>'
        if m is None:
            raise Unsupported(f'{w}: missing')
        self.Sw = child_to(m, 'wingarea', 'FT2', w)
        self.bw = child_to(m, 'wingspan', 'FT', w)
        self.cbar = child_to(m, 'chord', 'FT', w)
        self.iw = child_to(m, 'wing_incidence', 'RAD', w, 0.0)
        self.Sh = child_to(m, 'htailarea', 'FT2', w, 0.0)
        self.lh = child_to(m, 'htailarm', 'FT', w, 0.0)
        self.Sv = child_to(m, 'vtailarea', 'FT2', w, 0.0)
        self.lv = child_to(m, 'vtailarm', 'FT', w, 0.0)
        self.rp_in = None
        for loc in m.findall('location'):
            if loc.get('name') == 'AERORP':
                self.rp_in = triplet_to(loc, 'IN', f'{w}/<location AERORP>')
        if self.rp_in is None:
            raise Unsupported(f'{w}: AERORP location is missing')
        for tag in ('aero_ref_pt_shift_x',):
            if m.find(tag) is not None:
                raise Unsupported(f'{w}: <{tag}> is not supported')

    def mass(self):
        mb = self.v.root.find('mass_balance')
        w = f'{self.where}/<mass_balance>'
        if mb is None:
            raise Unsupported(f'{w}: missing')
        if mb.findall('pointmass'):
            raise Unsupported(f'{w}: <pointmass> is not supported yet')
        if self.v.root.find('propulsion/tank') is not None:
            raise Unsupported(f'{w}: fuel tanks are not supported (mass would change)')
        g = {k: child_to(mb, k, 'SLUG*FT2', w, 0.0) for k in ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz')}
        if mb.get('negated_crossproduct_inertia') == 'false':
            J = [[g['ixx'], g['ixy'], -g['ixz']], [g['ixy'], g['iyy'], g['iyz']], [-g['ixz'], g['iyz'], g['izz']]]
        else:
            J = [[g['ixx'], -g['ixy'], g['ixz']], [-g['ixy'], g['iyy'], -g['iyz']], [g['ixz'], -g['iyz'], g['izz']]]
        self.J_slugft2 = J
        self.weight_lbs = child_to(mb, 'emptywt', 'LBS', w)
        self.mass_slug = LBTOSLUG * self.weight_lbs
        cg = None
        for loc in mb.findall('location'):
            if loc.get('name') == 'CG':
                cg = triplet_to(loc, 'IN', f'{w}/<location CG>')
        if cg is None:
            raise Unsupported(f'{w}: CG location is missing')
        self.cg_in = cg

    def to_body_ft(self, r_in):
        """FGMassBalance::StructuralToBody: from the CG, x forward, z down, in ft."""
        d = [r_in[i] - self.cg_in[i] for i in range(3)]
        return [-d[0] / 12.0, d[1] / 12.0, -d[2] / 12.0]

    def ground(self):
        gr = self.v.root.find('ground_reactions')
        if gr is None:
            return
        for c in gr.findall('contact'):
            loc = c.find('location')
            self.contacts.append((c.get('name', '?'), self.to_body_ft(triplet_to(loc, 'IN', f'{self.where}/<contact>'))))
        self.v.notes.append('ground reactions are not modelled: the core is for flight; outputs give the height of the '
                            'lowest contact point above the ground so a training loop can end an episode on contact')

    def propulsion(self):
        pr = self.v.root.find('propulsion')
        if pr is None:
            return
        for e_i, eng in enumerate(pr.findall('engine')):
            w = f'{self.where}/<propulsion>/<engine {e_i}>'
            edoc = self.v.include('Engines', eng.get('file'))
            if edoc.tag != 'brushless_dc_motor':
                raise Unsupported(f'{w}: engine type <{edoc.tag}> is not supported (brushless_dc_motor is)')
            ew = f'Engines/{eng.get("file")}.xml'
            motor = dict(maxv=child_to(edoc, 'maxvolts', 'VOLTS', ew), kv=num(edoc.find('velocityconstant').text, ew),
                         r=child_to(edoc, 'coilresistance', 'OHMS', ew), i0=child_to(edoc, 'noloadcurrent', 'AMPERES', ew))
            th = eng.find('thruster')
            tdoc = self.v.include('Engines', th.get('file'))
            tw = f'Engines/{th.get("file")}.xml'
            if tdoc.tag != 'propeller':
                raise Unsupported(f'{tw}: thruster <{tdoc.tag}> is not supported (propeller is)')
            pitch = [tdoc.find(t) for t in ('minpitch', 'maxpitch')]
            if any(e is not None for e in pitch) and (None in pitch or num(pitch[0].text, tw) != num(pitch[1].text, tw)):
                raise Unsupported(f'{tw}: variable-pitch propellers are not supported')
            if tdoc.find('constspeed') is not None and num(tdoc.find('constspeed').text, tw) != 0.0:
                raise Unsupported(f'{tw}: constant-speed propellers are not supported')
            if tdoc.find('gearratio') is not None and num(tdoc.find('gearratio').text, tw) != 1.0:
                raise Unsupported(f'{tw}: <gearratio> other than 1 is not supported yet')
            for tag in ('table',):
                for t in tdoc.findall(tag):
                    if t.get('name') not in ('C_THRUST', 'C_POWER', 'CT_RPM_FACTOR', 'CP_RPM_FACTOR'):
                        raise Unsupported(f'{tw}: propeller table {t.get("name")} is not supported')
            for tag in ('ct_factor', 'cp_factor'):
                if tdoc.find(tag) is not None:
                    raise Unsupported(f'{tw}: <{tag}> is not supported yet')
            ixx = max(child_to(tdoc, 'ixx', 'SLUG*FT2', tw), 1e-06)
            dia = max(child_to(tdoc, 'diameter', 'FT', tw), 0.001)
            sense_mult = -1.0 if tdoc.get('version') and float(tdoc.get('version')) > 1.0 else 1.0
            sense_el = th.find('sense')
            sense = 1.0 if sense_el is None or num(sense_el.text, w) >= 0.0 else -1.0
            pf = th.find('p_factor')
            if pf is not None and num(pf.text, w) > 0.0001:
                raise Unsupported(f'{w}: <p_factor> is not supported yet')
            loc = th.find('location')
            if loc is None:
                raise Unsupported(f'{w}: thruster location is missing')
            if th.find('pointing') is not None:
                raise Unsupported(f'{w}: <pointing> is not supported')
            orient = triplet_to(th.find('orient'), 'RAD', w) if th.find('orient') is not None else [0.0, 0.0, 0.0]
            r, p, y = orient
            cp, sp, cr, sr, cy, sy = math.cos(p), math.sin(p), math.cos(r), math.sin(r), math.cos(y), math.sin(y)
            mT = [[cp * cy, sr * sp * cy - cr * sy, cr * cy * sp + sr * sy],
                  [cp * sy, sr * sp * sy + cr * cy, cr * sy * sp - sr * cy],
                  [-sp, sr * cp, cr * cp]]  # FGForce::UpdateCustomTransformMatrix
            tabs = {t.get('name'): t for t in tdoc.findall('table')}
            ct = self.table(tabs['C_THRUST'], tw, keys=['J'])
            cpw = self.table(tabs['C_POWER'], tw, keys=['J'])
            # FGPropeller: optional Reynolds-number corrections indexed by the propeller RPM
            if 'CT_RPM_FACTOR' in tabs:
                ct = f'({ct} * {self.table(tabs["CT_RPM_FACTOR"], tw, keys=["RPM"])})'
            if 'CP_RPM_FACTOR' in tabs:
                cpw = f'({cpw} * {self.table(tabs["CP_RPM_FACTOR"], tw, keys=["RPM"])})'
            self.engines.append(dict(motor=motor, ixx=ixx, dia=dia, sense=sense, sense_mult=sense_mult, mT=mT,
                                     r=self.to_body_ft(triplet_to(loc, 'IN', w)), ct=ct, cp=cpw,
                                     engine_file=ew, thruster_file=tw))

    # -- flight control ------------------------------------------------------------------------------------------------
    FCS_BUILTIN_CMDS = ['fcs/aileron-cmd-norm', 'fcs/elevator-cmd-norm', 'fcs/rudder-cmd-norm', 'fcs/flap-cmd-norm',
                        'fcs/speedbrake-cmd-norm', 'fcs/spoiler-cmd-norm', 'fcs/pitch-trim-cmd-norm',
                        'fcs/roll-trim-cmd-norm', 'fcs/yaw-trim-cmd-norm', 'fcs/steer-cmd-norm',
                        'fcs/left-brake-cmd-norm', 'fcs/right-brake-cmd-norm', 'fcs/center-brake-cmd-norm']

    def fcs(self):
        systems = []
        for el in self.v.root:
            if el.tag in ('system', 'flight_control', 'autopilot'):
                if el.get('file'):
                    systems.append((f'Systems/{el.get("file")}.xml', self.v.include('Systems', el.get('file'))))
                else:
                    systems.append((self.where, el))
        n_eng = len(self.engines)
        # inputs: the commands the FCS reads, discovered as they are used; throttle commands always
        self.fcs_vars = {}
        for i in range(n_eng):
            self.add_input(f'fcs/throttle-cmd-norm[{i}]')
            self.fcs_vars[f'fcs/throttle-pos-norm[{i}]'] = f'u[U_THROTTLE_CMD{i}]'
            if i == 0:
                self.fcs_vars['fcs/throttle-pos-norm'] = 'u[U_THROTTLE_CMD0]'
        for where, sysel in systems:
            for prop in sysel.findall('property'):
                raise Unsupported(f'{where}: <property> declarations are not supported yet ({prop.text})')
            for ch in sysel.findall('channel'):
                if ch.get('execrate') not in (None, '1'):
                    raise Unsupported(f'{where}: channel {ch.get("name")}: execrate is not supported')
                for comp in ch:
                    if comp.tag == 'description':
                        continue
                    self.component(comp, f'{where}/<channel {ch.get("name")}>')
            for other in sysel:
                if other.tag not in ('channel', 'property', 'description'):
                    raise Unsupported(f'{where}: <{other.tag}> in a system is not supported')

    def add_input(self, prop):
        if prop not in self.inputs:
            self.inputs.append(prop)
        return self.inputs.index(prop)

    def fcs_in(self, text, where):
        p = text.strip()
        sign = ''
        if p.startswith('-'):
            sign, p = '-', p[1:]
        if p in self.fcs_vars:
            return f'({sign}{self.fcs_vars[p]})'
        if p in self.FCS_BUILTIN_CMDS:
            i = self.add_input(p)
            self.fcs_vars[p] = f'u[{i}]'
            return f'({sign}u[{i}])'
        raise Unsupported(f'{where}: FCS input {p} is neither a command nor written by an earlier component')

    def clip(self, comp, where):
        c = comp.find('clipto')
        if c is None:
            return None
        if c.get('type') == 'cyclic':
            raise Unsupported(f'{where}: cyclic clipping is not supported')
        return num(c.find('min').text, where), num(c.find('max').text, where)

    def component(self, comp, where):
        name = comp.get('name')
        prop = name if '/' in name else 'fcs/' + ''.join('-' if ch.isspace() else ch.lower() for ch in name)
        w = f'{where}/<{comp.tag} {name}>'
        var = cname(prop)
        code = self.fcs_code
        allowed = {'summer': {'bias'}, 'pure_gain': {'gain'}, 'aerosurface_scale': {'domain', 'range', 'zero_centered', 'gain'},
                   'lag_filter': {'c1'}, 'actuator': {'lag', 'rate_limit', 'bias'}}
        if comp.tag not in allowed:
            raise Unsupported(f'{w}: FCS component <{comp.tag}> is not supported')
        for k in comp:
            if k.tag not in allowed[comp.tag] | {'input', 'clipto', 'output', 'description'}:
                raise Unsupported(f'{w}: <{k.tag}> is not supported')
        inputs = [self.fcs_in(i.text, w) for i in comp.findall('input')]
        if comp.tag == 'summer':
            bias = num(comp.find('bias').text, w) if comp.find('bias') is not None else 0.0
            expr = ' + '.join(inputs) + (f' + {cnum(bias)}' if bias else '')
            code.append(f'  double {var} = {expr};')
        elif comp.tag == 'pure_gain':
            gain = num(comp.find('gain').text, w)
            code.append(f'  double {var} = {cnum(gain)} * {inputs[0]};')
        elif comp.tag == 'aerosurface_scale':
            dom = comp.find('domain')
            rng = comp.find('range')
            imin, imax = (num(dom.find('min').text, w), num(dom.find('max').text, w)) if dom is not None else (-1.0, 1.0)
            omin, omax = (num(rng.find('min').text, w), num(rng.find('max').text, w)) if rng is not None else (0.0, 0.0)
            zc = comp.find('zero_centered')
            zc = True if zc is None else zc.text.strip().lower() not in ('0', 'false')
            gain = num(comp.find('gain').text, w) if comp.find('gain') is not None else 1.0
            x = inputs[0]
            if zc:
                e = (f'({x} == 0.0 ? 0.0 : ({x} > 0.0 ? ({x} / {cnum(imax)}) * {cnum(omax)} '
                     f': ({x} / {cnum(imin)}) * {cnum(omin)}))')
            else:
                e = f'({cnum(omin)} + (({x} - {cnum(imin)}) / {cnum(imax - imin)}) * {cnum(omax - omin)})'
            code.append(f'  double {var} = {e} * {cnum(gain)};')
        elif comp.tag == 'lag_filter':
            c1 = num(comp.find('c1').text, w)
            si, so = self.fcs_state(prop, 'in'), self.fcs_state(prop, 'out')
            # FGFilter lag: Tustin, ca = dt c1 / (2 + dt c1), cb = (2 - dt c1) / (2 + dt c1); pass-through when uninitialized
            code.append(f'  double {var};')
            code.append(f'  {{ const double in = {inputs[0]}, d = dt * {cnum(c1)};')
            code.append(f'    {var} = init ? (d / (2.0 + d)) * (in + x[{si}]) + ((2.0 - d) / (2.0 + d)) * x[{so}] : in;')
            code.append(f'    x[{si}] = in; x[{so}] = {var}; }}')
        elif comp.tag == 'actuator':
            for t in ('deadband_width', 'hysteresis_width', 'delay'):
                if comp.find(t) is not None:
                    raise Unsupported(f'{w}: <{t}> is not supported yet')
            lag = comp.find('lag')
            lag = num(lag.text, w) if lag is not None else 0.0
            incr = decr = None
            for rl in comp.findall('rate_limit'):
                v = num(rl.text, w)
                s = rl.get('sense', '')
                if s.startswith('incr'):
                    incr = v
                elif s.startswith('decr'):
                    decr = v
                else:
                    incr = decr = v
            bias = num(comp.find('bias').text, w) if comp.find('bias') is not None else 0.0
            code.append(f'  double {var};')
            code.append(f'  {{ double out = {inputs[0]};')
            if lag:
                li, lo = self.fcs_state(prop, 'lag_in'), self.fcs_state(prop, 'lag_out')
                code.append(f'    {{ const double in = out, d = dt * {cnum(lag)};')
                code.append(f'      if (init) out = (d / (2.0 + d)) * (in + x[{li}]) + x[{lo}] * ((2.0 - d) / (2.0 + d));')
                code.append(f'      x[{li}] = in; x[{lo}] = out; }}')
            if incr is not None or decr is not None:
                ro = self.fcs_state(prop, 'rate_out')
                code.append('    if (init) {')
                code.append(f'      const double delta = out - x[{ro}];')
                if incr:
                    code.append(f'      if (delta > dt * {cnum(incr)}) out = x[{ro}] + {cnum(incr)} * dt;')
                if decr:
                    code.append(f'      if (delta < dt * {cnum(-decr)}) out = x[{ro}] + {cnum(-decr)} * dt;')
                code.append('    }')
                code.append(f'    x[{ro}] = out;')
            if bias:
                code.append(f'    out += {cnum(bias)};')
            cl = self.clip(comp, w)
            if cl:
                code.append(f'    out = fc_clip(out, {cnum(cl[0])}, {cnum(cl[1])});')
                cl = None
            code.append(f'    {var} = out; }}')
            self.write_outputs(comp, prop, var, w, None)
            return
        self.write_outputs(comp, prop, var, w, self.clip(comp, w))

    def fcs_state(self, prop, what):
        self.fcs_states.append(f'{prop}:{what}')
        return f'X_FCS0 + {len(self.fcs_states) - 1}'

    def write_outputs(self, comp, prop, var, where, cl):
        if cl:
            self.fcs_code.append(f'  {var} = fc_clip({var}, {cnum(cl[0])}, {cnum(cl[1])});')
        self.fcs_vars[prop] = var
        for o in comp.findall('output'):
            p = o.text.strip()
            self.fcs_vars[p] = var
            if p.endswith('-pos-rad') and p.startswith('fcs/'):
                self.fcs_vars[p[:-4] + '-deg'] = f'({var} * {cnum(RADTODEG)})'

    # -- aerodynamics --------------------------------------------------------------------------------------------------
    def aero(self):
        ae = self.v.root.find('aerodynamics')
        w = f'{self.where}/<aerodynamics>'
        if ae is None:
            raise Unsupported(f'{w}: missing')
        for t in ('alphalimits', 'hysteresis_limits'):
            if ae.find(t) is not None:
                raise Unsupported(f'{w}: <{t}> is not supported yet')
        code = self.aero_code
        for f in ae.findall('function'):  # pre-functions
            self.aero_function(f, f'{w}/<function {f.get("name")}>')
        axes = {}
        for ax in ae.findall('axis'):
            n = ax.get('name')
            if ax.get('frame') not in (None, 'BODY') or n not in ('LIFT', 'DRAG', 'SIDE', 'X', 'Y', 'Z', 'ROLL', 'PITCH',
                                                                  'YAW'):
                raise Unsupported(f'{w}: axis {n} frame {ax.get("frame")} is not supported')
            axes[n] = ax
        wind = {'LIFT', 'DRAG', 'SIDE'} & axes.keys()
        body = {'X', 'Y', 'Z'} & axes.keys()
        if wind and body:
            raise Unsupported(f'{w}: wind and body force axes mixed')
        self.wind_axes = bool(wind) or not body
        order = ['DRAG', 'SIDE', 'LIFT'] if self.wind_axes else ['X', 'Y', 'Z']
        # lift first, so aero/cl-squared can come from this evaluation's lift (JSBSim uses the previous frame's)
        sums = {}
        eval_order = (['LIFT', 'DRAG', 'SIDE'] if self.wind_axes else order) + ['ROLL', 'PITCH', 'YAW']
        for n in eval_order:
            terms = []
            for f in (axes[n].findall('function') if n in axes else []):
                terms.append(self.aero_function(f, f'{w}/<axis {n}>/<function {f.get("name")}>'))
            sums[n] = ' + '.join(terms) if terms else '0.0'
            code.append(f'  const double ax_{n} = {sums[n]};')
            if n == 'LIFT':
                code.append('  /* aero/cl-squared: FGAerodynamics::Run, from the lift; the reference order uses the stored'
                            ' value */')
                code.append('  const double cl2 = jsb ? x[X_AUX_CLSQ] : (qbar > 1e-9 ? (ax_LIFT / (SW * qbar)) * '
                            '(ax_LIFT / (SW * qbar)) : 0.0);')
                self.props['aero/cl-squared'] = 'cl2'
        if self.wind_axes:
            self.v.notes.append('aero/cl-squared comes from the same evaluation\'s lift (JSBSim: the previous frame\'s)')

    def aero_function(self, f, where):
        name = f.get('name')
        if not name:
            raise Unsupported(f'{where}: unnamed function')
        var = cname(name)
        self.aero_code.append(f'  const double {var} = {self.function(f, where)};')
        self.props[name] = var
        self.aero_funcs.append((name, var))
        return var

    # -- properties available to the functions -------------------------------------------------------------------------
    def base_props(self):
        p = self.props
        p.update({
            'aero/qbar-psf': 'qbar', 'aero/qbarUW-psf': 'qbarUW', 'aero/qbarUV-psf': 'qbarUV',
            'aero/alpha-rad': 'alpha', 'aero/alpha-deg': f'(alpha * {cnum(RADTODEG)})',
            'aero/beta-rad': 'beta', 'aero/beta-deg': f'(beta * {cnum(RADTODEG)})',
            'aero/mag-beta-rad': 'fabs(beta)', 'aero/mag-beta-deg': f'(fabs(beta) * {cnum(RADTODEG)})',
            'aero/alphadot-rad_sec': 'adot', 'aero/alphadot-deg_sec': f'(adot * {cnum(RADTODEG)})',
            'aero/betadot-rad_sec': 'bdot', 'aero/betadot-deg_sec': f'(bdot * {cnum(RADTODEG)})',
            'aero/ci2vel': 'ci2vel', 'aero/bi2vel': 'bi2vel', 'aero/qbar-area': '(SW * qbar)',
            'aero/alpha-wing-rad': '(alpha + IW)',
            'aero/h_b-cg-ft': 'hb_cg', 'aero/h_b-mac-ft': 'hb_mac',
            'velocities/vt-fps': 'Vt', 'velocities/mach': '(Vt / sqrt(1.4 * FC_RDRY * T_R))',
            'velocities/p-aero-rad_sec': 'pa', 'velocities/q-aero-rad_sec': 'qa', 'velocities/r-aero-rad_sec': 'ra',
            'velocities/p-rad_sec': 'x[10]', 'velocities/q-rad_sec': 'x[11]', 'velocities/r-rad_sec': 'x[12]',
            'velocities/u-aero-fps': 'ua', 'velocities/v-aero-fps': 'va', 'velocities/w-aero-fps': 'wa',
            'metrics/Sw-sqft': 'SW', 'metrics/bw-ft': 'BW', 'metrics/cbarw-ft': 'CBAR', 'metrics/iw-rad': 'IW',
            'metrics/iw-deg': f'(IW * {cnum(RADTODEG)})', 'metrics/Sh-sqft': cnum(self.Sh), 'metrics/lh-ft': cnum(self.lh),
            'metrics/Sv-sqft': cnum(self.Sv), 'metrics/lv-ft': cnum(self.lv),
            'metrics/lh-norm': cnum(self.lh / self.cbar if self.cbar else 0.0),
            'metrics/lv-norm': cnum(self.lv / self.bw if self.bw else 0.0),
            'metrics/vbarh-norm': cnum(self.Sh * self.lh / (self.cbar * self.Sw) if self.cbar * self.Sw else 0.0),
            'metrics/vbarv-norm': cnum(self.Sv * self.lv / (self.bw * self.Sw) if self.bw * self.Sw else 0.0),
            'atmosphere/rho-slugs_ft3': 'rho', 'atmosphere/T-R': 'T_R', 'atmosphere/P-psf': 'P_psf',
            'position/h-sl-ft': 'h_ft', 'position/h-agl-ft': 'hagl_ft',
        })
        # FCS values the continuous part reads are held: computed in the FCS update, stored in the state
        self.fcs_refs = {}

    def hold(self, prop):
        """Make an FCS value available to the continuous part through a held state slot."""
        if prop in self.fcs_refs:
            return self.fcs_refs[prop]
        if prop not in self.fcs_vars:
            return None
        i = len(self.held)
        self.held.append((prop, self.fcs_vars[prop]))
        self.fcs_refs[prop] = f'x[X_HELD0 + {i}]'
        return self.fcs_refs[prop]


class LazyProps(dict):
    """Property lookup that pulls FCS values into held slots on first use."""

    def __init__(self, gen, base):
        super().__init__(base)
        self.gen = gen

    def __contains__(self, k):
        return dict.__contains__(self, k) or (k.startswith('fcs/') and self.gen.hold(k) is not None)

    def __getitem__(self, k):
        if dict.__contains__(self, k):
            return dict.__getitem__(self, k)
        h = self.gen.hold(k)
        if h is None:
            raise KeyError(k)
        return h


# --- emit --------------------------------------------------------------------------------------------------------------

def generate(folder, out):
    v = Vehicle(folder)
    g = Gen(v)
    g.metrics()
    g.mass()
    g.ground()
    g.propulsion()
    g.fcs()
    g.base_props()
    g.props = LazyProps(g, g.props)
    g.aero()
    for t in ('external_reactions', 'buoyant_forces'):
        if v.root.find(t) is not None:
            raise Unsupported(f'{g.where}: <{t}> is not supported')
    for e in g.engines:
        g.hold(f'fcs/throttle-pos-norm[{g.engines.index(e)}]')
    return emit(v, g, Path(out))


def emit(v, g, out):
    out.mkdir(parents=True, exist_ok=True)
    N = v.name
    P = N.upper()
    ne = len(g.engines)
    # state layout
    x_names = ['n_m', 'e_m', 'd_m', 'u_mps', 'v_mps', 'w_mps', 'q0', 'q1', 'q2', 'q3', 'p_rps', 'q_rps', 'r_rps']
    x_names += [f'omega_rps[{i}]' for i in range(ne)]
    nc = len(x_names)
    x_held0 = len(x_names)
    x_names += [f'held:{p}' for p, _ in g.held]
    x_fcs0 = len(x_names)
    x_names += [f'fcs:{s}' for s in g.fcs_states]
    x_aux0 = len(x_names)
    x_names += ['aux:udot_mps2', 'aux:vdot_mps2', 'aux:wdot_mps2', 'aux:cl_squared', 'aux:fcs_initialized']
    nx = len(x_names)
    u_names = list(g.inputs)
    env_names = ['wind_n_mps', 'wind_e_mps', 'wind_d_mps', 'gravity_mps2', 'origin_alt_msl_m', 'ground_alt_msl_m']
    y_names = ['fx_N', 'fy_N', 'fz_N', 'mx_Nm', 'my_Nm', 'mz_Nm',
               'aero_fx_N', 'aero_fy_N', 'aero_fz_N', 'aero_mx_Nm', 'aero_my_Nm', 'aero_mz_Nm',
               'specific_force_x_mps2', 'specific_force_y_mps2', 'specific_force_z_mps2',
               'alpha_rad', 'beta_rad', 'airspeed_mps', 'qbar_Pa', 'rho_kgm3', 'alphadot_rps', 'betadot_rps',
               'cl_squared', 'lift_N', 'drag_N', 'side_N', 'agl_cg_m', 'agl_lowest_contact_m']
    for i in range(ne):
        y_names += [f'thrust_N[{i}]', f'rpm[{i}]', f'current_A[{i}]', f'engine_power_W[{i}]', f'advance_ratio[{i}]',
                    f'prop_fx_N[{i}]', f'prop_fy_N[{i}]', f'prop_fz_N[{i}]',
                    f'prop_mx_Nm[{i}]', f'prop_my_Nm[{i}]', f'prop_mz_Nm[{i}]']
    y_names += [f'fn:{p}' for p, _ in g.aero_funcs]
    ny = len(y_names)

    J = g.J_slugft2
    Jsi = [[J[r][c] * 1.3558179483314004 for c in range(3)] for r in range(3)]
    Jinv = inv3(Jsi)
    mass_kg = g.mass_slug * (4.4482216152605 / 0.3048)
    rp = g.to_body_ft(g.rp_in)
    srcs = {str(f.relative_to(v.folder)): hashlib.sha256(f.read_bytes()).hexdigest() for f in v.files}
    gen_hash = hashlib.sha256((Path(__file__).read_bytes() + (RUNTIME / 'fastcore.h').read_bytes())).hexdigest()

    L = []
    a = L.append
    a(f'/* {N}_core.c: generated by px4-llm-sim2hitl fastcore/gen.py from vehicles/{N}. Do not edit.')
    for f, h in srcs.items():
        a(f' *   {f} sha256 {h}')
    a(f' *   generator + runtime sha256 {gen_hash} */')
    a(f'#include "{N}_core.h"')
    a('#include "fastcore.h"')
    a('#include <string.h>')
    a('')
    a(f'#define NX {nx}\n#define NC {nc}\n#define NU {len(u_names)}\n#define NE 6\n#define NY {ny}')
    a(f'#define X_HELD0 {x_held0}\n#define X_FCS0 {x_fcs0}\n#define X_AUX0 {x_aux0}')
    a(f'#define X_AUX_UDOT {x_aux0}\n#define X_AUX_CLSQ {x_aux0 + 3}\n#define X_AUX_INIT {x_aux0 + 4}')
    for i in range(ne):
        a(f'#define U_THROTTLE_CMD{i} {u_names.index(f"fcs/throttle-cmd-norm[{i}]")}')
    a(f'#define SW {cnum(g.Sw)}\n#define BW {cnum(g.bw)}\n#define CBAR {cnum(g.cbar)}\n#define IW {cnum(g.iw)}')
    a(f'#define MASS_KG {cnum(mass_kg)}')
    a(f'static const double JSI[3][3] = {{{", ".join("{" + ", ".join(map(cnum, r)) + "}" for r in Jsi)}}};')
    a(f'static const double JINV[3][3] = {{{", ".join("{" + ", ".join(map(cnum, r)) + "}" for r in Jinv)}}};')
    a(f'static const double RP_FT[3] = {{{", ".join(map(cnum, rp))}}};  /* AERORP from the CG, body axes */')
    a(f'static const double CONTACT_M[{max(1, len(g.contacts))}][3] = {{'
      + ', '.join('{' + ', '.join(cnum(c * 0.3048) for c in r) + '}' for _, r in g.contacts) + '};' if g.contacts
      else 'static const double CONTACT_M[1][3] = {{0, 0, 0}};')
    a(f'#define N_CONTACTS {len(g.contacts) or 1}')
    a('')
    a('\n'.join(g.tables))
    a('')
    # FCS update
    a('/* Flight control, once per step with the inputs u (FGFCS::Run and the components\' Run). Writes the held values')
    a(' * and the components\' own states into x. Before the first step after a reset the components pass their input')
    a(' * through, as JSBSim\'s do on their first frame. */')
    a('static void fcs_update(double *x, const double *u, double dt)')
    a('{')
    a('  const int init = x[X_AUX_INIT] != 0.0;')
    a('  (void)dt; (void)u;')
    L.extend(g.fcs_code)
    for i, (p, var) in enumerate(g.held):
        a(f'  x[X_HELD0 + {i}] = {var};  /* {p} */')
    a('  x[X_AUX_INIT] = 1.0;')
    a('}')
    a('')
    # derivative
    a('/* Continuous dynamics: xd[0..NC) from x and the environment, and the outputs y (may be NULL). uvwdot is the')
    a(' * body acceleration used for alphadot (JSBSim: the previous frame\'s). jsb != 0 reproduces JSBSim\'s order exactly')
    a(' * (aero/cl-squared from the state instead of this evaluation\'s lift); the check uses it. */')
    a('static void deriv(const double *x, const double *uvwdot, const double *env, int jsb, double *xd, double *y)')
    a('{')
    a('  double C[3][3];')
    a('  fc_quat_dcm(x + 6, C);')
    a('  /* FGAuxiliary::Run: air-relative velocity and rates, ft/s */')
    a('  const double wbx = C[0][0] * env[0] + C[1][0] * env[1] + C[2][0] * env[2];')
    a('  const double wby = C[0][1] * env[0] + C[1][1] * env[1] + C[2][1] * env[2];')
    a('  const double wbz = C[0][2] * env[0] + C[1][2] * env[1] + C[2][2] * env[2];')
    a('  const double ua = (x[3] - wbx) / FC_FT, va = (x[4] - wby) / FC_FT, wa = (x[5] - wbz) / FC_FT;')
    a('  const double pa = x[10], qa = x[11], ra = x[12];')
    a('  const double mUW = ua * ua + wa * wa, Vt2 = mUW + va * va, Vt = sqrt(Vt2);')
    a('  double alpha = 0.0, beta = 0.0, adot = 0.0, bdot = 0.0, ca = 1.0, sa = 0.0, cb = 1.0, sb = 0.0;')
    a('  if (Vt > 0.001) {')
    a('    const double sUW = sqrt(mUW);')
    a('    beta = atan2(va, sUW); cb = sUW / Vt; sb = va / Vt;')
    a('    if (mUW >= 1e-6) {')
    a('      const double ud = uvwdot[0] / FC_FT, vd = uvwdot[1] / FC_FT, wd = uvwdot[2] / FC_FT;')
    a('      alpha = atan2(wa, ua); ca = ua / sUW; sa = wa / sUW;')
    a('      const double Vtdot = (ua * ud + va * vd + wa * wd) / Vt;')
    a('      adot = (ua * wd - wa * ud) / mUW;')
    a('      bdot = (vd * Vt - va * Vtdot) / (Vt * sUW);')
    a('    }')
    a('  }')
    a('  const double h_m = env[4] - x[2], h_ft = h_m / FC_FT;')
    a('  double T_R, P_psf, rho;')
    a('  fc_atmosphere(h_ft, &T_R, &P_psf, &rho);')
    a('  const double qbar = 0.5 * rho * Vt2, qbarUW = 0.5 * rho * mUW, qbarUV = 0.5 * rho * (ua * ua + va * va);')
    a('  const double ci2vel = Vt != 0.0 ? CBAR / (2.0 * Vt) : 0.0, bi2vel = Vt != 0.0 ? BW / (2.0 * Vt) : 0.0;')
    a('  const double hagl_ft = (env[4] - env[5] - x[2]) / FC_FT, hb_cg = hagl_ft / BW;')
    a('  const double hb_mac = (hagl_ft - (C[2][0] * RP_FT[0] + C[2][1] * RP_FT[1] + C[2][2] * RP_FT[2])) / BW;')
    a('  (void)qbarUW; (void)qbarUV; (void)hb_cg; (void)hb_mac; (void)P_psf; (void)bdot; (void)ca; (void)sa;')
    a('  /* FGAerodynamics::Run, lbs and ft lbs */')
    L.extend(g.aero_code)
    if g.wind_axes:
        a('  /* wind axes: (-D, S, -L) through Tw2b (FGAuxiliary::UpdateWindMatrices) */')
        a('  const double fD = -ax_DRAG, fS = ax_SIDE, fL = -ax_LIFT;')
        a('  const double Fa[3] = {ca * cb * fD - ca * sb * fS - sa * fL, sb * fD + cb * fS, sa * cb * fD - sa * sb * fS + ca * fL};')
    else:
        a('  const double Fa[3] = {ax_X, ax_Y, ax_Z};')
    a('  const double Ma[3] = {ax_ROLL + RP_FT[1] * Fa[2] - RP_FT[2] * Fa[1],')
    a('                        ax_PITCH + RP_FT[2] * Fa[0] - RP_FT[0] * Fa[2],')
    a('                        ax_YAW + RP_FT[0] * Fa[1] - RP_FT[1] * Fa[0]};')
    a('  double F[3] = {Fa[0], Fa[1], Fa[2]}, M[3] = {Ma[0], Ma[1], Ma[2]};')
    for i, e in enumerate(g.engines):
        m, mT, r = e['motor'], e['mT'], e['r']
        D = e['dia']
        a(f'  /* engine {i}: FGBrushLessDCMotor::Calculate ({e["engine_file"]}) and FGPropeller::Calculate ({e["thruster_file"]}) */')
        a('  {')
        a(f'    static const double mT[3][3] = {{{", ".join("{" + ", ".join(map(cnum, row)) + "}" for row in mT)}}};')
        a(f'    static const double r[3] = {{{", ".join(map(cnum, r))}}};')
        a(f'    const double thr = {g.fcs_refs[f"fcs/throttle-pos-norm[{i}]"]};')
        a(f'    const double RPM = x[{13 + i}] * 60.0 / (2.0 * FC_PI);')
        a(f'    const double V = {cnum(m["maxv"])} * thr;')
        a(f'    const double I = (V - RPM / {cnum(m["kv"])}) / {cnum(m["r"])};')
        a(f'    const double If = RPM > 0.0 ? {cnum(m["i0"])} : (RPM < 0.0 ? {cnum(-m["i0"])} : fc_clip(I, {cnum(-m["i0"])}, {cnum(m["i0"])}));')
        a(f'    const double Tq = (I - If) / {cnum(m["kv"])} * {cnum(WATT_PER_RPM_TO_FTLB)};')
        a('    const double Peng = (2.0 * FC_PI) * fmax(RPM, 0.0001) * Tq / 60.0;')
        a('    const double lx = ua + (qa * r[2] - ra * r[1]), ly = va + (ra * r[0] - pa * r[2]), lz = wa + (pa * r[1] - qa * r[0]);')
        a('    const double Vel = mT[0][0] * lx + mT[1][0] * ly + mT[2][0] * lz;')
        a('    const double RPS = RPM / 60.0;')
        a(f'    const double J = RPS > 0.01 ? Vel / ({cnum(D)} * RPS) : Vel / {cnum(D)};')
        a('    const double lrps = RPS < 0.01 ? 0.01 : RPS;')
        a(f'    const double Preq = {e["cp"]} * lrps * lrps * lrps * {cnum(D ** 5)} * rho;')
        a('    const double Pav = Peng - Preq;')
        a(f'    const double thrust = {e["ct"]} * RPS * RPS * {cnum(D ** 4)} * rho;')
        a('    const double om = RPS * 2.0 * FC_PI;')
        a(f'    const double tx = {cnum(-e["sense"])} * Peng / fmax(0.01, om);')
        a(f'    const double hx = {cnum(e["ixx"])} * om * {cnum(e["sense"] * e["sense_mult"])};')
        a(f'    if (xd) xd[{13 + i}] = (om > 0.01 ? Pav / om : Pav) / {cnum(e["ixx"])};')
        a('    const double Fb[3] = {mT[0][0] * thrust, mT[1][0] * thrust, mT[2][0] * thrust};')
        a('    const double Hb[3] = {mT[0][0] * hx, mT[1][0] * hx, mT[2][0] * hx};')
        a('    const double Tb[3] = {mT[0][0] * tx, mT[1][0] * tx, mT[2][0] * tx};')
        a('    const double Mp[3] = {qa * Hb[2] - ra * Hb[1] + Tb[0] + r[1] * Fb[2] - r[2] * Fb[1],')
        a('                          ra * Hb[0] - pa * Hb[2] + Tb[1] + r[2] * Fb[0] - r[0] * Fb[2],')
        a('                          pa * Hb[1] - qa * Hb[0] + Tb[2] + r[0] * Fb[1] - r[1] * Fb[0]};')
        a('    F[0] += Fb[0]; F[1] += Fb[1]; F[2] += Fb[2]; M[0] += Mp[0]; M[1] += Mp[1]; M[2] += Mp[2];')
        base = y_names.index(f'thrust_N[{i}]')
        a(f'    if (y) {{ y[{base}] = thrust * FC_LBF; y[{base + 1}] = RPM; y[{base + 2}] = I; y[{base + 3}] = Peng * FC_FTLBF;')
        a(f'      y[{base + 4}] = J; for (int k = 0; k < 3; ++k) {{ y[{base + 5} + k] = Fb[k] * FC_LBF; y[{base + 8} + k] = Mp[k] * FC_FTLBF; }} }}')
        a('  }')
    a('  /* equations of motion, flat Earth, SI */')
    a('  const double f[3] = {F[0] * FC_LBF / MASS_KG, F[1] * FC_LBF / MASS_KG, F[2] * FC_LBF / MASS_KG};')
    a('  const double mo[3] = {M[0] * FC_FTLBF, M[1] * FC_FTLBF, M[2] * FC_FTLBF};')
    a('  const double p = x[10], q = x[11], r = x[12], u = x[3], v = x[4], w = x[5], g = env[3];')
    a('  const double ud = f[0] + C[2][0] * g - (q * w - r * v);')
    a('  const double vd = f[1] + C[2][1] * g - (r * u - p * w);')
    a('  const double wd = f[2] + C[2][2] * g - (p * v - q * u);')
    a('  const double Jw[3] = {JSI[0][0] * p + JSI[0][1] * q + JSI[0][2] * r, JSI[1][0] * p + JSI[1][1] * q + JSI[1][2] * r,')
    a('                        JSI[2][0] * p + JSI[2][1] * q + JSI[2][2] * r};')
    a('  const double e0 = mo[0] - (q * Jw[2] - r * Jw[1]), e1 = mo[1] - (r * Jw[0] - p * Jw[2]), e2 = mo[2] - (p * Jw[1] - q * Jw[0]);')
    a('  if (xd) {')
    a('    xd[0] = C[0][0] * u + C[0][1] * v + C[0][2] * w;')
    a('    xd[1] = C[1][0] * u + C[1][1] * v + C[1][2] * w;')
    a('    xd[2] = C[2][0] * u + C[2][1] * v + C[2][2] * w;')
    a('    xd[3] = ud; xd[4] = vd; xd[5] = wd;')
    a('    xd[6] = 0.5 * (-x[7] * p - x[8] * q - x[9] * r);')
    a('    xd[7] = 0.5 * (x[6] * p + x[8] * r - x[9] * q);')
    a('    xd[8] = 0.5 * (x[6] * q - x[7] * r + x[9] * p);')
    a('    xd[9] = 0.5 * (x[6] * r + x[7] * q - x[8] * p);')
    a('    xd[10] = JINV[0][0] * e0 + JINV[0][1] * e1 + JINV[0][2] * e2;')
    a('    xd[11] = JINV[1][0] * e0 + JINV[1][1] * e1 + JINV[1][2] * e2;')
    a('    xd[12] = JINV[2][0] * e0 + JINV[2][1] * e1 + JINV[2][2] * e2;')
    a('  }')
    a('  if (y) {')
    a('    double lowest = 1e300;')
    a('    for (int k = 0; k < N_CONTACTS; ++k) {')
    a('      const double hz = C[2][0] * CONTACT_M[k][0] + C[2][1] * CONTACT_M[k][1] + C[2][2] * CONTACT_M[k][2];')
    a('      if (-hz < lowest) lowest = -hz;')
    a('    }')
    yi = {n: i for i, n in enumerate(y_names)}
    a(f'    y[{yi["fx_N"]}] = F[0] * FC_LBF; y[{yi["fy_N"]}] = F[1] * FC_LBF; y[{yi["fz_N"]}] = F[2] * FC_LBF;')
    a(f'    y[{yi["mx_Nm"]}] = mo[0]; y[{yi["my_Nm"]}] = mo[1]; y[{yi["mz_Nm"]}] = mo[2];')
    a(f'    for (int k = 0; k < 3; ++k) {{ y[{yi["aero_fx_N"]} + k] = Fa[k] * FC_LBF; y[{yi["aero_mx_Nm"]} + k] = Ma[k] * FC_FTLBF; '
      f'y[{yi["specific_force_x_mps2"]} + k] = f[k]; }}')
    a(f'    y[{yi["alpha_rad"]}] = alpha; y[{yi["beta_rad"]}] = beta; y[{yi["airspeed_mps"]}] = Vt * FC_FT;')
    a(f'    y[{yi["qbar_Pa"]}] = qbar * (FC_LBF / (FC_FT * FC_FT)); y[{yi["rho_kgm3"]}] = rho * (FC_SLUG / (FC_FT * FC_FT * FC_FT));')
    a(f'    y[{yi["alphadot_rps"]}] = adot; y[{yi["betadot_rps"]}] = bdot;')
    if g.wind_axes:
        a(f'    y[{yi["cl_squared"]}] = cl2; y[{yi["lift_N"]}] = ax_LIFT * FC_LBF; y[{yi["drag_N"]}] = ax_DRAG * FC_LBF; '
          f'y[{yi["side_N"]}] = ax_SIDE * FC_LBF;')
    a(f'    y[{yi["agl_cg_m"]}] = hagl_ft * FC_FT; y[{yi["agl_lowest_contact_m"]}] = hagl_ft * FC_FT + lowest;')
    for p, var in g.aero_funcs:
        a(f'    y[{yi["fn:" + p]}] = {var};')
    a('  }')
    a('}')
    a('')
    a(f'void {N}_reset(int n, double *x, const double *u)')
    a('{')
    a('  for (int i = 0; i < n; ++i) {')
    a('    double *xi = x + (size_t)i * NX;')
    a('    fc_quat_normalize(xi + 6);')
    a('    memset(xi + X_FCS0, 0, sizeof(double) * (NX - X_FCS0));')
    a('    fcs_update(xi, u + (size_t)i * NU, 0.0);  /* like JSBSim\'s RunIC: components pass their input through */')
    a('  }')
    a('}')
    a('')
    a(f'void {N}_step(int n, double *x, const double *u, const double *env, double dt, int k, double *y)')
    a('{')
    a('  for (int i = 0; i < n; ++i) {')
    a('    double *xi = x + (size_t)i * NX;')
    a('    const double *ui = u + (size_t)i * NU, *ei = env + (size_t)i * NE;')
    a('    for (int s = 0; s < k; ++s) {')
    a('      double k1[NC], k2[NC], k3[NC], k4[NC], xt[NX];')
    a('      fcs_update(xi, ui, dt);')
    a('      memcpy(xt, xi, sizeof(xt));')
    a('      deriv(xi, xi + X_AUX_UDOT, ei, 0, k1, NULL);')
    a('      for (int j = 0; j < NC; ++j) xt[j] = xi[j] + 0.5 * dt * k1[j];')
    a('      deriv(xt, k1 + 3, ei, 0, k2, NULL);')
    a('      for (int j = 0; j < NC; ++j) xt[j] = xi[j] + 0.5 * dt * k2[j];')
    a('      deriv(xt, k2 + 3, ei, 0, k3, NULL);')
    a('      for (int j = 0; j < NC; ++j) xt[j] = xi[j] + dt * k3[j];')
    a('      deriv(xt, k3 + 3, ei, 0, k4, NULL);')
    a('      for (int j = 0; j < NC; ++j) xi[j] += dt / 6.0 * (k1[j] + 2.0 * k2[j] + 2.0 * k3[j] + k4[j]);')
    a('      xi[X_AUX_UDOT] = k4[3]; xi[X_AUX_UDOT + 1] = k4[4]; xi[X_AUX_UDOT + 2] = k4[5];')
    a('      fc_quat_normalize(xi + 6);')
    for i in range(ne):
        a(f'      if (xi[{13 + i}] < 0.0) xi[{13 + i}] = 0.0;  /* FGPropeller: the engine does not turn backwards */')
    a('    }')
    a('    if (y) deriv(xi, xi + X_AUX_UDOT, ei, 0, NULL, y + (size_t)i * NY);')
    a('  }')
    a('}')
    a('')
    a(f'void {N}_eval(int n, const double *x, const double *env, int jsbsim_order, double *xd, double *y)')
    a('{')
    a('  for (int i = 0; i < n; ++i) {')
    a('    const double *xi = x + (size_t)i * NX;')
    a('    deriv(xi, xi + X_AUX_UDOT, env + (size_t)i * NE, jsbsim_order, xd ? xd + (size_t)i * NC : NULL, y ? y + (size_t)i * NY : NULL);')
    a('  }')
    a('}')
    src = '\n'.join(L) + '\n'
    src = src.replace('X_HELD0 + 0]', 'X_HELD0]')

    H = [f'/* {N}_core.h: generated by px4-llm-sim2hitl fastcore/gen.py from vehicles/{N}. Do not edit.',
         f' * Layout of the arrays: {N}_core.json. All arrays are row-major, one row per vehicle. */',
         f'#ifndef {P}_CORE_H', f'#define {P}_CORE_H', '#ifdef __cplusplus', 'extern "C" {', '#endif',
         f'#define {P}_NX {nx}  /* state */', f'#define {P}_NC {nc}  /* continuous part of the state */',
         f'#define {P}_NU {len(u_names)}  /* inputs */', f'#define {P}_NE 6  /* environment */',
         f'#define {P}_NY {ny}  /* outputs */',
         f'/* Set the FCS and auxiliary states from the inputs; pos, velocity, attitude, rates and rpm are kept. */',
         f'void {N}_reset(int n, double *x, const double *u);',
         f'/* k steps of dt seconds for n vehicles; y (n x NY, may be NULL) gets the outputs at the final state. */',
         f'void {N}_step(int n, double *x, const double *u, const double *env, double dt, int k, double *y);',
         f'/* Derivatives (n x NC, may be NULL) and outputs (n x NY, may be NULL) at the given states. */',
         f'void {N}_eval(int n, const double *x, const double *env, int jsbsim_order, double *xd, double *y);',
         '#ifdef __cplusplus', '}', '#endif', '#endif', '']
    layout = {
        'vehicle': N, 'generator': 'px4-llm-sim2hitl fastcore/gen.py', 'sources_sha256': srcs, 'generator_sha256': gen_hash,
        'x': x_names, 'continuous': nc, 'u': u_names, 'env': env_names, 'y': y_names,
        'mass_kg': mass_kg, 'inertia_kgm2': Jsi,
        'contacts': [n for n, _ in g.contacts],
        'frames': 'NED position from an origin at origin_alt_msl_m; body velocity relative to the ground; quaternion '
                  'body to NED, scalar first; rates in body axes',
        'not_modelled': v.notes + [
            'flat, non-rotating Earth with constant gravity (env gravity_mps2): no Coriolis or transport rate',
            'standard atmosphere, first layer only (below 11 km)',
            'no turbulence; the wind is constant within a call (env)',
            'alphadot from the previous derivative evaluation (JSBSim: the previous frame)',
            'flight control runs once per step (dt) and its outputs are held over the step'],
    }
    (out / f'{N}_core.c').write_text(src)
    (out / f'{N}_core.h').write_text('\n'.join(H))
    (out / f'{N}_core.json').write_text(json.dumps(layout, indent=1) + '\n')
    return out


def inv3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def build(out, name, cc='cc', native=False):
    flags = ['-O3', '-fPIC', '-shared', '-fno-math-errno', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-variable', '-Wno-unused-parameter']
    if native:
        flags.append('-march=native')
    lib = out / f'lib{name}_core.so'
    cmd = [cc, *flags, '-I', str(RUNTIME), '-o', str(lib), str(out / f'{name}_core.c'), '-lm']
    subprocess.run(cmd, check=True)
    return lib


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('vehicle')
    p.add_argument('--out')
    p.add_argument('--cc', default='cc')
    p.add_argument('--native', action='store_true', help='-march=native (faster, not portable)')
    a = p.parse_args()
    name = Path(a.vehicle).resolve().name
    out = Path(a.out) if a.out else Path('build/fastcore') / name
    try:
        generate(a.vehicle, out)
    except Unsupported as e:
        sys.exit(f'fastcore: {e}')
    lib = build(out, name, a.cc, a.native)
    print(json.dumps({'vehicle': name, 'out': str(out), 'lib': str(lib)}))


if __name__ == '__main__':
    main()
