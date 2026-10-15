import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { ROOT } from '../src/platform.js';
import path from 'node:path';
const client=new Client({name:'computer-control-check',version:'1.1.0'});
const transport=new StdioClientTransport({command:process.execPath,args:[path.join(ROOT,'src','server.js')],stderr:'inherit'});
try{
  await client.connect(transport);
  assert.equal(client.getServerVersion().name,'codex-computer-control');
  assert.equal(client.getServerVersion().version,'1.1.0');
  const names=(await client.listTools()).tools.map(t=>t.name).sort();
  assert.deepEqual(names,['desktop_screenshot','desktop_status','desktop_step']);
  for(const args of [{actions:[{action:'click',x:1,y:1,clicks:99}]},{actions:[{action:'type',text:'x'},{action:'press',key:'bogus'}]},{actions:[],shell:'forbidden'}]){
    const r=await client.callTool({name:'desktop_step',arguments:args});assert.equal(r.isError,true);
  }
  if(process.argv.includes('--native-status')){
    const r=await client.callTool({name:'desktop_status',arguments:{}});assert(!r.isError,JSON.stringify(r));
    const s=r.structuredContent||JSON.parse(r.content[0].text);assert(['swift','csharp-powershell'].includes(s.backend));
    console.log('Native status:',JSON.stringify(s));
  }
  console.log('Real MCP handshake, three tools and batch validation passed. No desktop input sent.');
}finally{await client.close();}
