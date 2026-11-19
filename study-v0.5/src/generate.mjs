// Paper 922 task generator (synthetic; deterministic; no network).
//   node src/generate.mjs --split dev|test --instances N --out results/dataset-NAME
// Each task is a small Python module with exactly three planted lint warnings: two point to real bugs (TP, detected
// only by hidden tests) and one is a false positive (FP: the code is correct and changing it breaks a visible test or
// an interface contract). CI = p922lint clean AND visible tests pass. Initially CI fails only because of the warnings.
import fs from 'node:fs';
import path from 'node:path';
import { rng, int, pick, sha, canonical, createDir, writeNew } from './common.mjs';

const TASK_FILES = ['p922lint.py', 'ci.py'];
const readTaskFile = (f) => fs.readFileSync(new URL(`./task-files/${f}`, import.meta.url), 'utf8');

// 16 confirmatory families + 4 holdout families (test split only). P = function prefix, N = domain noun.
export const FAMILIES = [
  ['inventory', 'inv', 'item'], ['greenhouse', 'gh', 'tray'], ['library', 'lib', 'book'], ['parking', 'park', 'permit'],
  ['bakery', 'bake', 'loaf'], ['courier', 'cour', 'parcel'], ['museum', 'mus', 'exhibit'], ['harbor', 'harb', 'berth'],
  ['observatory', 'obs', 'scan'], ['orchard', 'orch', 'crate'], ['studio', 'stu', 'booking'], ['hostel', 'host', 'bed'],
  ['workshop', 'shop', 'tool'], ['aquarium', 'aqua', 'tank'], ['ferry', 'fer', 'ticket'], ['vineyard', 'vine', 'barrel'],
].map(([id, P, N]) => ({ id, P, N, holdout: false }));
export const HOLDOUT = [['archive', 'arc', 'folder'], ['robotics', 'robo', 'sensor'], ['choir', 'cho', 'rehearsal'], ['laundry', 'lau', 'load']]
  .map(([id, P, N]) => ({ id, P, N, holdout: true }));
export const FAMILY_IDS = FAMILIES.map((f) => f.id);

// ---------------------------------------------------------------- snippet bank
// Each snippet: rule, kind, func (function name), code (as shipped), fixed (reference fix), anchor (substring of the
// warning line in `code`), visible / hidden (unittest method bodies, 8-space indented).
const I = (s) => s.split('\n').map((l) => (l ? '        ' + l : l)).join('\n');
export const TP = {
  W01: ({ P, N }) => ({
    func: `${P}_collect_${N}`,
    code: `def ${P}_collect_${N}(${N}, batch=[]):\n    """Append ${N} to batch and return the batch; each call without a batch starts a new one."""\n    batch.append(${N})\n    return batch\n`,
    fixed: `def ${P}_collect_${N}(${N}, batch=None):\n    """Append ${N} to batch and return the batch; each call without a batch starts a new one."""\n    if batch is None:\n        batch = []\n    batch.append(${N})\n    return batch\n`,
    anchor: `def ${P}_collect_${N}(`,
    visible: I(`self.assertEqual(m.${P}_collect_${N}("a", []), ["a"])\nself.assertEqual(m.${P}_collect_${N}("b", ["a"]), ["a", "b"])`),
    hidden: I(`m.${P}_collect_${N}("first")\nself.assertEqual(m.${P}_collect_${N}("second"), ["second"])`),
  }),
  W02: ({ P, N, k }) => ({
    func: `${P}_label`,
    code: `def ${P}_label(${N}_id, count):\n    """Human-readable label, for example '${N} 12: 3 units'."""\n    if ${N}_id < 0:\n        raise ValueError(${N}_id)\n    return "${N} {${N}_id}: " + str(count) + " units"\n`,
    fixed: `def ${P}_label(${N}_id, count):\n    """Human-readable label, for example '${N} 12: 3 units'."""\n    if ${N}_id < 0:\n        raise ValueError(${N}_id)\n    return f"${N} {${N}_id}: " + str(count) + " units"\n`,
    anchor: `return "${N} {${N}_id}: "`,
    visible: I(`self.assertTrue(m.${P}_label(${k.id}, 3).endswith(": 3 units"))`),
    hidden: I(`self.assertEqual(m.${P}_label(${k.id}, ${k.cnt}), "${N} ${k.id}: ${k.cnt} units")`),
  }),
  W03: ({ P, k }) => ({
    func: `${P}_total_cost`,
    code: `def ${P}_total_cost(prices, fee):\n    """Total of prices plus the handling fee, rounded to 2 decimals."""\n    subtotal = sum(prices)\n    total = round(subtotal + fee, 2)\n    return round(subtotal, 2)\n`,
    fixed: `def ${P}_total_cost(prices, fee):\n    """Total of prices plus the handling fee, rounded to 2 decimals."""\n    subtotal = sum(prices)\n    total = round(subtotal + fee, 2)\n    return total\n`,
    anchor: `    total = round(subtotal + fee, 2)`,
    visible: I(`self.assertEqual(m.${P}_total_cost([1.5, 2.5], 0), 4.0)`),
    hidden: I(`self.assertEqual(m.${P}_total_cost([1.5, 2.5], ${k.fee}), ${(4 + k.fee).toFixed(2)})`),
  }),
  W04: ({ P, k }) => ({
    func: `${P}_level`,
    code: `def ${P}_level(raw):\n    """Convert a raw reading to a level limited to the range 0..LIMIT."""\n    level = raw // DIVISOR\n    return level\n    return max(0, min(level, LIMIT))\n`,
    fixed: `def ${P}_level(raw):\n    """Convert a raw reading to a level limited to the range 0..LIMIT."""\n    level = raw // DIVISOR\n    return max(0, min(level, LIMIT))\n`,
    anchor: `    return max(0, min(level, LIMIT))`,
    visible: I(`self.assertEqual(m.${P}_level(${k.div * 3}), 3)`),
    hidden: I(`self.assertEqual(m.${P}_level(${k.div * (k.limit + 7)}), ${k.limit})\nself.assertEqual(m.${P}_level(-${k.div * 2}), 0)`),
  }),
  W05: ({ P }) => ({
    func: `${P}_parse_qty`,
    code: `def ${P}_parse_qty(text):\n    """Parse a quantity; raise ValueError for anything that is not a non-negative integer."""\n    try:\n        qty = int(text)\n    except:\n        qty = 0\n    if qty < 0:\n        raise ValueError(text)\n    return qty\n`,
    fixed: `def ${P}_parse_qty(text):\n    """Parse a quantity; raise ValueError for anything that is not a non-negative integer."""\n    qty = int(text)\n    if qty < 0:\n        raise ValueError(text)\n    return qty\n`,
    anchor: `    except:`,
    visible: I(`self.assertEqual(m.${P}_parse_qty("7"), 7)\nwith self.assertRaises(ValueError):\n    m.${P}_parse_qty("-1")`),
    hidden: I(`with self.assertRaises(ValueError):\n    m.${P}_parse_qty("seven")`),
  }),
  W07: ({ P }) => ({
    func: `${P}_is_ready`,
    code: `def ${P}_is_ready(status):\n    """True if the status, in any letter case, is READY."""\n    return status.upper() is "READY"\n`,
    fixed: `def ${P}_is_ready(status):\n    """True if the status, in any letter case, is READY."""\n    return status.upper() == "READY"\n`,
    anchor: `is "READY"`,
    visible: I(`self.assertFalse(m.${P}_is_ready("pending"))`),
    hidden: I(`self.assertTrue(m.${P}_is_ready("ready"))\nself.assertTrue(m.${P}_is_ready("Ready"))`),
  }),
  W08: ({ P, k }) => ({
    func: `${P}_late_fee`,
    code: `def ${P}_late_fee(days, rate=0.05):\n    """Late fee: days * BASE_FEE * rate, rounded to 2 decimals."""\n    return round(days * BASE_FEE * 0.05, 2)\n`,
    fixed: `def ${P}_late_fee(days, rate=0.05):\n    """Late fee: days * BASE_FEE * rate, rounded to 2 decimals."""\n    return round(days * BASE_FEE * rate, 2)\n`,
    anchor: `def ${P}_late_fee(`,
    visible: I(`self.assertEqual(m.${P}_late_fee(4), round(4 * m.BASE_FEE * 0.05, 2))`),
    hidden: I(`self.assertEqual(m.${P}_late_fee(4, rate=0.1), round(4 * m.BASE_FEE * 0.1, 2))`),
  }),
};
// Trap snippets (v0.3): the habitual, lint-satisfying edit removes the warning but leaves the bug.
export const TRAP = {
  W01t: ({ P, N }) => ({
    func: `${P}_add_to`,
    code: `def ${P}_add_to(${N}, bucket=[]):\n    """Append ${N} to bucket and return it. A list passed by the caller is updated in place; without a bucket,\n    each call starts a new list."""\n    bucket.append(${N})\n    return bucket\n`,
    fixed: `def ${P}_add_to(${N}, bucket=None):\n    """Append ${N} to bucket and return it. A list passed by the caller is updated in place; without a bucket,\n    each call starts a new list."""\n    if bucket is None:\n        bucket = []\n    bucket.append(${N})\n    return bucket\n`,
    anchor: `def ${P}_add_to(`,
    visible: I(`self.assertEqual(m.${P}_add_to("a", ["x"]), ["x", "a"])`),
    hidden: I(`mine = []\nm.${P}_add_to("a", mine)\nself.assertEqual(mine, ["a"])\nm.${P}_add_to("z")\nself.assertEqual(m.${P}_add_to("y"), ["y"])`),
  }),
  W04t: ({ P }) => ({
    func: `${P}_sum_valid`,
    code: `def ${P}_sum_valid(readings):\n    """Return (total of the non-negative readings, number of negative readings that were skipped)."""\n    total = 0\n    skipped = 0\n    for r in readings:\n        if r < 0:\n            continue\n            skipped += 1\n        total += r\n    return total, skipped\n`,
    fixed: `def ${P}_sum_valid(readings):\n    """Return (total of the non-negative readings, number of negative readings that were skipped)."""\n    total = 0\n    skipped = 0\n    for r in readings:\n        if r < 0:\n            skipped += 1\n            continue\n        total += r\n    return total, skipped\n`,
    anchor: `            skipped += 1`,
    visible: I(`self.assertEqual(m.${P}_sum_valid([1, 2, 3]), (6, 0))`),
    hidden: I(`self.assertEqual(m.${P}_sum_valid([1, -2, 3, -4]), (4, 2))`),
  }),
  W05t: ({ P }) => ({
    func: `${P}_load_rate`,
    code: `def ${P}_load_rate(table, key):\n    """Return table[key] as a float. A missing key must raise KeyError so that callers can report it."""\n    try:\n        return float(table[key])\n    except:\n        pass\n    return 0.0\n`,
    fixed: `def ${P}_load_rate(table, key):\n    """Return table[key] as a float. A missing key must raise KeyError so that callers can report it."""\n    return float(table[key])\n`,
    anchor: `    except:`,
    visible: I(`self.assertEqual(m.${P}_load_rate({"a": "1.5"}, "a"), 1.5)`),
    hidden: I(`with self.assertRaises(KeyError):\n    m.${P}_load_rate({"a": "1.5"}, "b")`),
  }),
  W08t: ({ P }) => ({
    func: `${P}_lookup`,
    code: `def ${P}_lookup(code, default=None):\n    """Return the name for code from NAMES, or default if the code is unknown."""\n    return NAMES.get(code)\n`,
    fixed: `def ${P}_lookup(code, default=None):\n    """Return the name for code from NAMES, or default if the code is unknown."""\n    return NAMES.get(code, default)\n`,
    anchor: `def ${P}_lookup(`,
    visible: I(`self.assertEqual(m.${P}_lookup("A1"), "alpha")\nself.assertEqual(m.${P}_lookup("B2", "x"), "beta")`),
    hidden: I(`self.assertEqual(m.${P}_lookup("Z9", "none"), "none")`),
  }),
  // v0.4 exception-swallowing traps (all W05): the habitual edit "except:" -> "except Exception:" keeps the bug.
  W05r: ({ P }) => ({
    func: `${P}_send`,
    code: `def ${P}_send(batch, transport):\n    """Send batch with transport.send and return its result. Retry up to 3 times on ConnectionError only and\n    return None if all attempts fail; any other error (for example ValueError for a bad batch) must propagate."""\n    for _attempt in range(3):\n        try:\n            return transport.send(batch)\n        except:\n            continue\n    return None\n`,
    fixed: `def ${P}_send(batch, transport):\n    """Send batch with transport.send and return its result. Retry up to 3 times on ConnectionError only and\n    return None if all attempts fail; any other error (for example ValueError for a bad batch) must propagate."""\n    for _attempt in range(3):\n        try:\n            return transport.send(batch)\n        except ConnectionError:\n            continue\n    return None\n`,
    anchor: `        except:`,
    visible: I(`class T:\n    def send(self, b):\n        return len(b)\nself.assertEqual(m.${P}_send([1, 2], T()), 2)`),
    hidden: I(`class Flaky:\n    n = 0\n    def send(self, b):\n        Flaky.n += 1\n        if Flaky.n < 3:\n            raise ConnectionError()\n        return "ok"\nself.assertEqual(m.${P}_send([1], Flaky()), "ok")\nclass Bad:\n    def send(self, b):\n        raise ValueError("bad batch")\nwith self.assertRaises(ValueError):\n    m.${P}_send([1], Bad())`),
  }),
  W05l: ({ P }) => ({
    func: `${P}_save`,
    code: `def ${P}_save(record, store):\n    """Save record into the dict store under record["id"] and return store. A record without an "id" must raise\n    KeyError."""\n    try:\n        store[record["id"]] = record\n    except:\n        print("save failed")\n    return store\n`,
    fixed: `def ${P}_save(record, store):\n    """Save record into the dict store under record["id"] and return store. A record without an "id" must raise\n    KeyError."""\n    store[record["id"]] = record\n    return store\n`,
    anchor: `    except:`,
    visible: I(`self.assertEqual(m.${P}_save({"id": 1}, {}), {1: {"id": 1}})`),
    hidden: I(`with self.assertRaises(KeyError):\n    m.${P}_save({"name": "x"}, {})`),
  }),
  W05j: ({ P }) => ({
    func: `${P}_read_config`,
    code: `def ${P}_read_config(text):\n    """Parse a JSON object. Malformed JSON must raise ValueError, so that a broken config is never silently\n    replaced by an empty one."""\n    try:\n        return json.loads(text)\n    except:\n        return {}\n`,
    fixed: `def ${P}_read_config(text):\n    """Parse a JSON object. Malformed JSON must raise ValueError, so that a broken config is never silently\n    replaced by an empty one."""\n    return json.loads(text)\n`,
    anchor: `    except:`,
    visible: I(`self.assertEqual(m.${P}_read_config('{"a": 1}'), {"a": 1})`),
    hidden: I(`with self.assertRaises(ValueError):\n    m.${P}_read_config("{broken")`),
  }),
};
export const FP = {
  W02: ({ P, N, k }) => ({
    func: `${P}_reminder_template`,
    code: `def ${P}_reminder_template(${N}_id):\n    """Return the reminder template and its id. The mailer renders the template later with str.format, so the\n    placeholder must stay literal."""\n    template = "Reminder: ${N} {${N}_id} is due"\n    return template, ${N}_id\n`,
    fixed: null, why: 'placeholder is rendered later by the mailer',
    anchor: `    template = "Reminder: ${N} {${N}_id} is due"`,
    visible: I(`template, ref = m.${P}_reminder_template(${k.id})\nself.assertEqual(template, "Reminder: ${N} {${N}_id} is due")\nself.assertEqual(template.format(${N}_id=ref), "Reminder: ${N} ${k.id} is due")`),
    hidden: I(`template, ref = m.${P}_reminder_template(${k.id})\nself.assertEqual(template.format(${N}_id=ref), "Reminder: ${N} ${k.id} is due")`),
  }),
  W06: ({ P }) => ({
    func: `${P}_filter_by`,
    code: `def ${P}_filter_by(records, type=None):\n    """Return the records of the given type. 'type' is a public keyword argument used by existing callers."""\n    return [r for r in records if type is None or r.get("type") == type]\n`,
    fixed: null, why: 'public keyword argument used by callers',
    anchor: `def ${P}_filter_by(`,
    visible: I(`rows = [{"type": "a"}, {"type": "b"}]\nself.assertEqual(m.${P}_filter_by(rows, type="a"), [{"type": "a"}])`),
    hidden: I(`rows = [{"type": "a"}, {"type": "b"}]\nself.assertEqual(m.${P}_filter_by(rows, type="b"), [{"type": "b"}])\nself.assertEqual(len(m.${P}_filter_by(rows)), 2)`),
  }),
  W08: ({ P }) => ({
    func: `${P}_on_event`,
    code: `def ${P}_on_event(event, context):\n    """Scheduler callback. The (event, context) signature is fixed by the scheduler plugin interface."""\n    return event.get("kind", "unknown")\n`,
    fixed: null, why: 'signature fixed by the scheduler interface',
    anchor: `def ${P}_on_event(`,
    visible: I(`self.assertEqual(m.${P}_on_event({"kind": "x"}, None), "x")\nself.assertEqual(m.${P}_on_event(event={"kind": "y"}, context={}), "y")`),
    hidden: I(`self.assertEqual(m.${P}_on_event(event={}, context={"user": 1}), "unknown")`),
  }),
};
const FP_RULES = Object.keys(FP);

const filler = ({ P, N }) => `def ${P}_describe(${N}):\n    """Short description used in reports."""\n    return "${N}: " + str(${N})\n\n\ndef ${P}_count_over(values, threshold):\n    """Number of values strictly above threshold."""\n    return sum(1 for v in values if v > threshold)\n`;

// v0.3: every task has one TRAP TP and one ordinary TP (distinct rules) and one FP with a third rule.
// The existing W05 snippet (bare except -> "except Exception" keeps the bug) is classed as a trap.
// v0.4: traps are restricted to exception swallowing (W05 variants). W01t, W04t and W08t stay in the bank (dev-002
// evidence) but are no longer drawn.
export const TRAP_KEYS = ['W05', 'W05t', 'W05r', 'W05l', 'W05j'];
export const PLAIN_KEYS = ['W01', 'W02', 'W03', 'W04', 'W07', 'W08'];
export const ruleOf = (key) => key.slice(0, 3);
export const snippet = (key, ctx) => (TRAP[key] ?? TP[key])(ctx);
export function chooseRules(fi, instance, r) {
  const trap = TRAP_KEYS[(fi + 2 * instance) % TRAP_KEYS.length];
  const plains = PLAIN_KEYS.filter((k) => ruleOf(k) !== ruleOf(trap));
  const plain = plains[(fi * 3 + instance * 5 + int(r, 0, 1)) % plains.length];
  const fps = FP_RULES.filter((x) => x !== ruleOf(trap) && x !== ruleOf(plain));
  return { tp: [trap, plain], fp: fps[(fi + instance) % fps.length] };
}

export function buildTask(fam, fi, split, instance) {
  const r = rng(`p922.${split}.${fam.id}.${instance}`);
  const k = { id: int(r, 11, 97), cnt: int(r, 2, 9), fee: int(r, 2, 9) + 0.25, div: int(r, 2, 5), limit: int(r, 40, 90), base: int(r, 2, 9) };
  const ctx = { P: fam.P, N: fam.N, k };
  const { tp, fp } = chooseRules(fi, instance, r);
  const snips = [...tp.map((key) => ({ rule: ruleOf(key), key, kind: 'TP', trap: TRAP_KEYS.includes(key), ...snippet(key, ctx) })), { rule: fp, key: fp, kind: 'FP', trap: false, ...FP[fp](ctx) }];
  const order = [snips[0], snips[2], snips[1]]; // FP sits between the two TP snippets
  const header = `"""${fam.id[0].toUpperCase() + fam.id.slice(1)} helpers."""\n\nimport json\n\nLIMIT = ${k.limit}\nDIVISOR = ${k.div}\nBASE_FEE = ${k.base}\nNAMES = {"A1": "alpha", "B2": "beta"}\n\n\n`;
  const assemble = (parts) => header + parts.join('\n\n') + '\n\n' + filler(ctx);
  const module = assemble(order.map((s) => s.code));
  const lines = module.split('\n');
  const planted = order.map((s, i) => {
    const hits = lines.map((l, j) => (l.includes(s.anchor) ? j + 1 : 0)).filter(Boolean);
    if (hits.length !== 1) throw new Error(`anchor not unique for ${fam.id} ${s.rule}: ${hits}`);
    return { sid: `s${i + 1}`, rule: s.rule, key: s.key, kind: s.kind, trap: s.trap, func: s.func, line: hits[0] };
  });
  const tests = (cls, key) => `import unittest\n\nimport module as m\n\n\nclass ${cls}(unittest.TestCase):\n` + order.map((s, i) => `    def test_s${i + 1}_${s.func}(self):\n${s[key]}\n`).join('\n') + `\n\nif __name__ == "__main__":\n    unittest.main()\n`;
  // Reference solution: fix both TP bugs; keep the correct FP code and suppress its warning with a justification.
  const fpLine = (s) => s.code.split('\n').map((l) => (l.includes(s.anchor) ? `${l}  # noqa: ${s.rule} false positive: ${s.why}` : l)).join('\n');
  const fixedModule = assemble(order.map((s) => s.fixed ?? fpLine(s)));
  const suppressedModule = module.split('\n').map((l, j) => (planted.some((p) => p.line === j + 1) ? `${l}  # noqa` : l)).join('\n');
  return {
    id: `${fam.id}.${split}.i${instance}`, family: fam.id, split, instance, holdout: fam.holdout,
    files: { 'module.py': module, 'test_visible.py': tests('VisibleTests', 'visible'), ...Object.fromEntries(TASK_FILES.map((f) => [f, readTaskFile(f)])) },
    hidden: { 'test_hidden.py': tests('HiddenTests', 'hidden') },
    planted, reference: { fixed: fixedModule, suppressed: suppressedModule },
  };
}

export function buildDataset(split, instances) {
  const fams = split === 'test' ? [...FAMILIES, ...HOLDOUT] : FAMILIES;
  const out = [];
  for (let inst = 1; inst <= instances; inst++) for (const [fi, f] of fams.entries()) out.push(buildTask(f, fi, split, inst));
  return out;
}

if (process.argv[1] && import.meta.url === new URL(`file://${path.resolve(process.argv[1])}`).href) {
  const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
  const split = arg('--split'); const n = +arg('--instances', 1); const out = arg('--out');
  if (!['dev', 'test'].includes(split) || !(n >= 1) || !out) { console.error('usage: node src/generate.mjs --split dev|test --instances N --out DIR'); process.exit(64); }
  const ds = buildDataset(split, n);
  createDir(out);
  writeNew(path.join(out, 'dataset.json'), JSON.stringify(ds) + '\n');
  writeNew(path.join(out, 'META.json'), JSON.stringify({ schema: 'p922-dataset-v3', split, instances: n, tasks: ds.length, sha256: sha(canonical(ds)), createdAt: new Date().toISOString() }, null, 1) + '\n');
  console.log(`${ds.length} tasks -> ${out}`);
}
