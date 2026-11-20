#!/usr/bin/env python3
"""Recompute every number in the paper from data/ and compare with expected/. Standard library only.
  python3 reproduce_tables.py      -> writes out/, prints MATCH/MISMATCH per macro file, exit 0 iff all match.
Detector re-runs (ruff, pylint, Semgrep, scikit-learn, Ollama judge) and model runs are NOT repeated; their frozen
outputs in v1.1/results/ are used. To re-run the trivial and mechanism analyses from the final modules, see README."""
import json, os, re, shutil, subprocess, sys
ROOT = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(ROOT, 'out'); PY = sys.executable
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
def run(args, **kw): subprocess.run([PY, '-I'] + args, check=True, cwd=ROOT, stdout=subprocess.DEVNULL, **kw)
# 1. first study (v0.5): all paper macros and tables
gen = os.path.join(ROOT, 'paper', 'generated'); shutil.rmtree(gen, ignore_errors=True)
run(['paper/render_numbers.py']); shutil.copy(os.path.join(gen, 'numbers.tex'), os.path.join(OUT, 'numbers.tex'))
# 2. post hoc trap-only tests and Holm over 12
run(['paper/posthoc_trap_only.py', os.path.join(OUT, 'posthoc-trap.tex')])
# 3. follow-up (v1.1) macros
run(['paper/make_v11_macros.py', 'v1.1/results', 'test', os.path.join(OUT, 'v11')]); shutil.copy(os.path.join(OUT, 'v11', 'v11-macros.tex'), os.path.join(OUT, 'v11-macros.tex'))
# 4. post hoc trivial baseline and mechanism/acceptance (from shipped outputs)
f = lambda x: '%.2f' % x
d = json.load(open(os.path.join(ROOT, 'v1.1/posthoc/trivial-test-001/trivial.json')))
open(os.path.join(OUT, 'posthoc-trivial.tex'), 'w').write('\n'.join(['\\newcommand{\\PTrivRec}{%s}' % f(d['recall']), '\\newcommand{\\PTrivFalseAlarm}{%s}' % f(d['falseAlarmRate']), '\\newcommand{\\PTrivFone}{%s}' % f(d['f1'])]) + '\n')
d = json.load(open(os.path.join(ROOT, 'v1.1/posthoc/mechanism-test-001/mechanism.json'))); M = []
m = lambda k, v: M.append('\\newcommand{\\PM%s}{%s}' % (k, v)); pc = lambda x: '%.1f' % (100 * x)
a = d['acceptance']; m('NBad', a['nBad']); m('NGood', a['nGood'])
for k, nm in {'ci': 'Ci', 'ciRuff': 'Ruff', 'ciPylint': 'Pylint', 'ciRuffPylint': 'RuffPylint', 'ciTrivial': 'Trivial', 'ciContract': 'Contract'}.items():
    m(nm + 'WrongAcc', pc(a['rules'][k]['wrongAccepted'])); m(nm + 'CorrRej', pc(a['rules'][k]['correctRejected']))
rb = d['recallByForm']; m('NNarrow', rb['narrowed, still swallows']['n']); m('NExcExc', rb['except Exception, swallows']['n'])
m('NarrowDoc', d['narrowing']['catchesDocumentedExc']); m('NarrowN', d['narrowing']['nNarrowedWrong'])
ns = [v['budgetExhausted'] for k, v in d['budget'].items() if k.endswith('|N')]; m('BudgetNMin', '%.0f' % (100 * min(ns))); m('BudgetNMax', '%.0f' % (100 * max(ns)))
open(os.path.join(OUT, 'posthoc-mechanism.tex'), 'w').write('\n'.join(M) + '\n')
run(['v1.1/posthoc/ndr_counts.py', 'v1.1/posthoc/mechanism-test-001/units.jsonl', os.path.join(OUT, 'posthoc-ndr.tex')])
# 5. field check macros (AgentPack counts only; raw data not redistributed)
run(['field-check/make_field_macros.py', 'field-check/summary.json', os.path.join(OUT, 'field-macros.tex')])
# compare
def macros(p): return dict(re.findall(r'\\newcommand\{\\(\w+)\}\{(.*)\}\s*$', open(p).read(), re.M))
ok = True
for fn in sorted(os.listdir(os.path.join(ROOT, 'expected'))):
    e, o = macros(os.path.join(ROOT, 'expected', fn)), macros(os.path.join(OUT, fn))
    bad = [k for k in e if o.get(k) != e[k]]
    print(('MATCH   ' if not bad else 'MISMATCH'), fn, '(%d macros)' % len(e), ('' if not bad else 'e.g. %s: expected %s got %s' % (bad[0], e[bad[0]], o.get(bad[0]))))
    ok &= not bad
print('RESULT:', 'ALL MATCH' if ok else 'MISMATCH'); sys.exit(0 if ok else 1)
