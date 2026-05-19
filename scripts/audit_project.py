import os
import re
from datetime import datetime


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_PATH = os.path.join(ROOT, "reports", "system_audit.md")

PATTERNS = {
    "todo_fixme": re.compile(r"\b(TODO|FIXME|XXX)\b"),
    "pass_line": re.compile(r"^\s*pass\s*(#.*)?$"),
    "not_impl": re.compile(r"raise\s+NotImplementedError"),
}

SKIP_DIRS = {".git", ".venv", ".venv39", "node_modules", "__pycache__", "dist", "reports"}


def iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith((".py", ".js", ".html", ".md", ".ps1")):
                yield os.path.join(dirpath, fn)


def scan_file(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return None

    counts = {k: 0 for k in PATTERNS}
    hits = {k: [] for k in PATTERNS}
    for i, line in enumerate(lines, start=1):
        for key, rx in PATTERNS.items():
            if rx.search(line):
                counts[key] += 1
                if len(hits[key]) < 20:
                    rel = os.path.relpath(path, ROOT)
                    hits[key].append(f"{rel}:{i}: {line.strip()}")
    return counts, hits


def main():
    total = {k: 0 for k in PATTERNS}
    examples = {k: [] for k in PATTERNS}
    files_scanned = 0

    for p in iter_files():
        res = scan_file(p)
        if not res:
            continue
        files_scanned += 1
        counts, hits = res
        for k in PATTERNS:
            total[k] += counts[k]
            remaining = 20 - len(examples[k])
            if remaining > 0:
                examples[k].extend(hits[k][:remaining])

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("# System Audit (auto-generated)\n\n")
        out.write(f"- Generated: {datetime.now().isoformat(timespec='seconds')}\n")
        out.write(f"- Files scanned: {files_scanned}\n\n")
        out.write("## Counts\n\n")
        out.write(f"- TODO/FIXME/XXX: {total['todo_fixme']}\n")
        out.write(f"- Bare `pass` lines: {total['pass_line']}\n")
        out.write(f"- `NotImplementedError`: {total['not_impl']}\n\n")
        out.write("## Examples (top 20 each)\n\n")
        for k, title in [
            ("todo_fixme", "TODO/FIXME/XXX"),
            ("pass_line", "pass"),
            ("not_impl", "NotImplementedError"),
        ]:
            out.write(f"### {title}\n\n")
            if not examples[k]:
                out.write("- (none)\n\n")
                continue
            for line in examples[k]:
                out.write(f"- {line}\n")
            out.write("\n")


if __name__ == "__main__":
    main()
