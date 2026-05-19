from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "file_consistency_audit.md"

SKIP_DIRS = {
    ".git",
    ".venv",
    ".cleanup_quarantine",
    "node_modules",
    "__pycache__",
    "data",
    "logs",
}

SKIP_PARTS = {
    ("backend", "infrastructure", "protected_assets", "engine"),
    ("backend", "infrastructure", "protected_assets", "vision"),
    ("backend", "infrastructure", "vision", "models"),
    ("pikafish", "release-backup-20260131"),
}

TEXT_EXTENSIONS = {
    ".cjs",
    ".cpp",
    ".css",
    ".h",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}

TEXT_NAMES = {
    ".env",
    ".env.example",
    ".gitignore",
    "CHANGELOG.md",
    "README.md",
    "REFACTOR_PLAN.md",
}

FIXABLE_EXTENSIONS = {
    ".cjs",
    ".cpp",
    ".css",
    ".h",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}


def _has_skipped_part(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    for skip in SKIP_PARTS:
        if len(rel_parts) >= len(skip) and rel_parts[: len(skip)] == skip:
            return True
    return False


def iter_project_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if _has_skipped_part(path):
            continue
        if path.name == "package-lock.json":
            continue
        yield path


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in TEXT_NAMES


def normalize_text(text: str) -> str:
    lines = text.splitlines()
    normalized = "\n".join(line.rstrip() for line in lines)
    if normalized or text:
        normalized += "\n"
    return normalized


def audit_file(path: Path, fix: bool = False) -> dict:
    rel = path.relative_to(ROOT).as_posix()
    result = {
        "path": rel,
        "extension": path.suffix.lower() or path.name,
        "text_candidate": is_text_candidate(path),
        "utf8": None,
        "has_trailing_whitespace": False,
        "has_final_newline": None,
        "fixed": False,
        "skipped_reason": None,
    }

    if not result["text_candidate"]:
        result["skipped_reason"] = "non_text_extension"
        return result

    raw = path.read_bytes()
    if b"\x00" in raw:
        result["skipped_reason"] = "binary_content"
        return result

    try:
        text = raw.decode("utf-8-sig")
        result["utf8"] = True
    except UnicodeDecodeError:
        result["utf8"] = False
        result["skipped_reason"] = "not_utf8"
        return result

    result["has_final_newline"] = bool(not raw or raw.endswith((b"\n", b"\r\n")))
    result["has_trailing_whitespace"] = any(
        line.rstrip("\r\n").endswith((" ", "\t")) for line in text.splitlines(keepends=True)
    )

    if fix and path.suffix.lower() in FIXABLE_EXTENSIONS:
        normalized = normalize_text(text)
        if normalized != text:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(normalized)
            result["fixed"] = True
            result["has_final_newline"] = True
            result["has_trailing_whitespace"] = False

    return result


def write_report(results: list[dict]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(item["extension"] for item in results)
    problems = [
        item for item in results
        if item["utf8"] is False or item["has_trailing_whitespace"] or item["has_final_newline"] is False
    ]
    fixed = [item for item in results if item["fixed"]]
    non_utf8 = [item for item in results if item["utf8"] is False]

    lines = [
        "# File Consistency Audit",
        "",
        f"- Files scanned: {len(results)}",
        f"- Text candidates: {sum(1 for item in results if item['text_candidate'])}",
        f"- Fixed files: {len(fixed)}",
        f"- Remaining problem files: {len(problems)}",
        "",
        "## Extension Counts",
        "",
    ]
    for extension, count in counts.most_common():
        lines.append(f"- `{extension}`: {count}")

    lines.extend(["", "## Remaining Problems", ""])
    if not problems:
        lines.append("- None")
    else:
        for item in problems[:200]:
            flags = []
            if item["utf8"] is False:
                flags.append("not_utf8")
            if item["has_trailing_whitespace"]:
                flags.append("trailing_whitespace")
            if item["has_final_newline"] is False:
                flags.append("missing_final_newline")
            lines.append(f"- `{item['path']}`: {', '.join(flags)}")

    lines.extend(["", "## Non UTF-8 Files", ""])
    if not non_utf8:
        lines.append("- None")
    else:
        for item in non_utf8:
            lines.append(f"- `{item['path']}`")

    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit project file consistency.")
    parser.add_argument("--fix", action="store_true", help="Normalize fixable text/code files.")
    args = parser.parse_args()

    results = [audit_file(path, fix=args.fix) for path in iter_project_files()]
    write_report(results)
    print(f"Scanned files: {len(results)}")
    print(f"Report: {REPORT_PATH}")
    print(f"Fixed files: {sum(1 for item in results if item['fixed'])}")
    remaining = [
        item for item in results
        if item["utf8"] is False or item["has_trailing_whitespace"] or item["has_final_newline"] is False
    ]
    print(f"Remaining problem files: {len(remaining)}")
    return 1 if remaining and not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
