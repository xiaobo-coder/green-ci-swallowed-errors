// Paper 922 code execution for model-written Python (runner side).
// Every execution: fresh directory under the OS temp dir, macOS sandbox-exec profile (network denied, file writes only
// inside that directory and /dev), CPU-time limit via ulimit -t (RLIMIT_AS is not used: it fails on macOS),
// wall-clock timeout, minimal environment, /usr/bin/python3 -I.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export const PYTHON = '/usr/bin/python3';
const TMP_ROOT = path.join(os.homedir(), 'Documents/run-scripts/p922-container/work'); fs.mkdirSync(TMP_ROOT, { recursive: true });

export function freshDir(tag) { return fs.mkdtempSync(path.join(TMP_ROOT, `p922-${tag.replace(/[^A-Za-z0-9.-]/g, '_')}-`)); }
export function writeFiles(dir, files) { for (const [f, c] of Object.entries(files)) fs.writeFileSync(path.join(dir, f), c); }
export function readFiles(dir) { const o = {}; for (const f of fs.readdirSync(dir).sort()) { const p = path.join(dir, f); if (fs.statSync(p).isFile()) o[f] = fs.readFileSync(p, 'utf8'); } return o; }
export function removeDir(dir) { if (dir.startsWith(TMP_ROOT + path.sep) && path.basename(dir).startsWith('p922-')) fs.rmSync(dir, { recursive: true, force: true }); }

// v1.1: model-written code runs only in the hardened container (same flags as ~/Documents/run-scripts/p34-container,
// fresh mode): python:3.12.15-slim, network none, read-only root, caps dropped, pids 64, 512 MB, 1 CPU, uid 65534.
const DOCKER = '/opt/homebrew/bin/docker'; const IMAGE = 'python:3.12.15-slim';
const HARDEN = ['--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '64',
  '--memory', '512m', '--cpus', '1', '--user', '65534:65534', '--tmpfs', '/tmp:rw,size=16m,mode=1777'];
/** Run `python3 -I <args>` inside dir (mounted at /w). Returns { code, out, timedOut }. */
export function runPython(dir, args, { timeoutMs = 30000 } = {}) {
  fs.chmodSync(dir, 0o777); for (const f of fs.readdirSync(dir)) fs.chmodSync(path.join(dir, f), 0o666);
  const name = `p922v11-${Math.random().toString(16).slice(2, 12)}`;
  const r = spawnSync(DOCKER, ['run', '--rm', '--name', name, ...HARDEN, '-v', `${dir}:/w`, '-w', '/w', '-e', 'HOME=/w', '-e', 'TMPDIR=/tmp',
    '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'LANG=C.UTF-8', '--entrypoint', 'python3', IMAGE, '-I', ...args.map(String)],
    { timeout: timeoutMs + 10000, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
  const timedOut = r.error?.code === 'ETIMEDOUT'; if (timedOut) spawnSync(DOCKER, ['kill', name]);
  return { code: r.status, out: `${r.stdout ?? ''}${r.stderr ?? ''}`, timedOut };
}

/** CI on the given files (pristine CI files are expected to be among them). */
export function runCI(files, tag) {
  const dir = freshDir(tag);
  try { writeFiles(dir, files); const r = runPython(dir, ['ci.py']); return { pass: r.code === 0, out: r.out, timedOut: r.timedOut }; } finally { removeDir(dir); }
}
