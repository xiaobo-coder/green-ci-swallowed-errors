// Paper 922 shared helpers (copied from 921) (no network).
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const sha = (x) => createHash('sha256').update(x).digest('hex');
export const canonical = (x) => Array.isArray(x) ? '[' + x.map(canonical).join(',') + ']'
  : x && typeof x === 'object' ? '{' + Object.keys(x).filter((k) => x[k] !== undefined).sort().map((k) => JSON.stringify(k) + ':' + canonical(x[k])).join(',') + '}'
  : JSON.stringify(x);
export function rng(seed) {
  let h = parseInt(sha(seed).slice(0, 8), 16) >>> 0 || 0x9e3779b9;
  return () => { h ^= h << 13; h >>>= 0; h ^= h >>> 17; h ^= h << 5; h >>>= 0; return h / 4294967296; };
}
export const int = (r, a, b) => a + Math.floor(r() * (b - a + 1));
export const pick = (r, a) => a[Math.floor(r() * a.length)];
export function shuffle(r, a) { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; }
export const words = (s) => (s.match(/\S+/g) ?? []).length;
/** Keep the first n whitespace-separated words of s (deterministic budget enforcement). */
export function firstWords(s, n) { const m = s.match(/\S+\s*/g) ?? []; return m.slice(0, n).join('').trimEnd(); }
export function lastWords(s, n) { const m = s.match(/\S+\s*/g) ?? []; return m.slice(Math.max(0, m.length - n)).join('').trimEnd(); }
/** Normalise an answer for exact-match scoring: lower case, strip spaces/punctuation at the ends, collapse inner spaces. */
export const norm = (s) => String(s ?? '').toLowerCase().replace(/[\s"'`.,;:!?()]+$/g, '').replace(/^[\s"'`.,;:!?()]+/g, '').replace(/\s+/g, ' ');
/** Create a directory that must not exist yet (create-only evidence). */
export function createDir(d) { if (fs.existsSync(d)) throw new Error(`${d} exists (create-only)`); fs.mkdirSync(path.dirname(d), { recursive: true }); fs.mkdirSync(d); }
export const writeNew = (p, s) => fs.writeFileSync(p, s, { flag: 'wx' });
