function m = linear_model(jsonFile, airspeed)
%LINEAR_MODEL Control System Toolbox objects from the answers of tools/linear.py.
%   m = linear_model(jsonFile)            the first linear model in the file
%   m = linear_model(jsonFile, airspeed)  the linear model of the level trim at this airspeed (m/s)
%
%   m.airframe            ss: states u v w (m/s) p q r (rad/s) phi theta (rad); inputs: the JSBSim command
%                         properties of vehicle.toml (m.inputs); surfaces at the command, thrust quasi-steady
%   m.tf.<out>_<in>       zpk, airframe: for example m.tf.q_elevator, m.tf.p_aileron, m.tf.airspeed_throttle
%   m.tfServo.<out>_<in>  zpk with the actuator or engine pole, and the servo chain delay as InputDelay
%   m.modes, m.servo, m.trim, m.airspeed_m_s, m.outputs (which PX4 output drives which command, with which gain)
%
%   Small-signal models of one trim: no saturation, no rate limit, no PWM quantisation; the servo chain's PWM hold is
%   half its period of delay. Example:
%     m = linear_model('answers.json', 17); bode(m.tfServo.q_elevator); step(m.tf.theta_elevator)
data = jsondecode(fileread(jsonFile));
lins = data.linear;
if isempty(lins), error('linear_model:none', 'No linear model in %s: run tools/linear.py with --linear.', jsonFile); end
if ~iscell(lins), lins = num2cell(lins); end
k = 1;
if nargin > 1
    speeds = cellfun(@(l) l.trim.airspeed_m_s, lins);
    k = find(abs(speeds - airspeed) < 1e-9, 1);
    if isempty(k), error('linear_model:speed', 'No linear model at %g m/s (have %s).', airspeed, mat2str(speeds)); end
end
L = lins{k};

m.inputs = cellstr(L.inputs);
m.states = cellstr(L.states);
m.airframe = ss(L.A, L.B, eye(numel(m.states)), 0, 'StateName', m.states, 'InputName', m.inputs, ...
    'OutputName', m.states);
names = fieldnames(L.transfer_functions);
for i = 1:numel(names)
    item = L.transfer_functions.(names{i});
    m.tf.(names{i}) = zpk(tf(item.airframe.num(:)', item.airframe.den(:)'));
    s = item.with_servo;
    m.tfServo.(names{i}) = zpk(tf(s.num(:)', s.den(:)', 'InputDelay', s.delay_s));
end
m.modes = L.modes;
m.servo = L.servo;
m.trim = L.trim;
m.airspeed_m_s = L.trim.airspeed_m_s;
m.outputs = data.outputs;
end
