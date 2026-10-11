from app.analyzer import analyze_files, chunk_text, stable_id

def test_chunking():
    chunks = chunk_text("\n".join(f"line {i}" for i in range(100)), 100)
    assert len(chunks) > 1 and all(c.strip() for c in chunks)

def test_python_symbols_and_calls():
    symbols, edges = analyze_files({"service.py": "def helper(x):\n return x\ndef run():\n return helper(1)\n"})
    assert any(s.name == "helper" for s in symbols)
    assert any(s.name == "run" for s in symbols)
    assert any(e.edge_type == "call_or_import" for e in edges)

def test_stable_id():
    assert stable_id("a","b") == stable_id("a","b")
    assert stable_id("a","b") != stable_id("a","c")

# --- JS/TS edges ---------------------------------------------------------------------------
# Before these, the non-Python branch extracted symbols but never recorded a call, so a
# TypeScript repository produced zero edges no matter how many symbols it had.

def _symbol(symbols, name, path=None):
    return next(s for s in symbols if s.name == name and (path is None or s.file_path == path))

def test_js_call_edge_attributed_to_enclosing_declaration():
    symbols, edges = analyze_files(
        {"a.ts": "function foo() { return 1; }\nfunction bar() { return foo(); }\n"})
    bar, foo = _symbol(symbols, "bar"), _symbol(symbols, "foo")
    assert any(e.source_id == bar.symbol_id and e.target_id == foo.symbol_id for e in edges)

def test_js_top_level_call_attributed_to_module_symbol():
    # The call precedes the declaration, so nothing has been declared yet to own it.
    symbols, edges = analyze_files({"a.ts": "bootstrap();\nfunction bootstrap() {}\n"})
    module = next(s for s in symbols if s.kind == "module")
    boot = _symbol(symbols, "bootstrap")
    assert any(e.source_id == module.symbol_id and e.target_id == boot.symbol_id for e in edges)

def test_js_control_flow_keywords_do_not_create_edges():
    # `check` is referenced by an if, never called. Keywords look like calls to a naive regex.
    symbols, edges = analyze_files(
        {"a.ts": "function check() {}\nfunction run() { if (check) { for (let i=0;i<1;i++){} } }\n"})
    targets = {e.target_id for e in edges}
    assert _symbol(symbols, "check").symbol_id not in targets

def test_jsx_component_usage_creates_edge_and_dom_tags_are_ignored():
    symbols, edges = analyze_files(
        {"a.tsx": "export const Widget = () => null;\n"
                  "export function App() { return <div><Widget /></div>; }\n"})
    widget = _symbol(symbols, "Widget")
    assert any(e.target_id == widget.symbol_id for e in edges)
    assert not any(s.name == "div" for s in symbols)

def test_js_import_resolves_to_defined_name_not_the_alias():
    symbols, edges = analyze_files({
        "a.ts": "export function helper() {}\n",
        "b.ts": "import { helper as h } from './a';\nexport function use() { return h(); }\n",
    })
    helper = _symbol(symbols, "helper", path="a.ts")
    assert any(e.target_id == helper.symbol_id for e in edges)

def test_js_ambiguous_name_suppresses_the_edge():
    # Two symbols share the name, so the resolver cannot know which is meant - emit neither.
    symbols, edges = analyze_files(
        {"a.ts": "function render() {}\nfunction render() {}\nfunction go() { render(); }\n"})
    render_ids = {s.symbol_id for s in symbols if s.name == "render"}
    assert len(render_ids) == 2
    assert not any(e.target_id in render_ids for e in edges)

def test_non_js_files_contribute_no_edges():
    # Edge collection is gated on the JS/TS extension list, so prose cannot mint edges.
    symbols, edges = analyze_files({"README.md": "Call install() then run().\n"})
    assert edges == []
