function m = linear_model(jsonFile, index)
%LINEAR_MODEL Control System Toolbox objects from sitl/trim.py --linearize --out FILE.
%   m = linear_model(jsonFile)         the first trim in the file
%   m = linear_model(jsonFile, index)  another trim, when the file has several airspeeds
%
%   m.airframe  ss, states u v w p q r phi theta, inputs at the surfaces (servos out of the matrices)
%   m.full      ss, the 37 states and 5 commands of the model, servos included
%   m.tf        zpk per output_input, for example m.tf.q_elevator; m.tfServo adds the servo pole
%   m.modes, m.airspeed_m_s, m.elevator, m.throttle
%
%   Small-signal models of one trim: no saturation, no rate limit, no delay. Example:
%     m = linear_model('lin16.json'); bode(m.tfServo.q_elevator); step(m.tf.theta_elevator)
if nargin < 2, index = 1; end
data = jsondecode(fileread(jsonFile));
trims = data.trims;
if iscell(trims), r = trims{index}; else, r = trims(index); end
assert(isfield(r, 'linear'), 'No linear model in this file: run sitl/trim.py with --linearize.');
L = r.linear;

states = L.states_airframe;
inputs = L.inputs;
m.airframe = ss(L.A_airframe, L.B_airframe, eye(numel(states)), 0, 'StateName', states, 'InputName', inputs, ...
    'OutputName', states);
m.full = ss(L.A_full, L.B_full, eye(size(L.A_full, 1)), 0, 'InputName', inputs);
names = fieldnames(L.transfer_functions);
for k = 1:numel(names)
    item = L.transfer_functions.(names{k});
    m.tf.(names{k}) = zpk(tf(item.airframe.num(:)', item.airframe.den(:)'));
    m.tfServo.(names{k}) = zpk(tf(item.with_servo.num(:)', item.with_servo.den(:)'));
end
m.modes = L.modes;
m.airspeed_m_s = r.airspeed_m_s;
m.elevator = r.elevator;
m.throttle = r.throttle;
m.plant_lib = data.plant_lib;
end
