%% FW_SkySurfer_InitialFunction
% Source parameters for FW_SkySurfer_HIL.slx: initial conditions, mass properties, geometry,
% aerodynamic tables, actuator effectiveness, ground contact and sample time.
% Runs from the model InitFcn and from plant/core/build_core.m.

%% Caller check
if evalin('base', 'exist(''lastRunModel'', ''var'')')
    modelName = evalin('base', 'lastRunModel');
    if ~strcmp(modelName, 'FW_SkySurfer_HIL')
        error('Unrecognized model name: %s', modelName);
    end
elseif exist('ByPass_lastRunModel', 'var') && ByPass_lastRunModel == 1
    modelName = 'ByPass';
    ByPass_lastRunModel = 0;
else
    error('Variable lastRunModel does not exist in the base workspace. Please ensure the model InitFcn is set.');
end

%% Initial Condition

if strcmp(modelName, 'FW_SkySurfer_HIL')
    U0                  =  0 * convvel(1, 'kts', 'm/s');        % ini. velocity, kts
    W0                  =  0 * convvel(1, 'kts', 'm/s');        % ini. velocity, kts
    H0                  =  0 * convlength(1, 'ft', 'm');        % ini. altitude, ft
else
    U0                  =  40.0309 * convvel(1, 'kts', 'm/s');  % ini. velocity, kts
    W0                  =  0.6032 * convvel(1, 'kts', 'm/s');   % ini. velocity, kts
    H0                  =  1000 * convlength(1, 'ft', 'm');     % ini. altitude, ft
end

V0                      =  0;
Phi0                    =  0;
Theta0                  =  0.8633;                              % ini. euler angle, deg
Psi0                    =  0;

Lon0                    =  120.31096929726908;                  % ini. lon.
Lat0                    =  22.910275834988674;                  % ini. lat.

Vel_w                   =  0;                                   % wind velocity, kts
Psi_w                   =  0;                                   % wind direction, deg

%%  UAV Parameter

Mass0                   =   1.3;                        % empty weight, kg

% Moments of inertia from the first flight test, 2026-10-26: record
% records/20261026-1652_flight_04-doublet-cubeorangeplus-flight_none_OBSERVED, flight log on the GitHub
% release flight-test-20261026-1652. The doublets were fitted and compared with the same fits on HITL logs of this
% model, assuming the AVL Clp, Cmq, Cmde and the 27 deg elevator. Results: Ixx 0.02-0.03, Iyy 0.04-0.06; Izz was
% not identifiable (no rudder excitation), so it is Ixx + Iyy (a flat airframe, as the original mass file is).
% Before: Ixx 2*0.023, Iyy 3*0.029, Izz 0.05 (the original author's mass file times 2 and 3, reason unknown).
% Iyy re-estimated 2026-11-02 on the corrected aero model, because the first estimate (0.050) assumed the old elevator
% table: same-method fits on the same flight give 0.033-0.044 and the doublet replay is best at 0.04-0.045
% (docs/tasks/20261102_aero_review.md). Two doublets only; a bifilar pendulum would settle it.
Ixx                     =   0.023;                      % kg*m^2, flight test 2026-10-26 (0.02-0.03)
Ixy                     =   6.56e-05;                   % kg*m^2
Iyy                     =   0.040;                      % kg*m^2, flight test 2026-10-26, re-estimated 2026-11-02 (0.033-0.05)
Iyz                     =   2.784e-04;                  % kg*m^2
Izz                     =   Ixx + Iyy;                  % kg*m^2, 0.063: not measured, Ixx + Iyy
Ixz                     =  -2.266e-05;                  % kg*m^2

Inertia0	            =  [  Ixx -Ixy -Ixz  ;...       % moment of inertia, kg*m^2
                             -Ixy  Iyy -Iyz  ;...
                             -Ixz -Iyz  Izz ];

% Positions on the body station axis in metres (aft positive from the fuselage datum).
% The Aerodynamic block takes -CG_m / -XREF_m as body-axis (forward positive) positions and
% transfers the moments from XREF_m to CG_m. The AVL tables must be computed about XREF_m.
% CG of the real aircraft as flown in the first flight test (2026-10-26, user: about 65 mm behind the wing root
% leading edge = AVL x 0.065, 25.9 % of the geometric MAC; record 20261026-1652_flight_...). Was 0.330 (50 mm, the
% original author's mass file).
CG_m                    =  [0.345, 0, 0];               % centre of gravity, m
XREF_m                  =  [0.330, 0, 0];               % moment reference point of the aero tables, m

cbar                    =  0.20;                        % chord length, m
b                       =  1.41;                        % wing span, m
S                       =  0.238;                       % wing reference area, m^2
% Thrust line above the CG (+ gives nose down with thrust). The 2026-10-26 flight suggests about 0.12 m, but this stays 0:
% the ground has no moment and the aero is off below 5 m/s, so takeoff thrust alone pitches the model over on the ground
% (SITL record 20261102-1357). The horizontal tail ANGLE in the AVL file carries that nose-down moment at cruise instead.
del_z                   =  0 ;                          % thrust z-axis offset, m

% Onborad Atmosphere Model
g                       =  9.80665;                     % gravity, m/s^2

%% Choose which Aerodynamic table and Fix term
useAVL_VSP = 0; % 0: AVL, 1: VSP

% Control-surface effectiveness versus |deflection| (deg); clipped outside the breakpoints.
% The original fall with deflection (AIL 0.8 to 0.5, ELE 0.9 to 0.6, RUD 0.9 to 0.6) was the user's estimate. The
% 2026-10-26 flight does not show that fall on the elevator or the ailerons, and flat values replay its doublets better:
% elevator 0.8, ailerons 0.75 (docs/tasks/20261102_aero_review.md). Each value is relative to the AVL derivative and the
% model travel (27, 30 deg). The rudder is unchanged: that flight had no rudder excitation.
% Ailerons 0.75 -> 0.9 with the roll-due-to-sideslip term below (SkySurfer project, docs/tasks/20261102_ft_vane.md): 0.75 was fitted when
% the model had almost no Clb; with it the SITL roll rate per aileron fell from 251 to 204 deg/s (10-26 flight 259-278).
% 0.9 sits between the vane flights' own estimate (0.84) and a refit on the 10-26 rolls (about 1.0).
Aeroelasticity_Gain_AIL     = [ 0.9  0.9 ];
Aeroelasticity_AIL          = [   5   15];
Aeroelasticity_Gain_ELE     = [ 0.8  0.8];
Aeroelasticity_ELE          = [   5   15];
Aeroelasticity_Gain_RUD     = [ 0.9  0.6];
Aeroelasticity_RUD          = [   5   15];

% AVL
run import_aerostates_avl.m;
% Roll due to sideslip from the 2026-11-02 vane flights (SkySurfer project, docs/tasks/20261102_ft_vane.md): their Clb/Clp and Clb/Clda
% ratios give Clb about -0.12 /rad (+-30 %) at alpha -2..9 deg, where this AVL table has -0.015 (flat wing). The user
% measured the dihedral as about 0, so the cause is still open. AVL table only: the VSP table is not flown, and with
% about -0.054 at alpha 5 it is also far from the flight.
dClb_flight = -0.105;                                       % per rad, added to the AVL Cltot at every Mach and alpha
Cltot = Cltot + dClb_flight * deg2rad(reshape(beta_avl, 1, 1, []));
% Parasite drag on top of AVL (inviscid: induced drag only). 0.030 (was 0.075) carries over the SkyTalon CFD
% finding (rhyne1012/skytalon-cfd f48784f, docs/HANDOFF_6DOF_DRAG_20261022.md): its 6DOF drag was 2.5x CFD.
% Matched at the same CL, SkyTalon CFD minus this AVL table is 0.030 at CL 0.39 and 0.034 at CL 0.80; the old
% value was 2.1x CFD at CL 0.39. CFD there is clean laminar flow, a lower bound (props and roughness add 30-60%).
CD_fix_AVL = 0.030;
% VSP (aircraft/vsp/run_table.py, 2026-11-02: same planform, grid and moment reference as the AVL table)
run import_aerostates_vsp.m;
% VSPAERO's CD already has its own skin-friction estimate; 0.0045 makes the VSP path's total drag equal the AVL path's
% (CD_fix_AVL above) within 0.0005 over alpha -5..10 deg at the same alpha. Was 0.065 for the old table.
CD_fix_VSP = 0.0045;

%% Propulsion: static thrust table and in-flight lapse (Propulsion subsystem, aircraft/thrust)
% From rhyne1012/guppy-sim2hitl 126bc46 (aircraft/thrust): the GUPPY 8x6 bench static thrust (prop_8x6_data.mat
% Lookup; command clipped to 0..1) and T = max(0, Ts - K*V*sqrt(Ts)), V true airspeed, K from the GUPPY 9/28
% flight at 25-30 m/s. Not SkySurfer's own propeller (user choice 2026-10-25, until SkySurfer data exist). Replaces
% the airspeed-independent 2.45 kgf * throttle. The GUPPY bench delay and 3rd-order dynamics are not ported (6 more
% continuous states); the throttle actuator lag 5/(s+5) stays.
PropThrust.CommandBP = [0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1];
PropThrust.Table_N   = [0 0.53938499093055725 1.4710500240325928 2.6478900909423828 4.4131498336791992 ...
                        6.3745501041412354 8.3849849700927734 10.395419597625732 12.307785034179688 ...
                        14.220149993896484 16.132514953613281];
PropThrust.LapseK    = 0.057;                   % N^0.5 s/m

%% Sampling Timer
Thil                    =  1/250;               % model fixed step, s

%% Ground contact
uavData.contact.vd = 0.02;
uavData.contact.rollingFriction = 0.2;
uavData.contact.naturalFreq = 20;
uavData.contact.spring = Mass0*(uavData.contact.naturalFreq*2*pi)^2;
uavData.contact.damper = 2*Mass0*sqrt(uavData.contact.spring/Mass0);
