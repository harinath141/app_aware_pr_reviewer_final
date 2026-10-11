"""Parse the reviewer status commands left as replies on a finding's PR comment."""
import re

COMMAND_RE = re.compile(r"^/(resolved|invalid)\b(?:\s+(\d+))?", re.IGNORECASE)
STATUS_BY_ACTION = {"resolved": "resolved", "invalid": "invalid"}

def parse_command(body: str) -> tuple[str, int | None] | None:
    """Return (status, finding_id) for the first command line, else None.

    finding_id is None when the command carries no id, which is only usable on an inline
    review comment where the thread identifies the finding. Lines beginning with ">" are
    GitHub's quoted-reply text, so quoting an earlier command must not re-trigger it.
    """
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(">"):
            continue
        m = COMMAND_RE.match(line)
        if m:
            return STATUS_BY_ACTION[m.group(1).lower()], int(m.group(2)) if m.group(2) else None
    return None
