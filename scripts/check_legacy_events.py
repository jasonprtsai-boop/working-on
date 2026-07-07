from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_ROOTS = ("backend", "scripts")
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
}


@dataclass(frozen=True)
class LegacyPublishFinding:
    path: Path
    line: int
    column: int
    call: str

    def format(self) -> str:
        rel = self.path.relative_to(ROOT) if self.path.is_relative_to(ROOT) else self.path
        return f"{rel}:{self.line}:{self.column}: {self.call}"


class _LegacyPublishVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.findings: list[LegacyPublishFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_publish_call(node) and node.args and isinstance(node.args[0], ast.Dict):
            self.findings.append(
                LegacyPublishFinding(
                    path=self.path,
                    line=getattr(node, "lineno", 0),
                    column=getattr(node, "col_offset", 0) + 1,
                    call="publish({ ... })",
                )
            )
        self.generic_visit(node)

    @staticmethod
    def _is_publish_call(node: ast.Call) -> bool:
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "publish":
            return True
        return isinstance(fn, ast.Name) and fn.id == "publish"


def _iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for child in path.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in child.parts):
                continue
            files.append(child)
    return sorted(set(files))


def find_legacy_publish_calls(paths: list[Path]) -> list[LegacyPublishFinding]:
    findings: list[LegacyPublishFinding] = []
    for path in _iter_python_files(paths):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                LegacyPublishFinding(
                    path=path,
                    line=exc.lineno or 0,
                    column=exc.offset or 0,
                    call="syntax error while scanning",
                )
            )
            continue
        visitor = _LegacyPublishVisitor(path)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject first-party EventBus legacy dict publishers."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_SCAN_ROOTS),
        help="Files or directories to scan. Defaults to backend and scripts.",
    )
    args = parser.parse_args(argv)

    findings = find_legacy_publish_calls([Path(path) for path in args.paths])
    if findings:
        print("Legacy EventBus dict publishers found. Use BaseEvent.create(...).")
        for finding in findings:
            print(f"- {finding.format()}")
        return 1

    print("Legacy event publisher check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
