#!/usr/bin/env python3
"""Zero-caller detection for the B-class bug shape (方案 5 of #19).

B-class bugs ("built but never wired") hit this project five times: a class
and its methods are complete and unit-tested, yet nothing in ``src`` ever
constructs or calls them. Coverage cannot see this shape — the unit tests
instantiate the component themselves, so it looks alive while production
code never touches it. This check looks at the wiring instead: every public
class/function/method defined in ``src`` must be referenced at runtime
somewhere else in ``src``, or it is reported.

What does NOT count as wiring:

* imports — an import only proves a file mentioned the name, and a name may
  be imported solely to appear in a type annotation (ruff already forbids
  imports that are unused even by annotations, so real uses always show up
  as real expressions)
* type annotations — including everything under ``if TYPE_CHECKING:``
* names inside ``__all__`` — a re-export is not a call

Decorated functions and methods are exempt: FastAPI route handlers, Typer
commands, ``@property`` accessors and similar are invoked by the framework,
never by a name that could appear in ``src``.

Orphans kept on purpose (the HLS pipeline is built but deliberately not
wired yet, pinned by a strict xfail) live in
``scripts/zero_callers_whitelist.txt``. Every entry must carry a reason, and
entries that no longer match an orphan fail the check, so the whitelist
cannot quietly rot.

Usage:
    python scripts/zero_callers.py [--src src/birec] [--whitelist FILE]

Exit status: 0 when no orphan is found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SRC = Path("src/birec")
DEFAULT_WHITELIST = Path("scripts/zero_callers_whitelist.txt")


@dataclass(frozen=True, slots=True)
class Definition:
    """A public definition that must have a caller in ``src``."""

    qualname: str
    name: str
    path: Path
    lineno: int
    exempt_reason: str | None


def module_qualname(path: Path, src_root: Path) -> str:
    """``src/birec/space/__init__.py`` -> ``birec.space``."""
    parts = list(path.relative_to(src_root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_type_checking_test(test: ast.expr) -> bool:
    """``if TYPE_CHECKING:`` / ``if typing.TYPE_CHECKING:``."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def collect_uses(tree: ast.AST) -> set[str]:
    """Names referenced at runtime.

    Annotations, ``if TYPE_CHECKING:`` blocks and import statements are
    typing-only: they prove a module mentioned a name, not that it runs it.
    """
    uses: set[str] = set()

    def walk(node: ast.AST, typing_only: bool) -> None:
        if typing_only:
            return
        if isinstance(node, ast.Import | ast.ImportFrom):
            return
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                uses.add(node.id)
            return
        if isinstance(node, ast.Attribute):
            walk(node.value, typing_only)
            if isinstance(node.ctx, ast.Load):
                uses.add(node.attr)
            return
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            walk(node.test, typing_only)
            for child in [*node.body, *node.orelse]:
                walk(child, typing_only=True)
            return
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                walk(decorator, typing_only)
            for param in node.type_params:
                walk(param, typing_only=True)
            plain_args = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            starred_args = [a for a in (node.args.vararg, node.args.kwarg) if a]
            for arg in [*plain_args, *starred_args]:
                if arg.annotation is not None:
                    walk(arg.annotation, typing_only=True)
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default is not None:
                    walk(default, typing_only)
            if node.returns is not None:
                walk(node.returns, typing_only=True)
            for child in node.body:
                walk(child, typing_only)
            return
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                walk(decorator, typing_only)
            for base in node.bases:
                walk(base, typing_only)
            for keyword in node.keywords:
                walk(keyword.value, typing_only)
            for param in node.type_params:
                walk(param, typing_only=True)
            for child in node.body:
                walk(child, typing_only)
            return
        if isinstance(node, ast.AnnAssign):
            walk(node.annotation, typing_only=True)
            walk(node.target, typing_only)
            if node.value is not None:
                walk(node.value, typing_only)
            return
        if isinstance(node, ast.Call):
            # ``EventEmitter._emit("live_ended", ...)`` dispatches to a
            # listener method ``on_live_ended`` via getattr — that string is
            # the only place the wiring shows up, so count it as a use.
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "_emit"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                uses.add(f"on_{node.args[0].value}")
        for child in ast.iter_child_nodes(node):
            walk(child, typing_only)

    walk(tree, typing_only=False)
    return uses


def _is_protocol(node: ast.ClassDef) -> bool:
    """Protocol classes declare a contract, not implementations."""
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
        for base in node.bases
    )


def collect_definitions(tree: ast.Module, module: str, path: Path) -> list[Definition]:
    """Public top-level classes/functions and their public methods."""
    definitions: list[Definition] = []

    def visit_body(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name.startswith("_"):
                    continue
                exempt = (
                    "decorated: invoked via the decorator (framework hook, "
                    "property or similar), never by a name in src"
                    if node.decorator_list
                    else None
                )
                definitions.append(
                    Definition(prefix + node.name, node.name, path, node.lineno, exempt)
                )
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                definitions.append(
                    Definition(prefix + node.name, node.name, path, node.lineno, None)
                )
                # A Protocol's methods are dispatched dynamically against the
                # whole listener surface; only implementations are checked.
                if not _is_protocol(node):
                    visit_body(node.body, prefix + node.name + ".")

    visit_body(tree.body, module + ".")
    return definitions


def load_whitelist(path: Path) -> dict[str, str]:
    """``qualname # reason`` lines; every entry must justify itself."""
    entries: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, reason = line.partition("#")
        key = key.strip()
        if not sep or not reason.strip():
            raise ValueError(f"{path}:{lineno}: whitelist entry without a reason")
        if key in entries:
            raise ValueError(f"{path}:{lineno}: duplicate whitelist entry {key}")
        entries[key] = reason.strip()
    return entries


def run(src_root: Path, whitelist_path: Path) -> int:
    if not src_root.is_dir():
        print(f"error: source root not found: {src_root}", file=sys.stderr)
        return 1
    if not whitelist_path.is_file():
        print(f"error: whitelist not found: {whitelist_path}", file=sys.stderr)
        return 1
    try:
        whitelist = load_whitelist(whitelist_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    definitions: list[Definition] = []
    uses: set[str] = set()
    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions.extend(
            collect_definitions(tree, module_qualname(path, src_root), path)
        )
        uses |= collect_uses(tree)

    orphans: list[Definition] = []
    whitelisted: set[str] = set()
    exempt_count = 0
    for definition in definitions:
        if definition.exempt_reason:
            exempt_count += 1
            continue
        if definition.name in uses:
            continue
        if definition.qualname in whitelist:
            whitelisted.add(definition.qualname)
            continue
        orphans.append(definition)

    stale = sorted(set(whitelist) - whitelisted)
    for qualname in stale:
        print(
            f"stale whitelist: {qualname} no longer matches an orphan — "
            f"remove it from {whitelist_path}"
        )
    for orphan in orphans:
        print(
            f"{orphan.path}:{orphan.lineno}: {orphan.qualname} "
            f"has no caller anywhere in src"
        )

    print(
        f"zero-caller check: {len(definitions)} definitions, "
        f"{exempt_count} decorated hooks exempt, {len(whitelisted)} whitelisted, "
        f"{len(orphans)} orphan(s), {len(stale)} stale whitelist entry(ies)"
    )
    if orphans or stale:
        print(
            "wire the orphan into src, or — if a framework invokes it by "
            f"magic — add it to {whitelist_path} with a reason"
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--whitelist", type=Path, default=DEFAULT_WHITELIST)
    args = parser.parse_args(argv)
    return run(args.src, args.whitelist)


if __name__ == "__main__":
    sys.exit(main())
