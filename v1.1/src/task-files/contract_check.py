#!/usr/bin/env python3
"""contract_check: flags exception handlers that swallow an exception the function's docstring says must be raised.

Static and deterministic (no model, no test generation). For every function whose docstring states an obligation such as
"must raise KeyError", "raise ValueError for ...", "... must raise ValueError" or "any other error (for example ValueError)
must propagate", every `except` clause in that function that can catch a documented exception (the same class, a base
class or subclass, `Exception`/`BaseException`, or a bare `except:`), is the first such handler of its `try`, and whose
body contains no `raise` is reported:

  module.py:LINE: C01 handler swallows ValueError, which the docstring of FUNC says must be raised

Exit status 1 if anything is reported. Usage: python3 contract_check.py module.py"""
import ast
import builtins
import importlib
import re
import sys

# Standard-library modules whose exception classes may be resolved (only these are ever imported).
STDLIB = {'json', 'decimal', 'csv', 'configparser', 'datetime', 'socket', 'ssl', 'urllib', 'http', 'subprocess', 'zipfile', 'tarfile', 'pickle', 'struct', 'binascii', 'base64', 'shutil', 'os', 'io', 'asyncio', 'concurrent', 'queue', 'sqlite3', 'xml', 'email', 'locale', 'codecs'}

OBLIG = [
    re.compile(r"must\s+raise\s+([A-Z]\w*(?:Error|Exception))"),
    re.compile(r"\braise\s+([A-Z]\w*(?:Error|Exception))\b"),
    re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b[^.;]*?\bmust\s+(?:propagate|be\s+raised)"),
    re.compile(r"must\s+propagate[^.;]*?\b([A-Z]\w*(?:Error|Exception))\b"),
]


RAISES_SECTION = re.compile(r"^\s*Raises:?\s*\n((?:[ \t]+\S.*\n?)+)", re.M)   # Google style "Raises:" block (also "Raises" + dashes, NumPy)


def documented(doc):
    out = set()
    for rx in OBLIG:
        out.update(m.group(1) for m in rx.finditer(doc or ""))
    for blk in RAISES_SECTION.finditer((doc or "") + "\n"):
        out.update(re.findall(r"^\s*([A-Z]\w*(?:Error|Exception))\b", blk.group(1), re.M))
    return {e for e in out if isinstance(getattr(builtins, e, None), type) and issubclass(getattr(builtins, e), BaseException)}


def resolve(expr):
    """Exception class for a Name (builtin) or a dotted standard-library attribute such as json.JSONDecodeError; else None."""
    if isinstance(expr, ast.Name):
        c = getattr(builtins, expr.id, None)
    elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id in STDLIB:
        try:
            c = getattr(importlib.import_module(expr.value.id), expr.attr, None)
        except Exception:
            c = None
    else:
        c = None
    return c if isinstance(c, type) and issubclass(c, BaseException) else None


def catches(handler, cls):
    """True if the handler would catch some instance of cls: bare except, or a listed class that is cls, a base of it, or a
    subclass of it (e.g. json.JSONDecodeError is a ValueError: catching it swallows the documented ValueError case)."""
    if handler.type is None:
        return True
    elts = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for e in elts:
        k = resolve(e)
        if k is not None and (issubclass(cls, k) or issubclass(k, cls)):
            return True
    return False


def _live_raises(stmts):
    """Raise statements in a statement list that can run: stop at the first return/continue/break (code after it is dead);
    descend into if/else, with, try and loops, but not into nested function or class definitions."""
    out = []
    for st in stmts:
        if isinstance(st, ast.Raise):
            out.append(st); break
        if isinstance(st, (ast.Return, ast.Continue, ast.Break)):
            break
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        for field in ('body', 'orelse', 'finalbody', 'handlers'):
            sub = getattr(st, field, None)
            if isinstance(sub, list):
                if field == 'handlers':
                    for h in sub: out += _live_raises(h.body)
                else:
                    out += _live_raises(sub)
    return out


def reraises(handler, cls):
    """True if the handler can re-raise the documented exception: a reachable bare `raise`, `raise <name bound by the
    handler>`, or a raise of the documented class or one of its subclasses. A raise of an unrelated exception does not count."""
    for r in _live_raises(handler.body):
        e = r.exc
        if e is None:
            return True
        if isinstance(e, ast.Name) and handler.name and e.id == handler.name:
            return True
        k = resolve(e.func if isinstance(e, ast.Call) else e)
        if k is not None and issubclass(k, cls):
            return True
    return False


def check(src):
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [(e.lineno or 0, "C00", "module does not parse")]
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        excs = documented(ast.get_docstring(fn))
        if not excs:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            for exc in sorted(excs):
                cls = getattr(builtins, exc)
                first = next((h for h in node.handlers if catches(h, cls)), None)   # Python runs only the first matching handler
                if first is not None and not reraises(first, cls):
                    out.append((first.lineno, "C01", "handler swallows %s, which the docstring of %s says must be raised" % (exc, fn.name)))
    return sorted(set(out))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "module.py"
    found = check(open(path, encoding="utf-8").read())
    for line, code, msg in found:
        print("%s:%d: %s %s" % (path, line, code, msg))
    print("contract_check: %d finding(s)" % len(found))
    sys.exit(1 if found else 0)
