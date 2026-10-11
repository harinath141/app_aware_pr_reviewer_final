from app.diff_anchor import build_patch_index, parse_anchor_lines, resolve_anchor

# new-side numbering:  1 context, 2 added, 3 added, 4 blank context, 5 context, 6 context
PATCH = """@@ -1,4 +1,6 @@
 def a():
-    return 1
+    x = 2
+    return x

 def b():
     pass
"""

def test_parse_anchor_lines_tracks_new_side_numbering():
    added, context = parse_anchor_lines(PATCH)
    assert added == {2, 3}
    assert context == {1, 4, 5, 6}

def test_blank_context_line_advances_the_counter():
    # GitHub sends a blank context line as "", not as a lone space. If it did not advance the
    # counter every following line number would be wrong.
    added, context = parse_anchor_lines('@@ -1,2 +1,3 @@\n a\n\n+b\n')
    assert 2 in context
    assert added == {3}

def test_exact_line_is_kept():
    assert resolve_anchor(PATCH, 2) == 2
    assert resolve_anchor(PATCH, 5) == 5

def test_nearest_line_prefers_an_added_line():
    # 7 is not in the patch; 6 (context) and 5 (context) are equidistant-ish, and 3 is the
    # nearest added line, which must win over merely-nearest context.
    assert resolve_anchor(PATCH, 3) == 3
    assert resolve_anchor(PATCH, 100) == 6

def test_missing_line_falls_back_to_first_added_line():
    assert resolve_anchor(PATCH, None) == 2

def test_unanchorable_inputs_return_none():
    assert resolve_anchor(None, 10) is None          # no patch (binary or absent from the diff)
    assert resolve_anchor("", 10) is None
    assert resolve_anchor("@@ -1,2 +0,0 @@\n-a\n-b\n", 1) is None   # pure deletion, no new lines

def test_build_patch_index_skips_files_without_a_patch():
    files = [{"filename": "a.py", "patch": PATCH}, {"filename": "logo.png"}]
    assert build_patch_index(files) == {"a.py": PATCH}
