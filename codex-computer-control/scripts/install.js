import { cpSync,existsSync,mkdirSync,writeFileSync,renameSync,rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { ROOT, dataDirectory, detectPlatform } from '../src/platform.js';
if(!detectPlatform().supported)throw new Error('This plugin supports macOS and Windows only');
if(Number(process.versions.node.split('.')[0])<22)throw new Error('Node.js 22 or newer is required');
const data=dataDirectory();mkdirSync(data,{recursive:true});
const target=path.join(data,'marketplace'),staging=path.join(data,`install-${Date.now()}`),plugin=path.join(staging,'codex-computer-control');
const finalPlugin=path.join(target,'codex-computer-control');
function run(command,args,options={}){
  // Execute binaries directly; no shell interpolation of paths/arguments.
  const result=spawnSync(command,args,{stdio:'inherit',...options});
  if(result.error)throw result.error;if(result.status!==0)throw new Error(`${command} failed (${result.status})`);
}
function npmCi(cwd){
  if(process.platform==='win32'){
    // npm-cli.js is distributed next to node.exe in standard Windows Node installs.
    const npmCli=path.join(path.dirname(process.execPath),'node_modules','npm','bin','npm-cli.js');
    if(!existsSync(npmCli))throw new Error('npm-cli.js missing beside Node.js. Install the official Node.js LTS distribution.');
    run(process.execPath,[npmCli,'ci','--omit=dev','--ignore-scripts','--no-audit','--no-fund'],{cwd});
  }else run('npm',['ci','--omit=dev','--ignore-scripts','--no-audit','--no-fund'],{cwd});
}
let committed=false;const backup=path.join(data,`marketplace-backup-${Date.now()}`);
try{
  cpSync(ROOT,plugin,{recursive:true,filter:source=>!['node_modules','bin','.mcp.json','.DS_Store','.git','__pycache__'].includes(path.basename(source))});
  for(const file of ['README.md','README.en.md','ARCHITECTURE.md','BUG_AUDIT.md','BENCHMARKS.md']){const source=path.join(ROOT,'..',file);if(existsSync(source))cpSync(source,path.join(staging,file));}
  const measurements=path.join(ROOT,'..','benchmarks');if(existsSync(measurements))cpSync(measurements,path.join(staging,'benchmarks'),{recursive:true});
  mkdirSync(path.join(staging,'.agents','plugins'),{recursive:true});
  const market={name:'codex-computer-control-local',interface:{displayName:'Codex Computer Control Local'},plugins:[{name:'codex-computer-control',source:{source:'local',path:'./codex-computer-control'},policy:{installation:'AVAILABLE',authentication:'ON_INSTALL'},category:'Productivity'}]};
  writeFileSync(path.join(staging,'.agents','plugins','marketplace.json'),JSON.stringify(market,null,2)+'\n');
  npmCi(plugin);run(process.execPath,[path.join(plugin,'scripts','build-native.js')]);
  const config={mcpServers:{codex_computer_control:{command:process.execPath,args:[path.join(finalPlugin,'src','server.js')]}}};
  writeFileSync(path.join(plugin,'.mcp.json'),JSON.stringify(config,null,2)+'\n');
  // Keep an existing STOP marker. Legacy Python installations used the same data directory.
  if(existsSync(target))renameSync(target,backup);
  renameSync(staging,target);committed=true;
  let codex=process.env.CODEX_CLI||(process.platform==='win32'?'codex.exe':'codex');
  if(process.platform==='darwin'&&!process.env.CODEX_CLI){
    const probe=spawnSync(codex,['--version'],{stdio:'ignore'});
    if(probe.error)codex=['/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex','/Applications/Codex.app/Contents/Resources/codex'].find(existsSync)||codex;
  }
  let codexPrefix=[];
  if(process.platform==='win32'&&!process.env.CODEX_CLI){
    const probe=spawnSync(codex,['--version'],{stdio:'ignore',windowsHide:true});
    if(probe.error){
      const locations=[path.join(process.env.APPDATA||'', 'npm','node_modules','@openai','codex','bin','codex.js'),path.join(path.dirname(process.execPath),'node_modules','@openai','codex','bin','codex.js')];
      const shim=locations.find(existsSync);
      if(!shim)throw new Error('Codex CLI not found. Set CODEX_CLI to the full path of codex.exe.');
      codex=process.execPath;codexPrefix=[shim];
    }
  }
  run(codex,[...codexPrefix,'plugin','marketplace','add',target,'--json']);
  run(codex,[...codexPrefix,'plugin','add','codex-computer-control@codex-computer-control-local','--json']);
  console.error('Installed Codex Computer Control 1.1.0. Restart Codex and start a new chat.');
  if(existsSync(backup))console.error('Previous installation preserved at '+backup);
}catch(error){
  // Roll back source files on registration failure. User-level plugin config may need retry.
  if(committed&&existsSync(backup)){rmSync(target,{recursive:true,force:true});renameSync(backup,target);}
  if(existsSync(staging))rmSync(staging,{recursive:true,force:true});
  console.error(error.message);process.exitCode=1;
}
