import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { NativeBridge } from '../src/bridge.js';
const fixture=fileURLToPath(new URL('fake-native.js',import.meta.url));
test('persistent native protocol, timeout kills worker and subsequent calls restart',async t=>{
  const bridge=new NativeBridge({command:process.execPath,args:[fixture]});t.after(()=>bridge.close());
  assert.equal((await bridge.call('one')).echo,'one');const generation=bridge.generation;
  assert.equal((await bridge.call('two')).echo,'two');assert.equal(bridge.generation,generation);
  await assert.rejects(bridge.call('hang',{},60),/timed out/);assert.equal(bridge.child,null);
  assert.equal((await bridge.call('three')).echo,'three');assert(bridge.generation>generation);
});
test('unexpected native exit rejects request promptly',async t=>{const bridge=new NativeBridge({command:process.execPath,args:[fixture]});t.after(()=>bridge.close());await assert.rejects(bridge.call('exit',{},1000),/exited/);});
