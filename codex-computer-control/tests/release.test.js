import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { ROOT } from '../src/platform.js';
test('npm lock is portable and matches declared direct dependencies',()=>{
  const pkg=JSON.parse(readFileSync(path.join(ROOT,'package.json'),'utf8'));
  const lock=JSON.parse(readFileSync(path.join(ROOT,'package-lock.json'),'utf8'));
  assert.deepEqual(lock.packages[''].dependencies,pkg.dependencies);
  for(const [key,value] of Object.entries(lock.packages)){
    assert(key===''||key.startsWith('node_modules/'),`Nonportable lock key: ${key}`);
    assert(!key.includes('..')&&!key.includes('\\'),`Machine path in npm lock: ${key}`);
    assert(!value.link,'Source links must not enter the release dependency lock');
  }
});
