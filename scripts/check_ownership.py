"""Fail when a module writes a table it does not own."""

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNERS = {
    "songs": "library",
    "styles": "library",
    "photoshoots": "photoshoots",
    "photos": "photoshoots",
    "jobs": "jobs",
    "job_shots": "jobs",
    "attempts": "jobs",
    "provider_calls": "providers",
    "cut_checks": "comparison",
}
SQL_WRITE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|DELETE\s+FROM)\s+[\"`\[]?(\w+)"
    r"|\bUPDATE\s+[\"`\[]?(\w+)[\"`\]]?\s+SET\b",
    re.IGNORECASE,
)
STATEMENTS = {"insert", "update", "delete"}
SESSION_WRITES = {"add", "add_all", "merge"}


def _model_tables() -> dict[str, str]:
    import app.comparison.models  # noqa: F401
    import app.jobs.models  # noqa: F401
    import app.library.models  # noqa: F401
    import app.photoshoots.models  # noqa: F401
    import app.providers.models  # noqa: F401
    from app.db.base import Base

    return {m.class_.__name__: m.local_table.name for m in Base.registry.mappers}


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _built_models(value: ast.AST | None, models: dict[str, str]) -> set[str]:
    if isinstance(value, ast.Call) and _name(value.func) in models:
        return {models[_name(value.func)]}
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return set().union(*(_built_models(e, models) for e in value.elts))
    return set()


def _assigned_models(tree: ast.AST, models: dict[str, str]) -> dict[str, set[str]]:
    assigned: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        built = _built_models(value, models)
        for target in targets:
            if built and isinstance(target, ast.Name):
                assigned.setdefault(target.id, set()).update(built)
    return assigned


def _written_tables(tree: ast.AST, models: dict[str, str]) -> set[str]:
    tables: set[str] = set()
    assigned = _assigned_models(tree, models)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = _name(node.func)
            if func in STATEMENTS and node.args:
                model = _name(node.args[0])
                if model in models:
                    tables.add(models[model])
            elif func in SESSION_WRITES and isinstance(node.func, ast.Attribute):
                for arg in node.args:
                    for inner in ast.walk(arg):
                        if isinstance(inner, ast.Call) and _name(inner.func) in models:
                            tables.add(models[_name(inner.func)])
                        elif isinstance(inner, ast.Name) and inner.id in assigned:
                            tables.update(assigned[inner.id])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for groups in SQL_WRITE.findall(node.value):
                table = next(g for g in groups if g).lower() if any(groups) else ""
                if table in OWNERS:
                    tables.add(table)
    return tables


def find_ownership_violations(app_root: Path) -> list[tuple[str, str]]:
    app_root = Path(app_root)
    models = _model_tables()
    violations: list[tuple[str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        parts = path.relative_to(app_root).parts
        if parts[0] == "db":
            continue
        module = parts[0] if len(parts) > 1 else ""
        tree = ast.parse(path.read_text(), filename=str(path))
        shown = (Path(app_root.name) / Path(*parts)).as_posix()
        for table in sorted(_written_tables(tree, models)):
            if OWNERS.get(table) != module:
                violations.append((shown, table))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else REPO_ROOT / "app"
    violations = find_ownership_violations(root)
    for file, table in violations:
        print(f"{file} writes table {table} owned by {OWNERS[table]}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
