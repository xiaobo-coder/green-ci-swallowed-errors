#!/usr/bin/env python3
"""922 v1.1 independent detector comparison (ADDENDUM-v1.1 §5b). Question: given an agent's final module, does a detector flag
the exception-handling trap function when (and only when) its documented behavior is broken (hidden test fails)?

Unit: one trap warning in one non-failed episode. Truth: `bad` = the observer's hidden test for that trap failed.
A detector "flags" the unit iff it reports at least one finding whose line lies inside a `try` statement of the trap
function (same criterion for every detector). Detectors (each in a default and, where it has one, a tuned configuration
fixed in advance; no detector sees hidden tests):
  p922lint        the study's own CI linter (any finding)
  ruff-default    ruff check --isolated (ruff's default rule set)
  ruff-tuned      ruff check --isolated --select E722,BLE001,S110,S112,SIM105,PERF203,TRY (its exception-handling rules)
  pylint-default  pylint with its default checks (all messages)
  pylint-tuned    pylint --disable=all --enable=W0702,W0718,W0706,W0705,E0701 (its exception-handling messages)
  semgrep         Semgrep 1.136.0 with the official registry packs p/python, p/bandit, p/r2c-best-practices (pinned, offline)
  contract_check  the contract-guarded CI checker (C01 findings)
  boosting        gradient-boosted trees on generic AST features of the trap function, hyper-parameters tuned by 5-fold
                  grouped CV on the DEVELOPMENT data only (v0.5 test-001 final modules); trained once, then applied
Metrics per detector: TP, FP, FN, TN, precision, recall, F1, false-alarm rate on correct repairs, run time per module.
Training/selection never uses v1.1 data. Create-only output.
  ~/Documents/venvs/p922tools/bin/python -I tools/tool_compare.py --dev-observer ../study-v0.5/results/observer-test-001/observer.json \
     --dev-dataset ../study-v0.5/results/dataset-test-001 --observer results/observer-test-v11-001/observer.json \
     --dataset results/dataset-v11-001 --out results/toolcompare-test-v11-001"""
import argparse, ast, hashlib, importlib.util, json, os, re, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
VENV = os.path.expanduser('~/Documents/venvs/p922tools/bin')
RUFF_TUNED = 'E722,BLE001,S110,S112,SIM105,PERF203,TRY'
PYLINT_TUNED = 'W0702,W0718,W0706,W0705,E0701'
spec = importlib.util.spec_from_file_location('cc', os.path.join(ROOT, 'src', 'task-files', 'contract_check.py')); CC = importlib.util.module_from_spec(spec); spec.loader.exec_module(CC)
spec = importlib.util.spec_from_file_location('lint', os.path.join(ROOT, 'src', 'task-files', 'p922lint.py')); LINT = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(LINT)
except SystemExit: pass


def units(observer_path, dataset_dir):
    """Yield (group, key, module, func, bad) per trap warning of every non-failed episode."""
    O = json.load(open(observer_path)); base = os.path.dirname(os.path.dirname(os.path.abspath(observer_path)))
    ds = {t['id']: t for t in json.load(open(os.path.join(dataset_dir, 'dataset.json')))}
    for r in O['runs']:
        run = r['run'] if os.path.isabs(r['run']) else os.path.join(os.path.dirname(base), r['run'])
        if not os.path.exists(os.path.join(run, 'episodes.jsonl')): run = os.path.join(base, os.path.basename(r['run']))
        mods = {(j['taskId'], j['cond']): j['finalModule'] for j in map(json.loads, open(os.path.join(run, 'episodes.jsonl')))}
        for e in r['episodeDetail']:
            if e['systemFailure']: continue
            t = ds[e['taskId']]; mod = mods.get((e['taskId'], e['cond']))
            if not mod: continue
            for w in e['cls']['warnings']:
                if not w['trap']: continue
                p = next(p for p in t['planted'] if p['sid'] == w['sid'])
                yield {'group': e['family'], 'model': r['model'], 'cond': e['cond'], 'task': e['taskId'], 'key': p['key'], 'module': mod, 'func': p['func'], 'bad': not w['hiddenPass']}


def try_spans(mod, func):
    try: tree = ast.parse(mod)
    except SyntaxError: return None
    f = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if f is None: return None
    return [(n.lineno, n.end_lineno) for n in ast.walk(f) if isinstance(n, ast.Try)]


def lines_ruff(mod, select=None):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'module.py'); open(p, 'w').write(mod)
        cmd = [os.path.join(VENV, 'ruff'), 'check', '--isolated', '--output-format', 'json', '--no-cache'] + (['--select', select] if select else []) + [p]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    try: return [x['location']['row'] for x in json.loads(out or '[]')]
    except Exception: return []


def lines_pylint(mod, enable=None):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'module.py'); open(p, 'w').write(mod)
        cmd = [os.path.join(VENV, 'pylint'), '--output-format=json', '--score=n', '--persistent=n'] + (['--disable=all', '--enable=' + enable] if enable else []) + [p]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=d).stdout
    try: return [x['line'] for x in json.loads(out or '[]')]
    except Exception: return []


SEMGREP_RULES = ['p-python.yaml', 'p-bandit.yaml', 'p-r2c-best-practices.yaml']   # official registry packs, pinned (tools/semgrep/SHA256SUMS)


def semgrep_batch(mods):
    """Run Semgrep once over all modules (offline, metrics off); returns {index: [finding lines]}."""
    out = {i: [] for i in range(len(mods))}
    with tempfile.TemporaryDirectory() as d:
        for i, m in enumerate(mods): open(os.path.join(d, 'u%05d.py' % i), 'w').write(m)
        cmd = [os.path.join(VENV, 'semgrep'), '--metrics=off', '--disable-version-check', '--json', '--quiet', '--no-git-ignore']
        for r in SEMGREP_RULES: cmd += ['--config', os.path.join(HERE, 'semgrep', r)]
        res = subprocess.run(cmd + [d], capture_output=True, text=True, timeout=3600).stdout
        for r in json.loads(res or '{"results": []}').get('results', []):
            i = int(os.path.basename(r['path'])[1:6]); out[i].append(r['start']['line'])
    return out


def lines_p922lint(mod):
    try: return [l for l, _c, _s in LINT.lint(mod)]
    except Exception: return []


def lines_contract(mod):
    return [l for l, c, _ in CC.check(mod) if c == 'C01']


FEATS = ['n_try', 'n_handlers', 'bare', 'broad', 'specific', 'handler_raises', 'handler_returns_const', 'handler_pass_or_continue',
         'handler_assigns', 'doc_mentions_raise', 'doc_mentions_propagate', 'n_doc_exc', 'handler_catches_doc_exc', 'stmt_after_try_return']


def features(mod, func):
    z = dict.fromkeys(FEATS, 0)
    try: tree = ast.parse(mod)
    except SyntaxError: return [z[k] for k in FEATS]
    f = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if f is None: return [z[k] for k in FEATS]
    doc = ast.get_docstring(f) or ''; docexc = set(re.findall(r'\b([A-Z]\w*(?:Error|Exception))\b', doc))
    z['doc_mentions_raise'] = int(bool(re.search(r'\braise', doc, re.I))); z['doc_mentions_propagate'] = int('propagate' in doc); z['n_doc_exc'] = len(docexc)
    for t in (n for n in ast.walk(f) if isinstance(n, ast.Try)):
        z['n_try'] += 1
        for h in t.handlers:
            z['n_handlers'] += 1; names = [] if h.type is None else [getattr(e, 'id', getattr(e, 'attr', '')) for e in (h.type.elts if isinstance(h.type, ast.Tuple) else [h.type])]
            z['bare'] += h.type is None; z['broad'] += any(n in ('Exception', 'BaseException') for n in names); z['specific'] += bool(names) and not any(n in ('Exception', 'BaseException') for n in names)
            body = ast.Module(body=h.body, type_ignores=[]); kinds = [type(n).__name__ for n in ast.walk(body)]
            z['handler_raises'] += 'Raise' in kinds; z['handler_pass_or_continue'] += ('Pass' in kinds or 'Continue' in kinds) and 'Raise' not in kinds
            z['handler_returns_const'] += any(isinstance(n, ast.Return) and isinstance(n.value, (ast.Constant, ast.Dict, ast.List)) for n in ast.walk(body))
            z['handler_assigns'] += 'Assign' in kinds; z['handler_catches_doc_exc'] += any(n in docexc for n in names)
    z['stmt_after_try_return'] = int(any(isinstance(n, ast.Return) for n in f.body[-1:]))
    return [z[k] for k in FEATS]


def main():
    ap = argparse.ArgumentParser()
    for k in ('--dev-observer', '--dev-dataset', '--observer', '--dataset', '--out'): ap.add_argument(k, required=True)
    a = ap.parse_args()
    if os.path.exists(a.out): sys.exit('exists (create-only)')
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import GridSearchCV, GroupKFold
    dev = list(units(a.dev_observer, a.dev_dataset)); test = list(units(a.observer, a.dataset))
    X = np.array([features(u['module'], u['func']) for u in dev]); y = np.array([u['bad'] for u in dev]); g = [u['group'] for u in dev]
    grid = {'n_estimators': [50, 100, 200], 'max_depth': [1, 2, 3], 'learning_rate': [0.05, 0.1, 0.3]}
    gs = GridSearchCV(GradientBoostingClassifier(random_state=922), grid, cv=GroupKFold(n_splits=5), scoring='f1').fit(X, y, groups=g)
    model = gs.best_estimator_
    detectors = {'p922lint': lines_p922lint, 'ruff-default': lambda m: lines_ruff(m), 'ruff-tuned': lambda m: lines_ruff(m, RUFF_TUNED),
                 'pylint-default': lambda m: lines_pylint(m), 'pylint-tuned': lambda m: lines_pylint(m, PYLINT_TUNED), 'contract_check': lines_contract}
    res = {k: {'TP': 0, 'FP': 0, 'FN': 0, 'TN': 0, 'sec': 0.0} for k in list(detectors) + ['semgrep', 'boosting']}
    t0 = time.time(); SG = semgrep_batch([u['module'] for u in test]); res['semgrep']['sec'] = time.time() - t0
    rows = []
    for u in test:
        spans = try_spans(u['module'], u['func']); row = {k: u[k] for k in ('model', 'cond', 'task', 'key', 'bad')}
        for name, fn in detectors.items():
            if name == 'contract_check' and u['cond'] == 'G':   # in the loop under G (agents saw its output): excluded from its scores
                row[name] = None; continue
            t0 = time.time(); ls = fn(u['module']); res[name]['sec'] += time.time() - t0
            flag = bool(spans) and any(s <= l <= e for l in ls for s, e in spans); row[name] = flag
            res[name][('TP' if u['bad'] else 'FP') if flag else ('FN' if u['bad'] else 'TN')] += 1
        flag = bool(spans) and any(s_ <= l <= e_ for l in SG[len(rows)] for s_, e_ in spans); row['semgrep'] = flag
        res['semgrep'][('TP' if u['bad'] else 'FP') if flag else ('FN' if u['bad'] else 'TN')] += 1
        t0 = time.time(); flag = bool(model.predict(np.array([features(u['module'], u['func'])]))[0]); res['boosting']['sec'] += time.time() - t0
        row['boosting'] = flag; res['boosting'][('TP' if u['bad'] else 'FP') if flag else ('FN' if u['bad'] else 'TN')] += 1
        rows.append(row)
    for k, r in res.items():
        tp, fp, fn, tn = r['TP'], r['FP'], r['FN'], r['TN']
        r['precision'] = tp / (tp + fp) if tp + fp else None; r['recall'] = tp / (tp + fn) if tp + fn else None
        r['f1'] = 2 * tp / (2 * tp + fp + fn) if tp else 0.0; r['falseAlarmRate'] = fp / (fp + tn) if fp + tn else None
        r['secPerModule'] = r['sec'] / max(len(test), 1)
    os.makedirs(a.out)
    rep = {'schema': 'p922-toolcompare-v1.1', 'devUnits': len(dev), 'testUnits': len(test), 'testBad': sum(u['bad'] for u in test),
           'boosting': {'bestParams': gs.best_params_, 'cvF1': gs.best_score_, 'features': FEATS}, 'ruffTuned': RUFF_TUNED, 'pylintTuned': PYLINT_TUNED,
           'tools': {'ruff': subprocess.run([os.path.join(VENV, 'ruff'), '--version'], capture_output=True, text=True).stdout.strip(),
                     'pylint': subprocess.run([os.path.join(VENV, 'pylint'), '--version'], capture_output=True, text=True).stdout.split('\n')[0]},
           'results': res, 'contractCheckerSha256': hashlib.sha256(open(os.path.join(ROOT, 'src', 'task-files', 'contract_check.py'), 'rb').read()).hexdigest()}
    open(os.path.join(a.out, 'toolcompare.json'), 'x').write(json.dumps(rep, indent=1))
    with open(os.path.join(a.out, 'units.jsonl'), 'x') as f:
        for r in rows: f.write(json.dumps(r) + '\n')
    print(json.dumps({k: {m: (round(v, 3) if isinstance(v, float) else v) for m, v in r.items() if m != 'sec'} for k, r in res.items()}, indent=1))


if __name__ == '__main__':
    main()
