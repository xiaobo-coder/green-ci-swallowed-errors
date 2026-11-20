#!/usr/bin/env python3
"""922 v1.1 POST HOC (2026-11-19, after co-author review): handler-form counts within the acceptance-rule scope
(N, D, R episodes; wrong trap repairs), from mechanism-test-001/units.jsonl. Writes \\PMNDR* macros (create-only).
  python3 -I posthoc/ndr_counts.py posthoc/mechanism-test-001/units.jsonl OUT.tex"""
import collections, json, sys, os
R = [json.loads(l) for l in open(sys.argv[1])]
b = [r for r in R if r['bad'] and r['cond'] in 'NDR']; f = collections.Counter(r['form'] for r in b)
acc = [r for r in b if r['ci'] and not r['ruff'] and not r['pylint']]
M = {'NDRBad': len(b), 'NDRNarrow': f['narrowed, still swallows'], 'NDRExcExc': f['except Exception, swallows'],
     'NDRAccepted': len(acc), 'NDRAccNarrow': sum(r['form'] == 'narrowed, still swallows' for r in acc),
     'NDRNarrowFlagged': sum(r['form'] == 'narrowed, still swallows' and (r['ruff'] or r['pylint']) for r in b),
     'NDRExcExcFlagged': sum(r['form'] == 'except Exception, swallows' and r['ruff'] and r['pylint'] for r in b)}
if os.path.exists(sys.argv[2]): sys.exit('exists (create-only)')
open(sys.argv[2], 'x').write('% POST HOC: v1.1/posthoc/ndr_counts.py\n' + '\n'.join('\\newcommand{\\PM%s}{%d}' % kv for kv in M.items()) + '\n')
print(M)
