import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { ROOT } from '../src/platform.js';
export function buildNative(root=ROOT){
  if(process.platform==='darwin'){
    mkdirSync(path.join(root,'bin'),{recursive:true});
    execFileSync('/usr/bin/xcrun',['swiftc','-O','-module-cache-path',path.join(process.env.TMPDIR||'/tmp','ccc-swift-module-cache'),path.join(root,'native','macos','main.swift'),'-o',path.join(root,'bin','computer-control-macos')],{stdio:'inherit'});
    console.error('Swift helper compiled for '+process.arch);
  }else if(process.platform==='win32'){
    // Compile-only check, no desktop input. Windows PowerShell hosts the same C# source at runtime.
    const exe=path.win32.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
    execFileSync(exe,['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','RemoteSigned','-File',path.join(root,'native','windows','check.ps1')],{stdio:'inherit',windowsHide:true});
  }else throw new Error('Only macOS and Windows are supported');
}
buildNative();
