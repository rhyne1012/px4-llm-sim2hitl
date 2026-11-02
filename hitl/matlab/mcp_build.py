"""MATLAB through its MCP server (SIM2HITL_MATLAB_MCP, or the two usual install paths), from the command line.

The server connects to an existing shared MATLAB session by default (SIM2HITL_MATLAB_MCP_MODE=new starts its own)."""
import json,os,queue,re,subprocess,threading,time
from pathlib import Path
def find_server():
 candidates=[os.environ.get('SIM2HITL_MATLAB_MCP'),Path.home()/'.matlab/agentic-toolkits/bin/matlab-mcp-server',Path.home()/'.MathWorks/AgenticToolkits/v1/bin/matlab-mcp-server']
 for candidate in candidates:
  if candidate and Path(candidate).is_file():return Path(candidate)
 raise RuntimeError('Configure this host MATLAB MCP, or run plant/core/build_core.m in MATLAB directly; no runtime reinstall')
def evaluate(project,code):
 """Run MATLAB code with the project as the current folder; returns the command window text. Without a shared session
 (MATLAB shareMATLABSession) it starts its own, unless SIM2HITL_MATLAB_MCP_MODE says which one to use."""
 mode=os.environ.get('SIM2HITL_MATLAB_MCP_MODE')
 if mode:return _evaluate(project,code,mode)
 try:return _evaluate(project,code,'existing')
 except RuntimeError as error:
  if 'attach' not in str(error):raise
 return _evaluate(project,code,'new')
def _evaluate(project,code,mode):
 server=find_server()
 proc=subprocess.Popen([str(server),'--matlab-session-mode',mode,'--disable-telemetry=true'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 messages=queue.Queue()
 def read():
  for line in proc.stdout:
   try:messages.put(json.loads(line))
   except ValueError:pass
 threading.Thread(target=read,daemon=True).start()
 def request(ident,method,params):
  proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n');proc.stdin.flush();deadline=time.monotonic()+600
  while time.monotonic()<deadline:
   try:r=messages.get(timeout=1)
   except queue.Empty:
    if proc.poll() is not None:raise RuntimeError('MATLAB MCP exited: '+proc.stderr.read()[-2000:])
    continue
   if r.get('id')==ident:
    if 'error' in r:raise RuntimeError(str(r['error']))
    return r['result']
  raise RuntimeError('MATLAB MCP build timeout')
 try:
  request(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'px4-llm-sim2hitl-update','version':'1.0'}})
  proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');proc.stdin.flush()
  tools=request(2,'tools/list',{})['tools'];tool=next(t for t in tools if t['name']=='evaluate_matlab_code')
  props=tool['inputSchema']['properties']
  args={'code':code}
  if 'project_path' in props:args['project_path']=str(project)
  result=request(3,'tools/call',{'name':tool['name'],'arguments':args})
  text='\n'.join(c.get('text','') for c in result.get('content',[]))
  if not result.get('isError'):print(text,flush=True)
  if result.get('isError'):raise RuntimeError('MATLAB code failed: '+text[-500:])
  return text
 finally:
  proc.stdin.close()
  try:proc.wait(timeout=3)
  except subprocess.TimeoutExpired:proc.terminate()
def generate(runtime):
 # Plant core builder (plant/core/build_core.m): reusable core C plus Simulink reference runs.
 path=str(Path(runtime).parent/'plant'/'core').replace("'","''")
 text=evaluate(Path(runtime).parent,"addpath('"+path+"'); bcache=build_core(); fprintf('B_EXPORT_CACHE=%s\\n',bcache);")
 match=re.search(r'B_EXPORT_CACHE=([^\r\n]+)',text)
 if not match:raise RuntimeError('MATLAB did not return export cache')
 return Path(match.group(1))
