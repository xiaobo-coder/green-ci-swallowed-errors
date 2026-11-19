"""Paper 922 observer: independent re-implementation of the p922lint rules (written separately from
src/task-files/p922lint.py; the tests check that both agree on generated tasks and perturbations).

lint(source, honour_suppressions=True) -> sorted list of (line, code, suppression_comment_or_None)
With honour_suppressions=False every raw finding is returned, with the suppression comment that WOULD hide it.
"""
import ast
import builtins
import re

_BUILTIN_NAMES = frozenset(n for n in dir(builtins) if not n.startswith('_'))
_PH = re.compile(r'\{([A-Za-z_]\w*)\}')
_CODE_LIST = r'[A-Z]\d\d(?:\s*,\s*[A-Z]\d\d)*'
_SUPP = re.compile(r'#\s*(?:noqa(?::\s*(' + _CODE_LIST + r'))?|lint:\s*disable=(' + _CODE_LIST + r'))(?![A-Za-z0-9=:,-])(.*)$')
_FILE_OFF = re.compile(r'^\s*#\s*lint:\s*disable-file\s*$')
_MUTABLE_CALLS = ('list', 'dict', 'set')
_STOPPERS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def suppression_on(line_text, code):
    """Return (covered, comment_text) for one source line and rule code."""
    m = _SUPP.search(line_text)
    if m is None:
        return False, None
    listed = m.group(1) or m.group(2)
    if listed is None:
        return True, m.group(0)
    return code in [c.strip() for c in listed.split(',')], m.group(0)


def file_disabled(source):
    return any(_FILE_OFF.match(l) for l in source.splitlines())


class _Scope(ast.NodeVisitor):
    """Collects names loaded/stored and string constants directly in one function body."""

    def __init__(self):
        self.loaded, self.stored, self.strings, self.format_targets, self.fstring_parts = set(), {}, [], set(), set()

    def visit_FunctionDef(self, node):
        pass  # nested functions have their own scope

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node):
        pass

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.loaded.add(node.id)
        elif isinstance(node.ctx, ast.Store) and node.id not in self.stored:
            self.stored[node.id] = node.lineno

    def visit_Attribute(self, node):
        if node.attr in ('format', 'format_map') and isinstance(node.value, ast.Constant):
            self.format_targets.add(id(node.value))
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        for v in node.values:
            self.fstring_parts.add(id(v))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            self.strings.append(node)


def _raw_findings(tree):
    found = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        a = fn.args
        params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
        params += [x.arg for x in (a.vararg, a.kwarg) if x is not None]
        for d in list(a.defaults) + [d for d in a.kw_defaults if d is not None]:
            mutable = isinstance(d, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in _MUTABLE_CALLS)
            if mutable:
                found.append((fn.lineno, 'W01'))
        sc = _Scope()
        for stmt in fn.body:
            sc.visit(stmt)
        for p in params:
            if p in _BUILTIN_NAMES:
                found.append((fn.lineno, 'W06'))
        for name, line in sc.stored.items():
            if name in _BUILTIN_NAMES:
                found.append((line, 'W06'))
            if not name.startswith('_') and name not in sc.loaded:
                found.append((line, 'W03'))
        only_doc_or_pass = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                               for s in fn.body)
        if not only_doc_or_pass:
            for p in params:
                if p not in ('self', 'cls') and not p.startswith('_') and p not in sc.loaded:
                    found.append((fn.lineno, 'W08'))
        names_here = set(params) | set(sc.stored)
        for s in sc.strings:
            if id(s) in sc.format_targets or id(s) in sc.fstring_parts:
                continue
            if any(p in names_here for p in _PH.findall(s.value)):
                found.append((s.lineno, 'W02'))
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            seq = getattr(node, field, None)
            if isinstance(seq, list):
                stop = next((i for i, s in enumerate(seq) if isinstance(s, _STOPPERS)), None)
                if stop is not None and stop + 1 < len(seq):
                    found.append((seq[stop + 1].lineno, 'W04'))
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            found.append((node.lineno, 'W05'))
        if isinstance(node, ast.Compare):
            for op, rhs in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(rhs, ast.Constant) \
                        and type(rhs.value) in (str, int, float):
                    found.append((node.lineno, 'W07'))
    return sorted(set(found))


def lint(source, honour_suppressions=True):
    """Raises SyntaxError for unparsable source."""
    tree = ast.parse(source)
    lines = source.splitlines()
    off = file_disabled(source)
    out = []
    for line, code in _raw_findings(tree):
        text = lines[line - 1] if 1 <= line <= len(lines) else ''
        covered, comment = suppression_on(text, code)
        if off:
            covered, comment = True, comment or '# lint: disable-file'
        if honour_suppressions and covered:
            continue
        out.append((line, code, comment if covered else None))
    return out
