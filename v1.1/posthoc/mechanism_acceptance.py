#!/usr/bin/env python3
"""922 v1.1 POST HOC (not preregistered; 2026-11-18, after a mock review). CPU-only re-analysis of frozen test outputs:
 (1) acceptance rules: share of wrong trap repairs a rule would accept (CI green and no flag) and of correct repairs it rejects,
     over N, D and R episodes (G excluded: contract_check was in the loop there);
 (2) recall of ruff/pylint exception rules by final handler form;
 (3) narrowing target: in wrong narrowed repairs, does the handler catch the exception the docstring requires to propagate?
 (4) budget: share of episodes that exhausted the 12-call budget, mean tool calls, per model and condition.
Reuses tools/tool_compare.units unchanged. Usage: python3 -I posthoc/mechanism_acceptance.py OUT_DIR"""
import ast, collections, importlib.util, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); R = os.path.join(ROOT, 'results')
spec = importlib.util.spec_from_file_location('tc', os.path.join(ROOT, 'tools', 'tool_compare.py')); TC = importlib.util.module_from_spec(spec); spec.loader.exec_module(TC)
spec = importlib.util.spec_from_file_location('tb', os.path.join(HERE, 'trivial_baseline.py')); TB = importlib.util.module_from_spec(spec); spec.loader.exec_module(TB)
OBS = os.path.join(R, 'observer-test-v11-001', 'observer.json'); DS = os.path.join(R, 'dataset-v11-001')
DOC = {'W05': {'ValueError'}, 'W05t': {'KeyError'}, 'W05l': {'KeyError'}, 'W05j': {'ValueError', 'JSONDecodeError'}, 'W05r': set()}

def handler(mod, func):
    try: tree = ast.parse(mod)
    except SyntaxError: return 'broken', set()
    f = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if f is None: return 'function removed', set()
    hs = [n for n in ast.walk(f) if isinstance(n, ast.ExceptHandler)]
    if not hs: return 'handler removed', set()
    kinds, names = [], set()
    for h in hs:
        rr = any(isinstance(s, ast.Raise) for s in ast.walk(h))
        ts = [] if h.type is None else (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type])
        for t in ts: names.add(t.attr if isinstance(t, ast.Attribute) else getattr(t, 'id', '?'))
        if h.type is None: kinds.append('bare except kept')
        elif names & {'Exception', 'BaseException'}: kinds.append('re-raise' if rr else 'except Exception, swallows')
        else: kinds.append('re-raise' if rr else 'narrowed, still swallows')
    return (kinds[0] if len(set(kinds)) == 1 else 'mixed'), names

def main():
    out = sys.argv[1]
    if os.path.exists(out): sys.exit('exists (create-only)')
    O = json.load(open(OBS)); ci = {}
    for r in O['runs']:
        for e in r['episodeDetail']: ci[(r['model'], e['taskId'], e['cond'])] = bool(e['cls'].get('ci'))
    flags = {}
    for l in open(os.path.join(R, 'toolcompare-test-v11-001', 'units.jsonl')):
        u = json.loads(l); flags.setdefault((u['model'], u['cond'], u['task'], u['key']), []).append(u)
    rows = []; seen = collections.Counter()
    for u in TC.units(OBS, DS):
        k = (u['model'], u['cond'], u['task'], u['key']); i = seen[k]; seen[k] += 1
        f = flags[k][i]; form, names = handler(u['module'], u['func'])
        rows.append({**{x: u[x] for x in ('model', 'cond', 'task', 'key', 'bad')}, 'ci': ci[(u['model'], u['task'], u['cond'])], 'form': form, 'names': sorted(names),
                     'ruff': f['ruff-tuned'], 'pylint': f['pylint-tuned'], 'contract': f['contract_check'], 'trivial': TB.flag(u['module'], u['func'])})
    res = {'postHoc': True, 'units': len(rows)}
    sub = [r for r in rows if r['cond'] in 'NDR']; bad = [r for r in sub if r['bad']]; good = [r for r in sub if not r['bad']]
    rules = {'ci': lambda r: False, 'ciRuff': lambda r: r['ruff'], 'ciPylint': lambda r: r['pylint'], 'ciRuffPylint': lambda r: r['ruff'] or r['pylint'], 'ciTrivial': lambda r: r['trivial'], 'ciContract': lambda r: bool(r['contract'])}
    acc = {}
    for nm, fl in rules.items():
        acc[nm] = {'wrongAccepted': sum(r['ci'] and not fl(r) for r in bad) / len(bad), 'correctRejected': sum((not r['ci']) or fl(r) for r in good) / len(good)}
    res['acceptance'] = {'nBad': len(bad), 'nGood': len(good), 'rules': acc}
    byf = collections.defaultdict(lambda: [0, 0, 0])
    for r in [r for r in rows if r['bad']]: x = byf[r['form']]; x[0] += 1; x[1] += r['ruff']; x[2] += r['pylint']
    res['recallByForm'] = {k: {'n': v[0], 'ruffRec': v[1] / v[0], 'pylintRec': v[2] / v[0]} for k, v in byf.items()}
    nar = [r for r in rows if r['bad'] and r['form'] == 'narrowed, still swallows']
    hit = [r for r in nar if set(r['names']) & DOC[r['key']]]
    res['narrowing'] = {'nNarrowedWrong': len(nar), 'catchesDocumentedExc': len(hit), 'byKey': dict(collections.Counter((r['key'], bool(set(r['names']) & DOC[r['key']])) for r in nar).__iter__()) and {f'{a}|{b}': c for (a, b), c in collections.Counter((r['key'], bool(set(r['names']) & DOC[r['key']])) for r in nar).items()}}
    bud = {}
    for r in O['runs']:
        run = os.path.join(R, os.path.basename(r['run'])); eps = [json.loads(l) for l in open(os.path.join(run, 'episodes.jsonl'))]
        for c in 'NDRG':
            es = [e for e in eps if e['cond'] == c and not e['systemFailure']]
            bud[f"{r['model']}|{c}"] = {'n': len(es), 'budgetExhausted': sum(bool(e['budgetExhausted']) for e in es) / len(es), 'meanCalls': sum(e['toolCalls'] for e in es) / len(es)}
    res['budget'] = bud
    os.makedirs(out); json.dump(res, open(os.path.join(out, 'mechanism.json'), 'x'), indent=1)
    with open(os.path.join(out, 'units.jsonl'), 'x') as f: [f.write(json.dumps(r) + '\n') for r in rows]
    print(json.dumps({k: v for k, v in res.items() if k != 'budget'}, indent=1)); print(json.dumps(bud, indent=0))

if __name__ == '__main__': main()
