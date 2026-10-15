import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { backendCommand, dataDirectory } from './platform.js';
export class NativeBridge {
  constructor({ platform=process.platform, root, dataDir=process.env.CCC_DATA_DIR||dataDirectory(platform), command, args }={}) {
    this.platform=platform;this.root=root;this.dataDir=dataDir;this.override=command?{command,args:args||[]}:null;
    this.child=null;this.pending=null;this.sequence=0;this.buffer='';this.generation=0;
  }
  start() {
    if(this.child)return;
    const spec=this.override||backendCommand(this.platform,this.root);
    if(this.platform==='darwin'&&!this.override&&!existsSync(spec.command))throw new Error('macOS helper missing. Run npm run build:native or reinstall.');
    const child=spawn(spec.command,spec.args,{stdio:['pipe','pipe','pipe'],windowsHide:true,
      env:{...process.env,CCC_DATA_DIR:this.dataDir,CCC_PARENT_PID:String(process.pid)}});
    this.child=child;this.buffer='';const generation=++this.generation;
    const fail=error=>{if(this.child===child){this.child=null;this.pending?.reject(error);this.pending=null;}};
    child.once('error',fail);child.once('exit',(code,signal)=>fail(new Error(`Native backend exited (${code??signal})`)));
    child.stderr.on('data',data=>process.stderr.write(data));
    child.stdin.on('error',fail);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>{
      if(generation!==this.generation)return;
      this.buffer+=chunk;
      if(this.buffer.length>64*1024*1024){this.close(new Error('Native response exceeds 64 MB'));return;}
      let pos;
      while((pos=this.buffer.indexOf('\n'))>=0){
        const line=this.buffer.slice(0,pos);this.buffer=this.buffer.slice(pos+1);
        if(!line.trim())continue;
        try {
          const record=JSON.parse(line);
          if(!this.pending||record.id!==this.pending.id)throw new Error('Unexpected native response ID');
          const pending=this.pending;this.pending=null;
          record.ok?pending.resolve(record.result):pending.reject(new Error(record.error||'Native operation failed'));
        } catch(error){this.close(error);return;}
      }
    });
  }
  call(op,params={},timeout=10000) {
    if(this.pending)return Promise.reject(new Error('Native backend busy'));
    if(timeout<=0)return Promise.reject(new Error('Workflow hard deadline exceeded'));
    try{this.start();}catch(e){return Promise.reject(e);}
    return new Promise((resolve,reject)=>{
      const id=++this.sequence;
      const timer=setTimeout(()=>this.close(new Error('Native operation timed out; delivery may be uncertain')),timeout);
      this.pending={id,resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}};
      this.child.stdin.write(JSON.stringify({id,op,...params})+'\n');
    });
  }
  close(error=new Error('Native backend closed')) {
    const child=this.child;this.child=null;this.generation++;
    this.pending?.reject(error);this.pending=null;
    if(child){child.stdin.destroy();child.kill();const timer=setTimeout(()=>{if(child.exitCode===null)child.kill('SIGKILL');},300);timer.unref();}
  }
}
