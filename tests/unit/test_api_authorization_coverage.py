from __future__ import annotations

import ast
import unittest
from pathlib import Path

from backend.interfaces.api.auth_guard import (
    PROTECTED_ENDPOINTS,
    PUBLIC_CONTROL_ENDPOINTS,
    PUBLIC_ENDPOINTS,
)


ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "backend" / "interfaces" / "api"

def _route_decorators(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "route"
                and isinstance(func.value, ast.Name)
                and func.value.id == "api_bp"
            ):
                yield decorator


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _methods_from_decorator(decorator: ast.Call) -> set[str]:
    for keyword in decorator.keywords:
        if keyword.arg != "methods":
            continue
        value = keyword.value
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            methods = {
                str(item.value).upper()
                for item in value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            return methods or {"GET"}
    return {"GET"}


def _full_api_path(route: str) -> str:
    route = route if route.startswith("/") else f"/{route}"
    return f"/api{route}".rstrip("/") or "/api"


def _declared_routes() -> list[tuple[str, str, str]]:
    routes: list[tuple[str, str, str]] = []
    for path in sorted(API_DIR.glob("*_routes.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for decorator in _route_decorators(tree):
            if not decorator.args:
                continue
            route = _literal_string(decorator.args[0])
            if route is None:
                continue
            for method in _methods_from_decorator(decorator):
                routes.append((_full_api_path(route), method, path.name))
    return routes


def _matches_policy(path: str, method: str, item: tuple) -> bool:
    prefix, policy_method = item[0], item[1]
    normalized = path.rstrip("/")
    if policy_method and method != policy_method:
        return False
    return normalized == prefix or normalized.startswith(prefix + "/")


def _is_classified(path: str, method: str) -> bool:
    return (
        any(_matches_policy(path, method, item) for item in PROTECTED_ENDPOINTS)
        or any(_matches_policy(path, method, item) for item in PUBLIC_CONTROL_ENDPOINTS)
        or any(_matches_policy(path, method, item) for item in PUBLIC_ENDPOINTS)
    )


class TestApiAuthorizationCoverage(unittest.TestCase):
    def test_every_api_route_has_auth_policy_classification(self):
        missing = [
            f"{method} {path} ({source})"
            for path, method, source in _declared_routes()
            if not _is_classified(path, method)
        ]

        self.assertEqual(
            [],
            missing,
            "Every API route must be protected, public-control, or explicitly public.",
        )

    def test_public_post_routes_are_explicit(self):
        public_posts = [
            f"{method} {path} ({source})"
            for path, method, source in _declared_routes()
            if method == "POST"
            and not any(_matches_policy(path, method, item) for item in PROTECTED_ENDPOINTS)
            and not any(_matches_policy(path, method, item) for item in PUBLIC_CONTROL_ENDPOINTS)
            and not any(_matches_policy(path, method, item) for item in PUBLIC_ENDPOINTS)
        ]

        self.assertEqual([], public_posts)


if __name__ == "__main__":
    unittest.main()
