import {readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {ROOT} from '../src/platform.js';
const files=readdirSync(path.join(ROOT,'tests')).filter(n=>n.endsWith('.test.js')).sort().map(n=>path.join(ROOT,'tests',n));
const result=spawnSync(process.execPath,['--test',...files],{stdio:'inherit'});
if(result.error)throw result.error;process.exitCode=result.status??1;
