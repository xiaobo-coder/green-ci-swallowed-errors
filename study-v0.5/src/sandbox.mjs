// Paper 922 code execution for model-written Python (runner side).
// Every execution: fresh directory under the OS temp dir, macOS sandbox-exec profile (network denied, file writes only
// inside that directory and /dev), CPU-time limit via ulimit -t (RLIMIT_AS is not used: it fails on macOS),
// wall-clock timeout, minimal environment, /usr/bin/python3 -I.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export const PYTHON = '/usr/bin/python3';
const TMP_ROOT = fs.realpathSync(os.tmpdir());

export function freshDir(tag) { return fs.mkdtempSync(path.join(TMP_ROOT, `p922-${tag.replace(/[^A-Za-z0-9.-]/g, '_')}-`)); }
export function writeFiles(dir, files) { for (const [f, c] of Object.entries(files)) fs.writeFileSync(path.join(dir, f), c); }
export function readFiles(dir) { const o = {}; for (const f of fs.readdirSync(dir).sort()) { const p = path.join(dir, f); if (fs.statSync(p).isFile()) o[f] = fs.readFileSync(p, 'utf8'); } return o; }
export function removeDir(dir) { if (dir.startsWith(TMP_ROOT + path.sep) && path.basename(dir).startsWith('p922-')) fs.rmSync(dir, { recursive: true, force: true }); }

const profile = (dir) => `(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (subpath "${dir}") (subpath "/dev"))`;

/** Run `python3 -I <args>` inside dir. Returns { code, out, timedOut }. */
export function runPython(dir, args, { timeoutMs = 30000, cpuSeconds = 20 } = {}) {
  const quoted = args.map((a) => `'${String(a).replace(/'/g, `'\\''`)}'`).join(' ');
  const r = spawnSync('/usr/bin/sandbox-exec', ['-p', profile(dir), '/bin/sh', '-c', `ulimit -t ${cpuSeconds}; exec ${PYTHON} -I ${quoted}`], {
    cwd: dir, timeout: timeoutMs, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024,
    env: { PATH: '/usr/bin:/bin', HOME: dir, TMPDIR: dir, PYTHONDONTWRITEBYTECODE: '1', LANG: 'en_US.UTF-8' },
  });
  return { code: r.status, out: `${r.stdout ?? ''}${r.stderr ?? ''}`, timedOut: r.error?.code === 'ETIMEDOUT' };
}

/** CI on the given files (pristine CI files are expected to be among them). */
export function runCI(files, tag) {
  const dir = freshDir(tag);
  try { writeFiles(dir, files); const r = runPython(dir, ['ci.py']); return { pass: r.code === 0, out: r.out, timedOut: r.timedOut }; } finally { removeDir(dir); }
}
