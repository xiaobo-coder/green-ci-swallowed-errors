#!/usr/bin/env python3
"""922 v1.1 POST HOC (not preregistered; written 2026-11-18 after a mock review, before the last model's test ended).
Trivial structural baseline for the detector comparison: flag a trap unit iff the trap function still contains a `try`
with at least one handler that has no `raise` anywhere in its body. Same units and truth as tools/tool_compare.py (reused,
unchanged). Also reports exception-rules-only scoring is NOT recomputed here (default configs keep any finding).
  python3 -I posthoc/trivial_baseline.py --observer OBS --dataset DS --out NEW_DIR"""
import argparse, ast, importlib.util, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location('tc', os.path.join(ROOT, 'tools', 'tool_compare.py')); TC = importlib.util.module_from_spec(spec); spec.loader.exec_module(TC)

def flag(mod, func):
    try: tree = ast.parse(mod)
    except SyntaxError: return False
    f = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if f is None: return False
    return any(not any(isinstance(s, ast.Raise) for s in ast.walk(h)) for t in ast.walk(f) if isinstance(t, ast.Try) for h in t.handlers)

def main():
    ap = argparse.ArgumentParser(); [ap.add_argument(k, required=True) for k in ('--observer', '--dataset', '--out')]; a = ap.parse_args()
    if os.path.exists(a.out): sys.exit('exists (create-only)')
    c = {'TP': 0, 'FP': 0, 'FN': 0, 'TN': 0}; rows = []
    for u in TC.units(a.observer, a.dataset):
        fl = flag(u['module'], u['func']); c[('T' if fl == u['bad'] else 'F') + ('P' if fl else 'N')] += 1
        rows.append({k: u[k] for k in ('model', 'cond', 'task', 'key', 'bad')} | {'trivial': fl})
    tp, fp, fn, tn = c['TP'], c['FP'], c['FN'], c['TN']
    prec = tp / (tp + fp) if tp + fp else None; rec = tp / (tp + fn) if tp + fn else None
    res = {**c, 'precision': prec, 'recall': rec, 'f1': (2 * prec * rec / (prec + rec)) if prec and rec else 0.0, 'falseAlarmRate': fp / (fp + tn) if fp + tn else None, 'units': len(rows), 'postHoc': True}
    os.makedirs(a.out); json.dump(res, open(os.path.join(a.out, 'trivial.json'), 'x'), indent=1)
    with open(os.path.join(a.out, 'units.jsonl'), 'x') as f: [f.write(json.dumps(r) + '\n') for r in rows]
    print(json.dumps(res))

if __name__ == '__main__': main()
