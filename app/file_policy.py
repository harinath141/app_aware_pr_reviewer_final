"""Per-repository include/exclude patterns.

**This composes with the built-in filters; it never replaces them.** `app/repository.py` decides
what is indexable at all - binaries, lockfiles, dependency trees, dot-directories - and those rules
are deliberately never named in any API response or UI. This decides what a repository's own
maintainers want skipped *on top* of that.

Two rules carry the meaning:

* **An exclude always beats an include.** "Everything except this" is the common intent, and the
  other precedence produces genuinely surprising results.
* **An empty include list means "everything not excluded"**, not "nothing". A form left blank must
  not silently index zero files.

Deliberately pure - no config, no database - so the matching rules can be tested directly.
"""
import fnmatch
from dataclasses import dataclass


def _clean(patterns) -> tuple[str, ...]:
    """Trim, drop blanks, de-duplicate, keep order."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern in patterns or []:
        value = str(pattern).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # A bare directory name ("vendor") and a trailing-slash form ("vendor/") both mean
        # everything beneath that directory, which fnmatch on its own does not give us.
        prefix = pattern.rstrip("/")
        if prefix and (path == prefix or path.startswith(prefix + "/")):
            return True
    return False


@dataclass(frozen=True)
class FilePolicy:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @classmethod
    def from_patterns(cls, include=None, exclude=None) -> "FilePolicy":
        return cls(include=_clean(include), exclude=_clean(exclude))

    @property
    def is_empty(self) -> bool:
        return not self.include and not self.exclude

    def allows(self, path: str) -> bool:
        if _matches(path, self.exclude):
            return False
        if not self.include:
            return True
        return _matches(path, self.include)


NO_POLICY = FilePolicy()


def policy_for(repo_full_name: str) -> FilePolicy:
    """The stored policy for a repository, or an empty one.

    A repository that was never onboarded, or whose settings row is missing, must index exactly as
    it did before this feature existed - so the failure mode is "no policy", never "no files".

    Imported lazily so this module stays free of app.config for testing.
    """
    from app.db import connect
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT include_patterns, exclude_patterns FROM repository_settings"
                " WHERE repo_full_name=%s", (repo_full_name,)).fetchone()
    except Exception:
        # A missing table (an older database) must not stop indexing.
        return NO_POLICY
    if not row:
        return NO_POLICY
    return FilePolicy.from_patterns(row[0], row[1])
