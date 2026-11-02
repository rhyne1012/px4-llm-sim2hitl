%MODEL_LOCAL_FOLDERS Keep Simulink's cache and generated files outside the project.
% Run by the FW_SkySurfer_HIL PreLoadFcn and InitFcn from this file's folder, and by plant/core/build_core.m.
% It also puts this folder on the path, for the aerodynamic tables and importers.
configureLocalFolders(fileparts(mfilename('fullpath')));

function configureLocalFolders(root)
%CONFIGURELOCALFOLDERS Keep paths and generated files local to this package.
arguments
    root (1,:) char
end
addpath(root);
[~, packageName] = fileparts(root);
% Distinguish projects with the same basename at different locations (the folder path itself, no Java).
packageName = [packageName '-' regexprep(root, '[^A-Za-z0-9]', '_')];
if ismac
    cacheBase = fullfile(getenv('HOME'), 'Library', 'Caches');
elseif ispc
    cacheBase = getenv('LOCALAPPDATA');
else
    cacheBase = getenv('XDG_CACHE_HOME');
    if isempty(cacheBase)
        cacheBase = fullfile(getenv('HOME'), '.cache');
    end
end
assert(~isempty(cacheBase), 'FW_HIL:CacheLocation', ...
    'Cannot resolve a local cache directory.');
localRoot = fullfile(cacheBase, 'PX4HIL', 'Simulink', packageName, computer('arch'));
cacheFolder = fullfile(localRoot, 'cache');
codeGenFolder = fullfile(localRoot, 'codegen');
% InitFcn re-runs this script during model update: change folders only when needed.
current = Simulink.fileGenControl('getConfig');
if ~strcmp(current.CacheFolder, cacheFolder) || ~strcmp(current.CodeGenFolder, codeGenFolder)
    Simulink.fileGenControl('set', 'CacheFolder', cacheFolder, ...
        'CodeGenFolder', codeGenFolder, 'createDir', true);
end
end
