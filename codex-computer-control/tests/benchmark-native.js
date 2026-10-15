import {writeFileSync} from 'node:fs';
import { NativeBridge } from '../src/bridge.js';
import { ROOT } from '../src/platform.js';
const root=ROOT;const output=process.argv[2];
const bridge=new NativeBridge({root});
const rows=[];
try{
  const t=performance.now();const status=await bridge.call('status');rows.push({op:'cold_status',ms:Math.round(performance.now()-t)});
  if(!status.desktop_available||!status.screen_recording)throw new Error('Desktop unavailable for benchmark');
  for(let i=0;i<5;i++){const t=performance.now();const result=await bridge.call('observe',{profile:'ultra',format:'jpeg'});rows.push({op:'observe',ms:Math.round(performance.now()-t),bytes:result.image.length,capture_backend:result.capture_backend});}
  for(let i=0;i<3;i++){const t=performance.now();const result=await bridge.call('text',{region:{x:100,y:100,width:800,height:500},target:'CCC BENCHMARK ABSENT TARGET 932851'});rows.push({op:'text_fallback',ms:Math.round(performance.now()-t),source:result.source,count:result.rows.length});}
  if(output)writeFileSync(output,JSON.stringify({rows},null,2));console.log(JSON.stringify({rows}));
}finally{bridge.close();}
