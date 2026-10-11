import io
import tarfile
from pathlib import PurePosixPath
from app.config import settings
from app.file_policy import FilePolicy

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
             "__pycache__", ".next", "coverage", "target", "out"}
TEXT_EXTS = {".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java",
 ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".hpp", ".sql",
 ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".xml", ".md", ".rst",
 ".txt", ".sh", ".tf", ".proto", ".graphql"}
SPECIAL_NAMES = {"dockerfile", "makefile", "requirements.txt", "pyproject.toml",
 "package.json", "pom.xml", "build.gradle", "go.mod", "cargo.toml", "openapi.yaml",
 "openapi.yml", "swagger.json"}

def is_indexable(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part in SKIP_DIRS or (part.startswith(".") and part != ".github") for part in p.parts):
        return False
    name = p.name.lower()
    if name.endswith((".lock", ".min.js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
                      ".zip", ".jar", ".class", ".so", ".dll", ".exe", ".bin")):
        return False
    return p.suffix.lower() in TEXT_EXTS or name in SPECIAL_NAMES or name.startswith("dockerfile")

def safe_extract_tar_gz(data: bytes, policy: FilePolicy | None = None,
                        stats: dict | None = None) -> dict[str, str]:
    """Extract the files worth indexing.

    `policy` is the repository's own include/exclude list and is applied **after** the built-in
    filters above, never instead of them - the built-ins decide what is indexable at all.

    `stats` is filled with counts of what was skipped and why. Onboarding uses them to show a
    repository what it is about to index without ever naming our built-in rules: the counts are
    reported, the rules are not.
    """
    counters = {"total": 0, "kept": 0, "builtin_skipped": 0, "policy_skipped": 0,
                "oversized": 0, "binary": 0}
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        counters["total"] = len(members)
        if len(members) > settings.max_files:
            raise ValueError("Repository has more than MAX_FILES files")
        for m in members:
            parts = PurePosixPath(m.name).parts
            if len(parts) < 2 or ".." in parts or PurePosixPath(m.name).is_absolute():
                counters["builtin_skipped"] += 1
                continue
            path = "/".join(parts[1:])
            if not path or not is_indexable(path):
                counters["builtin_skipped"] += 1
                continue
            if m.size < 0 or m.size > settings.max_file_bytes:
                counters["oversized"] += 1
                continue
            if policy is not None and not policy.allows(path):
                counters["policy_skipped"] += 1
                continue
            stream = tar.extractfile(m)
            if stream is None:
                counters["builtin_skipped"] += 1
                continue
            raw = stream.read(settings.max_file_bytes + 1)
            if len(raw) > settings.max_file_bytes or b"\x00" in raw[:8192]:
                counters["binary"] += 1
                continue
            try:
                result[path] = raw.decode("utf-8")
                counters["kept"] += 1
            except UnicodeDecodeError:
                counters["binary"] += 1
    if stats is not None:
        stats.update(counters)
    return result
