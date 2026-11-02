% Description
% This code is used to import the parsed aerostates and realize online aerodynamic coefficients interpolation. It is written regarding to the F-16 model, with range
% AoA: [-10:2:10]
% Beta: [0]
% Mach: [0.05, 0.10]
% Author
% Oscar Hii, currently doing MS degree in National Cheng Kung University.
% Contact: oscarhiishanmin26@gmail.com
% 2026-11-02: Skysurfer.mat is now made by aircraft/vsp/run_table.py (VSPAERO stability sweep of the AVL planform,
% same grid and reference point as the AVL tables). The grid is read from the data instead of being written here.
% clear; close all; clc
load(fullfile(fileparts(mfilename('fullpath')), 'Skysurfer.mat'));    data_w  = data_out;
% load("aerostates_ht.mat");   data_ht = data_out;
clear data_out

params  = {'Mach', 'AoA', 'Beta', 'CFx', 'CFy', 'CFz', 'CMx', 'CMy', 'CMz', 'CL', 'CD', 'CS', 'CMl', 'CMm', 'CMn'};
suffix  = {'base', 'da', 'db', 'dp', 'dq', 'dr', 'dM', 'dU', 'dailR', 'dailL', 'dele', 'drud'};

% Append suffixes for CFx, CFy, ..., CMn
PARAMS = {};

for i = 4:15
    for j = 1:length(suffix)
        PARAMS(end+1) = append(params(i),'_',suffix(j));
    end
end
% Rebuild dimensions on every import; do not retain another model's table.
AEROSTATES_w = [params(1:3), PARAMS].';


% Aerostates Arrangement
% Main Wing
% VSPAERO FLow Conditions
num_of_states = numel(data_w.mach) + 1; % cases + 1 (the first column is the name of the parameter)

AEROSTATES_w(1,2:num_of_states)  = num2cell(data_w.mach);
AEROSTATES_w(2,2:num_of_states)  = num2cell(data_w.aoa);
AEROSTATES_w(3,2:num_of_states)  = num2cell(data_w.beta);


% Starting from forth row, we place those important parameters
k = 4;
for i = 4:length(params)
    for j = 1:length(suffix)
        AEROSTATES_w(k,2:num_of_states) = num2cell(data_w.(params{i}).(suffix{j}));
        k = k + 1;
    end
end


% Create look-up table
% ------------------------------------------------------------------------
Mach    = unique(data_w.mach);
AoA     = unique(data_w.aoa);
AoS     = unique(data_w.beta);

% List of coefficients
coeffs = {'CFx', 'CFy', 'CFz', 'CMx', 'CMy', 'CMz', 'CL', 'CD', 'CS', 'CMl', 'CMm', 'CMn'};

n = length(suffix) - 1;
% Starting indices for each group
start_idx = 4:n+1:length(AEROSTATES_w)-n;
end_idx   = start_idx + n;

% Loop through each group and assign values
for i = 1:length(coeffs)
    eval([coeffs{i}, '_wgrp  = AEROSTATES_w(', num2str(start_idx(i)), ':', num2str(end_idx(i)), ', 1);']);
end

% Initialize each group variable with zeros
for i = 1:length(suffix)
    for j = 1:length(coeffs)
        eval([coeffs{j}, '_wgrp{i}  = zeros(length(Mach), length(AoA), length(AoS));']);
    end
end
% 
% Loop through each column of AEROSTATES_w and AEROSTATES_ht
C_wgrp  = struct();

for i = 2:length(AEROSTATES_w(1,:))
    % Loop through each variable
    for j = 1:length(coeffs)
        % Initialize the group variable within the structure
        for k = 1:n+1
            % Dynamically create a field within C_wgrp, C_htgrp and assign values
            field_name_w  = [coeffs{j}, '_wgrp'];

            C_wgrp.(field_name_w){k}(Mach == cell2mat(AEROSTATES_w(1, i)), ...
                AoA == cell2mat(AEROSTATES_w(2, i)), ...
                AoS == cell2mat(AEROSTATES_w(3, i))) = cell2mat(AEROSTATES_w(start_idx(j) + k - 1, i));

        end
    end
end


% Clear Some Workspace
clear data_w data_ht 
clear params PARAMS coeffs suffix start_idx end_idx i j k
clear field_name_w field_name_ht
clear CD_htgrp CD_wgrp CFx_htgrp CFx_wgrp CFy_htgrp CFy_wgrp CFz_htgrp CFz_wgrp CL_htgrp CL_wgrp CMl_htgrp CMl_wgrp CMm_htgrp CMm_wgrp CMn_htgrp CMn_wgrp CMx_htgrp CMx_wgrp CMy_htgrp CMy_wgrp CMz_htgrp CMz_wgrp CS_htgrp CS_wgrp
