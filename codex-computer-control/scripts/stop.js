import {mkdirSync,writeFileSync,rmSync} from 'node:fs';
import path from 'node:path';
import {dataDirectory} from '../src/platform.js';
const data=dataDirectory(),file=path.join(data,'STOP');
if(process.argv.includes('--resume')){rmSync(file,{force:true});console.error('Resumed. Move pointer away from top-left and inspect partial results before continuing.');}
else {mkdirSync(data,{recursive:true});writeFileSync(file,'');console.error('Emergency stop active.');}
