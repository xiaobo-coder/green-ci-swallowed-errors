#!/usr/bin/env python3
"""DEVELOPMENT evaluation of src/task-files/contract_check.py on the frozen v0.5 test-001 final modules (already reported
data, used here only as development data for the checker; not a result). Per trap warning: flagged = a C01 finding inside the
trap function; bad = the observer's hidden test for that warning failed. Prints precision/recall and per-pattern counts.
  python3 -I v1.1/tools/eval_contract_dev.py"""
import ast, collections, importlib.util, json, os
spec = importlib.util.spec_from_file_location('cc', 'v1.1/src/task-files/contract_check.py'); cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
O = json.load(open('study-v0.5/results/observer-test-001/observer.json'))
ds = {t['id']: t for t in json.load(open('study-v0.5/results/dataset-test-001/dataset.json'))}
C = collections.Counter(); K = collections.Counter()
for r in O['runs']:
    epf = os.path.join('study-v0.5', r['run'], 'episodes.jsonl')
    if not os.path.exists(epf): epf = os.path.join(r['run'], 'episodes.jsonl')
    mods = {(j['taskId'], j['cond']): j['finalModule'] for j in map(json.loads, open(epf))}
    for e in r['episodeDetail']:
        if e['systemFailure']: continue
        t = ds[e['taskId']]; mod = mods.get((e['taskId'], e['cond']))
        try: tree = ast.parse(mod)
        except Exception: continue
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}; found = cc.check(mod)
        for w in e['cls']['warnings']:
            p = next(p for p in t['planted'] if p['sid'] == w['sid']); f = fns.get(p['func'])
            if not f: continue
            flag = any(f.lineno <= ln <= f.end_lineno for ln, c, _ in found if c == 'C01'); bad = not w['hiddenPass']
            grp = 'trap' if w['trap'] else 'other'
            C[(grp, bad, flag)] += 1
            if w['trap']: K[(p['key'], 'bad' if bad else 'ok', 'flag' if flag else '-')] += 1
for g in ('trap', 'other'):
    tp, fp, fn = C[(g, True, True)], C[(g, False, True)], C[(g, True, False)]
    print(g, 'TP', tp, 'FP', fp, 'FN', fn, 'TN', C[(g, False, False)], 'precision %.3f recall %.3f' % (tp / max(tp + fp, 1), tp / max(tp + fn, 1)))
for k, v in sorted(K.items()): print(k, v)
print('original modules flagged', sum(1 for t in ds.values() if any(c == 'C01' for _, c, _ in cc.check(t['files']['module.py']))), '/', len(ds))
print('reference-fixed modules flagged', sum(1 for t in ds.values() if cc.check(t['reference']['fixed'])))
