// Creates and controls only its own local test window. No network/message delivery.
import { spawn,execFileSync } from 'node:child_process';
import { mkdtempSync,rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { ROOT } from '../src/platform.js';
if(process.platform!=='darwin')throw new Error('This optional live fixture runs on macOS only');
const temp=mkdtempSync(path.join(os.tmpdir(),'ccc-live-'));let fixture,client;let draftLog='';
try{
  const executable=path.join(temp,'local-test');
  execFileSync('/usr/bin/xcrun',['swiftc','-module-cache-path',path.join(os.tmpdir(),'ccc-swift-module-cache'),path.join(ROOT,'tests','macos-fixture.swift'),'-o',executable],{stdio:'inherit'});
  fixture=spawn(executable,[],{stdio:['ignore','pipe','inherit']});
  fixture.stdout.on('data',chunk=>{draftLog+=chunk.toString();});
  await Promise.race([once(fixture.stdout,'data'),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Fixture startup timed out')),8000))]);
  client=new Client({name:'local-fixture-test',version:'1.0.0'});
  await client.connect(new StdioClientTransport({command:process.execPath,args:[path.join(ROOT,'src','server.js')],stderr:'inherit',env:{...process.env,CCC_DATA_DIR:path.join(temp,'data')}}));
  const state=await client.callTool({name:'desktop_status',arguments:{}});
  const status=state.structuredContent||JSON.parse(state.content[0].text);
  assert.equal(status.app_id,String(fixture.pid),'Fixture is not foreground; refuse input');
  assert(status.desktop_available&&status.accessibility&&status.screen_recording,'Missing live desktop permissions');
  const workflowStarted=performance.now();
  let actions=[
    {action:'assert_text',text:'CCC Local Verification'},
    {action:'hotkey',keys:['command','a']},
    {action:'type',text:'本地测试 123🙂'},
    {action:'assert_text',text:'本地测试 123🙂',timeout_ms:1500},
    {action:'click_text',text:'Verify local draft'},
    {action:'assert_text',text:'Local verified 123',timeout_ms:1500}
  ];
  if(process.argv.includes('--semantic')){
    const seen=await client.callTool({name:'desktop_step',arguments:{actions:[],output:'text'}});
    const rows=seen.structuredContent?.text||[];
    const field=rows.find(row=>row.text==='Ready'&&row.actions?.includes('set_value'));
    const button=rows.find(row=>row.text==='Verify local draft'&&row.actions?.includes('invoke'));
    assert(field&&button,'Fixture did not expose semantic controls: '+JSON.stringify(rows));
    actions=[{action:'focus_element',element_id:field.element_id},{action:'set_value',element_id:field.element_id,value:'本地测试 123🙂'},
      {action:'assert_text',text:'本地测试 123🙂',timeout_ms:1500},{action:'invoke',element_id:button.element_id},
      {action:'assert_text',text:'Local verified 123',timeout_ms:1500}];
  }
  const r=await client.callTool({name:'desktop_step',arguments:{actions,profile:'detail',include_text:true,budget_ms:15000}});
  const info=r.structuredContent||JSON.parse(r.content[0].text);
  console.log(JSON.stringify({completed:info.completed,requested:info.requested,error:info.error,total_ms:info.total_ms,workflow_wall_ms:Math.round(performance.now()-workflowStarted),uncertain_action:info.uncertain_action,actions_ms:info.actions_ms,capture_ms:info.capture_ms,native_calls:info.native_calls,results:info.results}));
  if(r.isError){console.error('Fixture log:',draftLog);const seen=await client.callTool({name:'desktop_step',arguments:{actions:[],output:'text'}});console.error('Observed fixture text:',JSON.stringify(seen.structuredContent));}
  assert(!r.isError,info.error);assert.equal(info.completed,actions.length);
  console.log('Local fixture verified Unicode typing, shortcut, text targeting, click and result. No messages sent.');
}finally{await client?.close();fixture?.kill();rmSync(temp,{recursive:true,force:true});}
