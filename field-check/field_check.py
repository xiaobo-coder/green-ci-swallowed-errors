#!/usr/bin/env python3
"""922 post hoc field check (NOT preregistered) on AgentPack (nuprl/AgentPack rev 3e8457c, sample files).
Reads gzip JSONL as data only; never executes repository code. Usage:
  python3 -I field_check.py OUT_DIR file1.jsonl.gz [...]
Per Python-file hunk, counts handlers the agent ADDED (except line and its body all '+' lines):
  broad  = bare `except:` / `except Exception|BaseException` (incl. tuples containing them)
  swallow = handler body has no raise and only pass/continue/break/return[ const]/... /logging/print/warnings calls
plus suppression comments added/removed (# noqa, # type: ignore, # pylint: disable, # nosec) and
narrowing (hunk removes a broad handler and adds a specific one)."""
import gzip, json, os, re, sys, random, hashlib
BROAD = re.compile(r'^\s*except\s*(:|\(?\s*(Exception|BaseException)\b[^:]*:|\([^)]*\b(Exception|BaseException)\b[^)]*\)[^:]*:)')
EXCEPT = re.compile(r'^\s*except\b')
SUPP = re.compile(r'#\s*(noqa|type:\s*ignore|pylint:\s*disable|nosec)\b')
QUIET = re.compile(r'^\s*(pass|continue|break|\.\.\.|return(\s+(None|False|True|\[\]|\{\}|\(\)|""|\'\'|-?\d+|0\.0))?|(self\.)?(log|logger|logging|_log|_logger|LOG|LOGGER)\s*[.(].*\(.*|print\(.*|warnings\.warn\(.*)\s*(#.*)?$')

def files(patch):
    cur = None; hunk = None; out = []
    for ln in patch.split('\n'):
        if ln.startswith('diff --git'):
            m = re.search(r' b/(.+)$', ln); cur = m.group(1) if m else None; hunk = None; continue
        if cur is None or not cur.endswith('.py'): continue
        if ln.startswith('@@'): hunk = []; out.append((cur, hunk)); continue
        if hunk is not None and ln[:1] in '+- ' and not ln.startswith(('+++', '---')): hunk.append(ln)
    return out

def indent(s): return len(s) - len(s.lstrip(' \t'))

def handlers(hunk):
    out = []
    for i, ln in enumerate(hunk):
        if ln[:1] != '+' or not EXCEPT.match(ln[1:]): continue
        head = ln[1:]; ind = indent(head); body = []; allplus = True
        for nx in hunk[i + 1:]:
            t = nx[1:]
            if nx[:1] == '-': continue
            if not t.strip(): continue
            if indent(t) <= ind: break
            if nx[:1] != '+': allplus = False
            body.append(t)
        if not allplus or not body: continue
        stmts = [b for b in body if not b.strip().startswith('#')]
        swallow = all(QUIET.match(b) for b in stmts) and not any(re.match(r'^\s*raise\b', b) for b in stmts)
        out.append({'broad': bool(BROAD.match(head)), 'swallow': swallow, 'head': head.strip(), 'body': [b.rstrip() for b in body[:6]]})
    return out

def main():
    outd, paths = sys.argv[1], sys.argv[2:]
    if os.path.exists(outd): sys.exit('exists (create-only)')
    seen = set(); agg = {}; examples = []
    for p in paths:
        for line in gzip.open(p, 'rt'):
            r = json.loads(line); key = (r['repo'], r['sha'])
            if key in seen: continue
            seen.add(key); a = agg.setdefault(r['agent'], {k: 0 for k in ['events', 'eventsPy', 'handlersAdded', 'broadAdded', 'broadSwallowAdded', 'specificAdded', 'specificSwallowAdded', 'eventsBroadSwallow', 'suppAdded', 'suppRemoved', 'eventsSuppAdded', 'narrowings', 'eventsNarrowing']})
            a['events'] += 1; py = False; ebs = es = en = False
            for fn, hunk in files(r.get('patch') or ''):
                py = True
                for h in handlers(hunk):
                    a['handlersAdded'] += 1
                    if h['broad']:
                        a['broadAdded'] += 1
                        if h['swallow']: a['broadSwallowAdded'] += 1; ebs = True
                    else:
                        a['specificAdded'] += 1; a['specificSwallowAdded'] += h['swallow']
                    examples.append({'agent': r['agent'], 'repoHash': hashlib.sha256(r['repo'].encode()).hexdigest()[:10], 'file': fn.rsplit('/', 1)[-1], **h})
                add = [l for l in hunk if l[:1] == '+']; rem = [l for l in hunk if l[:1] == '-']
                sa = sum(bool(SUPP.search(l)) for l in add); sr = sum(bool(SUPP.search(l)) for l in rem)
                a['suppAdded'] += sa; a['suppRemoved'] += sr; es |= sa > sr
                if any(BROAD.match(l[1:]) for l in rem) and any(EXCEPT.match(l[1:]) and not BROAD.match(l[1:]) for l in add): a['narrowings'] += 1; en = True
            a['eventsPy'] += py; a['eventsBroadSwallow'] += ebs; a['eventsSuppAdded'] += es; a['eventsNarrowing'] += en
    os.makedirs(outd)
    json.dump({'source': 'nuprl/AgentPack@3e8457c45652cd1b8333dcf20d040b974ee91a11', 'files': [os.path.basename(p) for p in paths], 'postHoc': True, 'byAgent': agg}, open(os.path.join(outd, 'summary.json'), 'x'), indent=1)
    random.Random(922).shuffle(examples)
    with open(os.path.join(outd, 'audit-sample.jsonl'), 'x') as f:
        for e in [e for e in examples if e['broad']][:40] + [e for e in examples if not e['broad']][:20]: f.write(json.dumps(e) + '\n')
    print(json.dumps(agg, indent=1))

if __name__ == '__main__':
    main()
