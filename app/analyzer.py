import ast
import hashlib
import re
from dataclasses import dataclass

@dataclass
class Symbol:
    symbol_id: str
    name: str
    kind: str
    file_path: str
    start_line: int | None
    end_line: int | None
    signature: str = ""

@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str
    evidence_path: str
    evidence_line: int | None

def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

def chunk_text(text: str, max_chars: int = 3500) -> list[str]:
    lines = text.splitlines()
    chunks, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) + 1 > max_chars:
            chunks.append("\n".join(current))
            overlap = current[-5:]
            current, size = list(overlap), sum(len(x) + 1 for x in overlap)
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks or ([text] if text else [])

# --- JavaScript / TypeScript extraction ----------------------------------------------------
# Regex only: requirements.txt carries no parser, and analyze_files must stay pure and fast
# because it runs inside the webhook request. The README already describes JS/TS parsing as
# heuristic, and these rules are deliberately conservative - see the resolution rule below,
# which refuses any target name that is not unique across the repository.

# Extensions that may contribute call/import edges. The symbol patterns below still run over
# every non-Python file (unchanged behaviour); only edge collection is gated, so prose in a
# README cannot mint edges.
JS_TS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

JS_SYMBOL_PATTERNS = [
    (r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", "function"),
    (r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "function"),
    (r"\bclass\s+([A-Za-z_$][\w$]*)", "class"),
    (r"\b(?:public|private|protected|static|async|final|void|int|String|boolean|export|default)\s+([A-Za-z_$][\w$]*)\s*\(", "method"),
]

_JS_CALL = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")
# Capitalised, two characters or more: matches component usage, ignores DOM tags (<div>) and
# closing tags (</Foo>), because the character after "<" must be an uppercase letter.
_JSX_OPEN_TAG = re.compile(r"<\s*([A-Z][A-Za-z0-9_$]+)")
_JS_IMPORT_FROM = re.compile(r"\bimport\s+(?:type\s+)?([^;'\"]+?)\s+from\s*['\"]([^'\"]+)['\"]")
_JS_REQUIRE = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\s*\(")
_JS_EXPORT_FROM = re.compile(r"\bexport\s+\{([^}]*)\}\s*from\s*['\"]")
_JS_NAMESPACE = re.compile(r"as\s+([A-Za-z_$][\w$]*)")
_JS_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*\Z")

# Followed by "(" but not a call site. Without this the control-flow keywords alone would
# outnumber the real calls in a typical file.
_JS_KEYWORDS = frozenset((
    "if", "for", "while", "switch", "catch", "return", "function", "typeof", "await", "do",
    "else", "delete", "void", "in", "of", "new", "case", "throw", "yield", "super",
    "instanceof", "class", "const", "let", "var", "import", "export", "default", "extends",
    "with", "from", "as", "try", "finally", "break", "continue", "this", "null", "true",
    "false", "undefined", "static", "get", "set",
))

_JS_GLOBALS = frozenset((
    "console", "setTimeout", "setInterval", "clearTimeout", "clearInterval", "parseInt",
    "parseFloat", "require", "Object", "Array", "String", "Number", "Boolean", "Symbol",
    "Promise", "JSON", "Math", "Date", "RegExp", "Error", "Map", "Set", "WeakMap", "WeakSet",
    "fetch", "document", "window", "globalThis", "process", "localStorage", "sessionStorage",
    "isNaN", "encodeURIComponent", "decodeURIComponent", "structuredClone", "queueMicrotask",
))

# A generated or minified bundle can otherwise emit thousands of candidates from one file.
MAX_CALL_SITES_PER_FILE = 300


def _collect_js_call_sites(path: str, content: str,
                           symbols: list[Symbol], call_sites: list[tuple]) -> None:
    """Record call and import sites for a JS/TS file.

    Scope is approximated by "the most recently declared symbol wins": a call is attributed to
    the last declaration seen above it, or to the file's module symbol before the first one. A
    nested declaration therefore claims the calls inside it rather than its parent - the edge
    still points at a real symbol, so the imprecision is bounded to *who* calls, not *what*.

    Brace counting was considered and rejected: TSX is full of unbalanced braces (JSX
    expressions, template literals, object literals, strings), so a regex counter drifts within
    a few hundred lines and then misattributes silently, which is worse than the simple rule.
    """
    lines = content.splitlines()
    is_jsx = path.endswith((".jsx", ".tsx"))

    module_id = stable_id(path, "module")
    symbols.append(Symbol(module_id, path.rsplit("/", 1)[-1], "module", path,
                          1, max(1, len(lines)), path))

    owner_id = module_id
    seen: set[tuple[str, str]] = set()

    def add(source_id: str, name: str, line_no: int) -> None:
        if len(seen) >= MAX_CALL_SITES_PER_FILE:
            return
        key = (source_id, name)
        if key in seen:
            return
        seen.add(key)
        call_sites.append((source_id, name, path, line_no))

    for line_no, line in enumerate(lines, 1):
        # Re-match declarations only to track ownership; the symbols themselves were already
        # emitted by the caller, using the same patterns and therefore the same stable ids.
        declared = set()
        for pattern, kind in JS_SYMBOL_PATTERNS:
            match = re.search(pattern, line)
            if match:
                owner_id = stable_id(path, kind, match.group(1), str(line_no))
                declared.add(match.group(1))

        # Imports are module-scoped by definition, so they hang off the module symbol. Targets
        # use the name before "as" - the alias does not exist at the definition site.
        for match in _JS_IMPORT_FROM.finditer(line):
            clause = match.group(1).strip()
            if clause.startswith("*"):
                namespace = _JS_NAMESPACE.search(clause)
                if namespace:
                    add(module_id, namespace.group(1), line_no)
                continue
            head, brace, rest = clause.partition("{")
            head = head.strip().rstrip(",").strip()
            if _JS_IDENTIFIER.match(head):
                add(module_id, head, line_no)
            if brace:
                for part in rest.split("}")[0].split(","):
                    part = part.strip()
                    if part:
                        add(module_id, part.split(" as ")[0].strip(), line_no)

        match = _JS_REQUIRE.search(line)
        if match:
            add(module_id, match.group(1), line_no)

        for match in _JS_EXPORT_FROM.finditer(line):
            for part in match.group(1).split(","):
                part = part.strip()
                if part:
                    add(module_id, part.split(" as ")[0].strip(), line_no)

        for match in _JS_CALL.finditer(line):
            name = match.group(1)
            if name in declared or name in _JS_KEYWORDS or name in _JS_GLOBALS:
                continue
            add(owner_id, name, line_no)

        if is_jsx:
            for match in _JSX_OPEN_TAG.finditer(line):
                name = match.group(1)
                if name not in declared:
                    add(owner_id, name, line_no)


def analyze_files(files: dict[str, str]) -> tuple[list[Symbol], list[Edge]]:
    symbols, edges, call_sites = [], [], []
    for path, content in files.items():
        if path.endswith((".py", ".pyi")):
            try:
                tree = ast.parse(content)
            except (SyntaxError, ValueError):
                continue
            module_id = stable_id(path, "module")
            symbols.append(Symbol(module_id, path.rsplit("/", 1)[-1], "module", path,
                                  1, max(1, len(content.splitlines())), path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    sig = f"{kind} {node.name}"
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sig += "(" + ", ".join(a.arg for a in node.args.args) + ")"
                    sid = stable_id(path, kind, node.name, str(node.lineno))
                    symbols.append(Symbol(sid, node.name, kind, path, node.lineno,
                                          getattr(node, "end_lineno", node.lineno), sig))
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            target = child.func.id if isinstance(child.func, ast.Name) else (
                                child.func.attr if isinstance(child.func, ast.Attribute) else "")
                            if target:
                                call_sites.append((sid, target, path, getattr(child, "lineno", node.lineno)))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        call_sites.append((module_id, alias.name, path, node.lineno))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    call_sites.append((module_id, node.module, path, node.lineno))
        else:
            for line_no, line in enumerate(content.splitlines(), 1):
                for pattern, kind in JS_SYMBOL_PATTERNS:
                    m = re.search(pattern, line)
                    if m:
                        symbols.append(Symbol(stable_id(path, kind, m.group(1), str(line_no)),
                                              m.group(1), kind, path, line_no, line_no, line.strip()[:300]))
            if path.endswith(JS_TS_SUFFIXES):
                _collect_js_call_sites(path, content, symbols, call_sites)
    by_name = {}
    for s in symbols:
        by_name.setdefault(s.name, []).append(s)
    for source, name, path, line in call_sites:
        matches = by_name.get(name, [])
        if len(matches) == 1:
            edges.append(Edge(source, matches[0].symbol_id, "call_or_import", path, line))
    return symbols, edges
