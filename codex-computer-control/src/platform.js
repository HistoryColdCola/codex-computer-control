import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
export const ROOT = fileURLToPath(new URL('../', import.meta.url));
export function detectPlatform(platform = process.platform) {
  if (platform === 'darwin') return { platform, backend: 'swift', supported: true };
  if (platform === 'win32') return { platform, backend: 'csharp-powershell', supported: true };
  return { platform, backend: null, supported: false };
}
export function dataDirectory(platform = process.platform, env = process.env, home = os.homedir()) {
  return platform === 'win32'
    ? path.win32.join(env.LOCALAPPDATA || path.win32.join(home, 'AppData', 'Local'), 'codex-computer-control')
    : path.join(home, '.local', 'share', 'codex-computer-control');
}
export function backendCommand(platform = process.platform, root = ROOT) {
  if (platform === 'darwin') return { command: path.join(root, 'bin', 'computer-control-macos'), args: [] };
  if (platform === 'win32') {
    // Use the OS binary rather than a PowerShell executable from an arbitrary PATH entry.
    const system = process.env.SystemRoot || 'C:\\Windows';
    return { command: path.win32.join(system, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
      args: ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned', '-File', path.join(root, 'native', 'windows', 'bridge.ps1')] };
  }
  throw new Error(`Unsupported operating system: ${platform}. Supported: macOS and Windows.`);
}
