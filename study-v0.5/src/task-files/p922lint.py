#!/usr/bin/env python3
"""p922lint: a small static checker for this repository.

Usage: python3 p922lint.py FILE [FILE ...]
Prints one line per warning, "FILE:LINE: CODE message", and exits 1 if any warning is reported.

Rules
  W01  mutable default argument
  W02  string literal contains a {placeholder} naming a local variable but is not an f-string
  W03  local variable is assigned but never used
  W04  unreachable code after return/raise/continue/break
  W05  bare 'except:'
  W06  name shadows a Python builtin
  W07  'is' / 'is not' comparison with a str or number literal
  W08  function argument is never used

Suppression
  A warning is not reported when its line ends with a comment of the form
  "# noqa", "# noqa: W0x[,W0y]" or "# lint: disable=W0x[,W0y]", optionally followed by a justification
  (for example "# noqa: W06 public keyword argument").
  A line "# lint: disable-file" anywhere in a file disables all checks for that file.
"""
import ast
import builtins
import re
import sys

BUILTINS = {n for n in dir(builtins) if not n.startswith('_')}
PLACEHOLDER = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')
NOQA = re.compile(r'#\s*(?:noqa(?::\s*(?P<a>[A-Z]\d\d(?:\s*,\s*[A-Z]\d\d)*))?|lint:\s*disable=(?P<b>[A-Z]\d\d(?:\s*,\s*[A-Z]\d\d)*))(?![A-Za-z0-9=:,-]).*$')


def suppressed(lines, lineno, code):
    if not 1 <= lineno <= len(lines):
        return False
    m = NOQA.search(lines[lineno - 1])
    if not m:
        return False
    codes = m.group('a') or m.group('b')
    if codes is None:
        return True
    return code in {c.strip() for c in codes.split(',')}


def func_nodes(fn):
    """Nodes that belong to fn itself (not to nested functions, classes or lambdas)."""
    out, stack = [], list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))
    return out


def check_function(fn, warn):
    args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
    if fn.args.vararg:
        args.append(fn.args.vararg)
    if fn.args.kwarg:
        args.append(fn.args.kwarg)
    for d in fn.args.defaults + [d for d in fn.args.kw_defaults if d is not None]:
        if isinstance(d, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in ('list', 'dict', 'set')):
            warn(fn.lineno, 'W01', 'mutable default argument in %s()' % fn.name)
    nodes = func_nodes(fn)
    loads = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    stores = {}
    for n in nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            stores.setdefault(n.id, n.lineno)
    for a in args:
        if a.arg in BUILTINS:
            warn(fn.lineno, 'W06', "argument '%s' shadows a builtin" % a.arg)
    for name, line in stores.items():
        if name in BUILTINS:
            warn(line, 'W06', "variable '%s' shadows a builtin" % name)
    trivial = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                  for s in fn.body)
    if not trivial:
        for a in args:
            if a.arg in ('self', 'cls') or a.arg.startswith('_'):
                continue
            if a.arg not in loads:
                warn(fn.lineno, 'W08', "argument '%s' of %s() is never used" % (a.arg, fn.name))
    for name, line in stores.items():
        if not name.startswith('_') and name not in loads:
            warn(line, 'W03', "local variable '%s' is assigned but never used" % name)
    local_names = {a.arg for a in args} | set(stores)
    formatted = set()
    for n in nodes:
        if isinstance(n, ast.Attribute) and n.attr in ('format', 'format_map') and isinstance(n.value, ast.Constant):
            formatted.add(id(n.value))
    joined = {id(v) for n in nodes if isinstance(n, ast.JoinedStr) for v in n.values}
    for n in nodes:
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in formatted and id(n) not in joined:
            names = [p for p in PLACEHOLDER.findall(n.value) if p in local_names]
            if names:
                warn(n.lineno, 'W02', "string contains {%s} but is not an f-string" % names[0])


def check_blocks(tree, warn):
    for n in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            block = getattr(n, field, None)
            if not isinstance(block, list):
                continue
            for i, s in enumerate(block[:-1]):
                if isinstance(s, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                    warn(block[i + 1].lineno, 'W04', 'unreachable code')
                    break
        if isinstance(n, ast.ExceptHandler) and n.type is None:
            warn(n.lineno, 'W05', "bare 'except:'")
        if isinstance(n, ast.Compare):
            for op, right in zip(n.ops, n.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(right, ast.Constant) and \
                        isinstance(right.value, (str, int, float)) and not isinstance(right.value, bool):
                    warn(n.lineno, 'W07', "'is' comparison with a literal")


def lint(path):
    src = open(path, encoding='utf-8').read()
    lines = src.splitlines()
    if any(re.match(r'\s*#\s*lint:\s*disable-file\s*$', l) for l in lines):
        return []
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return ['%s:%s: E00 syntax error: %s' % (path, e.lineno, e.msg)]
    found = []

    def warn(line, code, msg):
        if not suppressed(lines, line, code):
            found.append((line, code, msg))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            check_function(n, warn)
    check_blocks(tree, warn)
    return ['%s:%d: %s %s' % (path, l, c, m) for l, c, m in sorted(set(found))]


if __name__ == '__main__':
    out = [w for p in sys.argv[1:] for w in lint(p)]
    print('\n'.join(out) if out else 'p922lint: no warnings')
    sys.exit(1 if out else 0)
