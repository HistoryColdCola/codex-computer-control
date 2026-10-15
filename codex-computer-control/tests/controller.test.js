import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Controller } from '../src/controller.js';
import { detectPlatform,dataDirectory,backendCommand } from '../src/platform.js';
class Fake {
  constructor(){this.platform='darwin';this.dataDir=mkdtempSync(path.join(os.tmpdir(),'ccc-test-'));this.generation=1;this.calls=[];this.rows=[];this.fail=null;this.app='100';}
  async call(op,params={}){
    this.calls.push({op,...params});if(this.fail?.(op,params))throw new Error('interrupted native input');
    if(op==='status')return {width:1600,height:900,app_id:this.app,desktop_available:true,accessibility:true,screen_recording:true};
    if(op==='focus'){this.app='200';return {app_id:this.app};}
    if(op==='observe')return {image:'eA==',mimeType:'image/jpeg',origin:[100,50],logical_size:[1024,512],image_size:[512,256],screen_size:[1600,900],app_id:this.app};
    if(op==='text')return {rows:this.rows,source:'mock'};
    return {ok:true};
  }
  close(){}
}
function setup(t,opts){const bridge=new Fake();t.after(()=>rmSync(bridge.dataDir,{recursive:true,force:true}));return {bridge,c:new Controller(bridge,opts)};}
test('platform detection and unsupported Linux',()=>{
  assert.equal(detectPlatform('darwin').backend,'swift');assert.equal(detectPlatform('win32').backend,'csharp-powershell');
  assert.equal(detectPlatform('linux').supported,false);assert.throws(()=>backendCommand('linux'));
  assert.equal(dataDirectory('win32',{LOCALAPPDATA:'C:\\Users\\Name\\AppData\\Local'},'ignored'),'C:\\Users\\Name\\AppData\\Local\\codex-computer-control');
});
test('batch schema rejects malformed later action before any native call',async t=>{const {bridge,c}=setup(t);await assert.rejects(c.step({actions:[{action:'click',x:2,y:2},{action:'press',key:'bogus'}]}));assert.equal(bridge.calls.length,0);});
test('rejects unknown fields, whitespace text, nonfinite duration and wait overflow',async t=>{const {bridge,c}=setup(t);for(const actions of [[{action:'click',x:1,y:2,shell:'x'}],[{action:'assert_text',text:'   '}],[{action:'move',x:1,y:2,duration:Infinity}],[{action:'wait',seconds:1},{action:'wait',seconds:1},{action:'wait',seconds:1}]])await assert.rejects(c.step({actions}));assert.equal(bridge.calls.length,0);});
test('invalid geometry rejects entire batch before activation or input',async t=>{const {bridge,c}=setup(t);const r=await c.step({app:'Test',actions:[{action:'click',x:2,y:2},{action:'click',x:1600,y:2}]});assert.equal(r.isError,true);assert(!bridge.calls.some(x=>x.op==='focus'||x.op==='action'));});
test('STOP blocks input and captures but status remains available',async t=>{const {bridge,c}=setup(t);writeFileSync(c.stopFile,'');const r=await c.step({actions:[{action:'type',text:'x'}]});assert(r.isError);await assert.rejects(c.screenshot());assert.equal(bridge.calls.length,0);assert.equal((await c.status()).stopped,true);});
test('output none completes guarded native batch without capture',async t=>{const {bridge,c}=setup(t);const r=await c.step({actions:[{action:'type',text:'中文🙂'},{action:'press',key:'enter'}],output:'none'});assert.equal(r.isError,false);assert.equal(r.structuredContent.completed,2);assert.equal(bridge.calls.filter(x=>x.op==='observe').length,0);assert(bridge.calls.filter(x=>x.op==='action').every(x=>x.expected==='100'));});
test('native input error activates STOP and never replays remaining actions',async t=>{const {bridge,c}=setup(t);bridge.fail=op=>op==='action';const r=await c.step({actions:[{action:'type',text:'x'},{action:'press',key:'enter'}]});assert.equal(r.structuredContent.uncertain_action,'type');assert(existsSync(c.stopFile));assert.equal(bridge.calls.filter(x=>x.op==='action').length,1);assert.equal(r.content.length,1);});
test('unique scoped text assertion gates send; failure does not send',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'different',x:100,y:100}];const r=await c.step({actions:[{action:'assert_text',text:'draft'},{action:'press',key:'enter'}]});assert(r.isError);assert.equal(r.structuredContent.completed,0);assert(!bridge.calls.some(x=>x.op==='action'));assert.equal(existsSync(c.stopFile),false);});
test('text match ignores whitespace, uses screen positions, and ambiguity stops',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'爸 爸',x:450,y:60}];let r=await c.step({actions:[{action:'click_text',text:'爸爸',region:{x:400,y:0,width:300,height:100}}],output:'none'});assert.equal(r.isError,false);assert.equal(bridge.calls.find(x=>x.op==='action').action.x,450);bridge.rows.push({text:'爸爸',x:500,y:60});r=await c.step({actions:[{action:'assert_text',text:'爸爸'}]});assert(r.structuredContent.error.includes('ambiguous'));});
test('image view transforms thumbnail coordinates including crop origin',async t=>{const {bridge,c}=setup(t);const first=await c.step({actions:[]});const token=first.structuredContent.view_id;const r=await c.step({actions:[{action:'click',x:100,y:50}],view_id:token,output:'none'});assert.equal(r.isError,false);const a=bridge.calls.find(x=>x.op==='action').action;assert.deepEqual([a.x,a.y],[300,150]);});
test('old, restarted and changed-focus views reject input',async t=>{let time=0;const {bridge,c}=setup(t,{clock:()=>time});let r=await c.step({actions:[]});time=120001;r=await c.step({actions:[{action:'click',x:5,y:5}],view_id:r.structuredContent.view_id});assert(r.isError);time=0;r=await c.step({actions:[]});bridge.generation++;r=await c.step({actions:[{action:'click',x:5,y:5}],view_id:r.structuredContent.view_id});assert(r.isError);r=await c.step({actions:[]});bridge.app='999';r=await c.step({actions:[{action:'click',x:5,y:5}],view_id:r.structuredContent.view_id});assert(r.isError);assert(!bridge.calls.some(x=>x.op==='action'));});
test('read-only text output returns text without image',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'hello',x:10,y:20}];const r=await c.step({actions:[],output:'text'});assert.equal(r.content.length,1);assert.equal(r.structuredContent.text_source,'mock');assert(!bridge.calls.some(x=>x.op==='observe'));});
test('action deadline stops following action without replay',async t=>{let time=0;const {bridge,c}=setup(t,{clock:()=>time});const call=bridge.call.bind(bridge);bridge.call=async(op,args)=>{const result=await call(op,args);if(op==='action')time=200;return result;};const r=await c.step({actions:[{action:'click',x:5,y:5},{action:'press',key:'enter'}],budget_ms:100,output:'none'});assert(r.isError);assert.equal(r.structuredContent.completed,1);assert.equal(bridge.calls.filter(x=>x.op==='action').length,1);});
test('busy calls reject instead of concurrently controlling desktop',async t=>{const {c}=setup(t);c.busy=true;await assert.rejects(c.status(),/busy/);await assert.rejects(c.step({actions:[]}),/busy/);});

test('missing click_text target does not pause when no input was dispatched',async t=>{const {c}=setup(t);const r=await c.step({actions:[{action:'click_text',text:'missing'}]});assert(r.isError);assert.equal(r.structuredContent.uncertain_action,null);assert.equal(existsSync(c.stopFile),false);});

test('click_text chooses native invoke when the observed control advertises it',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'Verify',x:500,y:100,element_id:'control-1',actions:['invoke']}];const r=await c.step({actions:[{action:'click_text',text:'Verify'}],output:'none'});assert(!r.isError);assert.deepEqual(bridge.calls.find(x=>x.op==='action').action,{action:'invoke',element_id:'control-1'});assert.equal(r.structuredContent.results[0].method,'invoke');});
test('failed native invoke never falls back to a second coordinate click',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'Verify',x:500,y:100,element_id:'control-1',actions:['invoke']}];bridge.fail=op=>op==='action';const r=await c.step({actions:[{action:'click_text',text:'Verify'}]});assert(r.isError);assert.equal(bridge.calls.filter(x=>x.op==='action').length,1);assert.equal(r.structuredContent.uncertain_action,'click_text');assert(existsSync(c.stopFile));});
test('semantic actions accept only explicit IDs and remain subject to whole-batch validation',async t=>{const {bridge,c}=setup(t);await assert.rejects(c.step({actions:[{action:'set_value',element_id:'field',value:'hello'},{action:'invoke'}]}));assert.equal(bridge.calls.length,0);const r=await c.step({actions:[{action:'focus_element',element_id:'field'},{action:'set_value',element_id:'field',value:'hello'}],output:'none'});assert(!r.isError);assert.equal(r.structuredContent.completed,2);});

test('default image observation adds semantic controls without automatic OCR',async t=>{const {bridge,c}=setup(t);bridge.rows=[{text:'Button',element_id:'button',actions:['invoke'],x:5,y:5}];const r=await c.step({actions:[]});assert(!r.isError);assert.equal(r.structuredContent.text[0].element_id,'button');assert.equal(bridge.calls.find(x=>x.op==='text').accessibility_only,true);});
test('explicit include_text retains full fallback and none mode stays lean',async t=>{const {bridge,c}=setup(t);await c.step({actions:[],include_text:true});assert.equal(bridge.calls.find(x=>x.op==='text').accessibility_only,false);bridge.calls=[];await c.step({actions:[],output:'none'});assert(!bridge.calls.some(x=>x.op==='observe'||x.op==='text'));});
