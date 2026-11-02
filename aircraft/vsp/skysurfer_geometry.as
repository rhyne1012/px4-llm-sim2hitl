// SkySurfer for VSPAERO: the planform of aircraft/avl/SkySurfer_wing2410_NDU.avl (wing, horizontal tail, fin; thin
// surfaces, no fuselage) with its four control surfaces and the 1.2 deg tail ANGLE. Included by run_table.py.
// VSP axes: X aft, Y right, Z up, origin at the wing root leading edge (the AVL origin).

void SetSS(string ss, string name, double value) { SetParmVal(FindParm(ss, name, "SS_Control"), value); }

// Sections of one lifting surface: span stations, chords, leading-edge x; NACA 4-digit camber/position/thickness.
string Surface(string name, array<double> @y, array<double> @c, array<double> @x, double camber, double camberLoc,
               double thick, double panel, int tessW) {
    string g = AddGeom("WING", "");
    SetGeomName(g, name);
    for (int i = 0; i < int(y.size()) - 2; i++) { InsertXSec(g, 1, XS_FOUR_SERIES); }
    Update();
    for (int i = 1; i < int(y.size()); i++) {
        SetDriverGroup(g, i, SPAN_WSECT_DRIVER, ROOTC_WSECT_DRIVER, TIPC_WSECT_DRIVER);
        string xs = "XSec_" + i;
        double dy = y[i] - y[i - 1];
        SetParmVal(g, "Span", xs, dy);
        SetParmVal(g, "Root_Chord", xs, c[i - 1]);
        SetParmVal(g, "Tip_Chord", xs, c[i]);
        SetParmVal(g, "Sweep_Location", xs, 0.0);
        SetParmVal(g, "Sweep", xs, atan((x[i] - x[i - 1]) / dy) * 180.0 / 3.14159265358979);
        SetParmVal(g, "Dihedral", xs, 0.0);
        SetParmVal(g, "Twist", xs, 0.0);
        SetParmVal(g, "SectTess_U", xs, int(dy / panel) + 3);
        Update();
    }
    string surf = GetXSecSurf(g, 0);
    for (int i = 0; i < int(y.size()); i++) {
        ChangeXSecShape(surf, i, XS_FOUR_SERIES);
        string xs = GetXSec(surf, i);
        SetParmVal(GetXSecParm(xs, "Camber"), camber);
        SetParmVal(GetXSecParm(xs, "CamberLoc"), camberLoc);
        SetParmVal(GetXSecParm(xs, "ThickChord"), thick);
    }
    SetParmVal(g, "Tess_W", "Shape", tessW);
    Update();
    return g;
}

// A control surface between two span fractions; chord as a fraction (rel) or in metres (abs).
string Control(string g, double etaStart, double etaEnd, double chord, bool absolute) {
    string ss = AddSubSurf(g, SS_CONTROL);
    SetSS(ss, "EtaFlag", 1.0);
    SetSS(ss, "EtaStart", etaStart);
    SetSS(ss, "EtaEnd", etaEnd);
    SetSS(ss, "SE_Const_Flag", 1.0);
    if (absolute) {
        SetSS(ss, "Abs_Rel_Flag", 0.0);
        SetSS(ss, "Length_Start", chord);
        SetSS(ss, "Length_End", chord);
    } else {
        SetSS(ss, "Abs_Rel_Flag", 1.0);
        SetSS(ss, "Length_C_Start", chord);
        SetSS(ss, "Length_C_End", chord);
    }
    Update();
    return ss;
}

void BuildSkySurfer(double tailIncidenceDeg) {
    // Wing: NACA 2410, sections of the AVL right wing; mirrored to the left.
    array<double> wy = {0, 0.27, 0.335, 0.4, 0.42, 0.46, 0.5, 0.52, 0.57, 0.67};
    array<double> wc = {0.198, 0.193, 0.19, 0.185, 0.181, 0.17, 0.16, 0.155, 0.126, 0.022};
    array<double> wx = {0, 0.004, 0.008, 0.013, 0.017, 0.028, 0.038, 0.043, 0.072, 0.176};
    string w = Surface("Wing", wy, wc, wx, 0.02, 0.4, 0.10, 0.0125, 25);
    // Ailerons: AVL y 0.27-0.50 per side, hinge at 70-73 % chord (about 29 % of the chord).
    Control(w, 0.27 / 0.67, 0.50 / 0.67, 0.29, false);

    // Horizontal tail: NACA 0013 at x 0.554, z -0.045; incidence about its root leading edge, leading edge up.
    array<double> ty = {0, 0.13, 0.157, 0.165, 0.173, 0.19, 0.2, 0.224, 0.238};
    array<double> tc = {0.107, 0.1, 0.096, 0.0935, 0.091, 0.084, 0.08, 0.063, 0.03};
    array<double> tx = {0, 0, 0.003, 0.004, 0.005, 0.012, 0.02, 0.037, 0.08};
    string t = Surface("HTail", ty, tc, tx, 0.0, 0.4, 0.13, 0.01, 25);
    SetParmVal(t, "X_Rel_Location", "XForm", 0.554);
    SetParmVal(t, "Z_Rel_Location", "XForm", -0.045);
    SetParmVal(t, "Y_Rel_Rotation", "XForm", tailIncidenceDeg);  // + = trailing edge down (checked)
    Update();
    // Elevator: measured 2026-10-15, hinged flap 0.035 m chord, y 0-0.165 per side.
    Control(t, 0.0, 0.165 / 0.238, 0.035, true);

    // Fin: NACA 0010 at x 0.51, z -0.045, one surface (no mirror).
    array<double> fz = {0, 0.007, 0.026, 0.068, 0.097, 0.125, 0.157, 0.176};
    array<double> fc = {0.123, 0.109, 0.125, 0.12, 0.104, 0.089, 0.064, 0.004};
    array<double> fx = {0, 0.014, 0.027, 0.031, 0.047, 0.061, 0.086, 0.15};
    string f = Surface("Fin", fz, fc, fx, 0.0, 0.4, 0.10, 0.012, 21);
    SetParmVal(f, "Sym_Planar_Flag", "Sym", 0);
    SetParmVal(f, "X_Rel_Location", "XForm", 0.51);
    SetParmVal(f, "Z_Rel_Location", "XForm", -0.045);
    SetParmVal(f, "X_Rel_Rotation", "XForm", 90.0);
    Update();
    // Rudder: measured 2026-10-15, 0.025 m chord, z 0.007-0.125.
    Control(f, 0.007 / 0.176, 0.125 / 0.176, 0.025, true);
}
