"""Decide whether a (file, line) can carry an inline PR review comment.

GitHub rejects an inline comment with 422 when its line is not part of the pull request diff,
so every anchor the model proposes must be validated against the diff hunks first, with a
standalone comment as the fallback.
"""
import re

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

def build_patch_index(files: list[dict]) -> dict[str, str]:
    """Map filename -> unified diff patch, from the raw GitHub files payload.

    Build this from the raw `files` list rather than the `diff` string assembled in main.py:
    that one is truncated to MAX_DIFF_CHARS and can end mid-hunk, which corrupts the parse.
    """
    return {f.get("filename"): f.get("patch") for f in files if f.get("patch")}

def parse_anchor_lines(patch: str) -> tuple[set[int], set[int]]:
    """Return (added, context) new-file line numbers present in the patch.

    Only these two kinds of line exist on the RIGHT side of the diff, so only these can carry
    an inline comment. Removed lines belong to the LEFT side and are deliberately excluded.
    """
    added, context = set(), set()
    new_no, in_hunk = 0, False
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            in_hunk = bool(m)
            if m:
                new_no = int(m.group(1))
            continue
        if not in_hunk:
            continue
        if not raw:
            # GitHub renders a blank context line as an empty string rather than a lone space.
            # It is still a line on the new side, so the counter must advance or every later
            # anchor is off by one.
            context.add(new_no)
            new_no += 1
            continue
        marker = raw[0]
        if marker == "+":
            added.add(new_no)
            new_no += 1
        elif marker == " ":
            context.add(new_no)
            new_no += 1
        # "-" is old-side only and does not advance the new-file counter.
        # "\" is the "\ No newline at end of file" marker and carries no line.
    return added, context

def resolve_anchor(patch: str | None, line: int | None) -> int | None:
    """Return a line GitHub will accept for a RIGHT-side comment, or None if none exists.

    None means the finding cannot be anchored (missing/binary patch, or a pure deletion with
    no hunk lines) and the caller should post a standalone comment instead.
    """
    if not patch:
        return None
    added, context = parse_anchor_lines(patch)
    anchorable = added | context
    if not anchorable:
        return None
    if line is None:
        # No usable line from the model: anchor at the first change in the file.
        return min(added) if added else min(context)
    if line in anchorable:
        return line
    # Nearest anchorable line, preferring an added line when equidistant.
    return min(anchorable, key=lambda n: (abs(n - line), n not in added))
