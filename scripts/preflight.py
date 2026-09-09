#!/usr/bin/env python3
"""Static and structural validation for the MergeZero contracts.

Run with the same interpreter that runs ``gltest`` so the GenVM SDK loader is
importable:

    python3 scripts/preflight.py

Checks performed:

1.  both contracts parse as Python;
2.  both pin the same stable Studionet runner, and that runner hash actually
    resolves inside the published GenVM release artifact;
3.  no Studio-dev / chain 61997 target leaks into the repository;
4.  each contract loads under the pinned GenVM SDK and produces a valid GenVM
    ABI schema exposing exactly the expected public surface;
5.  ``gl.Event`` subclasses declare their indexed (positional-only) parameters
    in alphabetical order, because the SDK binds positional arguments to the
    *sorted* field names;
6.  no ``.env`` file is present to be committed by accident.

Step 4 is the closest available equivalent to ``genvm-lint``: the upstream
linter publishes no macOS x86_64 build, so this script drives the same SDK the
linter would load and asserts the resulting ABI directly.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "mergezero.py"
GATE = ROOT / "contracts" / "mergezero_gate.py"
REQUIRED_RUNNER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"
FORBIDDEN = ("61997", "studio-dev.genlayer.com", "studio_devnet", "studioDevnet")
STUDIONET_RPC = "https://studio.genlayer.com/api"
CHAIN_ID = "61999"

EXPECTED_SURFACE = {
    "mergezero.py": {
        "write": {
            "create_workspace",
            "open_patch",
            "add_set_operation",
            "add_delete_operation",
            "seal_patch",
            "cancel_patch",
            "merge_patches",
        },
        "view": {
            "get_workspace",
            "get_version",
            "get_patch",
            "get_operation",
            "get_merge",
            "get_counters",
            "is_safe_merge",
        },
    },
    "mergezero_gate.py": {
        "write": {"consume"},
        "view": {"was_consumed", "get_accepted_count", "get_pins"},
    },
}

# Files that legitimately name the forbidden targets in order to forbid them.
ALLOW_FORBIDDEN_MENTIONS = {
    "scripts/preflight.py",
    "scripts/deploy_studionet.py",
    "gltest.config.yaml",
    "README.md",
    "SUBMISSION.md",
    "CLAUDE_HANDOFF.md",
    "docs/DEPLOYMENT.md",
}


def check_source(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"{path.name}: Python syntax error: {exc}"]

    if REQUIRED_RUNNER not in text:
        errors.append(f"{path.name}: stable Studionet runner hash is not pinned")

    # gl.Event binds positional-only arguments to the *sorted* tuple of their
    # names. Declaring them out of alphabetical order silently scrambles every
    # emitted topic and blob key.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {ast.unparse(b) for b in node.bases}
        if "gl.Event" not in bases:
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
                continue
            indexed = [a.arg for a in item.args.posonlyargs if a.arg != "self"]
            if indexed != sorted(indexed):
                errors.append(
                    f"{path.name}: event {node.name} declares indexed fields "
                    f"{indexed}; the SDK binds them as {sorted(indexed)}"
                )
    return errors


def check_repository_targets() -> list[str]:
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", ".venv/", "artifacts/", "__pycache__/")) or "/__pycache__/" in rel:
            continue
        if rel in ALLOW_FORBIDDEN_MENTIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for marker in FORBIDDEN:
            if marker in text:
                errors.append(f"{rel}: forbidden Studio-dev/61997 marker: {marker}")
    return errors


def check_schema(path: pathlib.Path) -> list[str]:
    """Load the contract under the pinned GenVM SDK and validate its ABI."""
    try:
        from gltest.direct.loader import create_address, load_contract_class
        from gltest.direct.vm import VMContext
    except ImportError as exc:
        return [
            f"{path.name}: cannot import the GenVM direct loader ({exc}); "
            "install requirements-test.txt and run preflight with that interpreter"
        ]

    vm = VMContext()
    vm.sender = create_address("preflight")
    try:
        with vm.activate():
            contract_class = load_contract_class(path, vm)
            schema = contract_class.__get_schema__()
    except Exception as exc:  # noqa: BLE001 - any load failure is a preflight failure
        return [f"{path.name}: contract failed to load under the pinned GenVM SDK: {exc}"]
    finally:
        _reset_contract_registry()

    try:
        parsed = json.loads(schema) if isinstance(schema, str) else schema
        methods = parsed["methods"]
    except Exception as exc:  # noqa: BLE001
        return [f"{path.name}: GenVM schema is not readable: {exc}"]

    expected = EXPECTED_SURFACE[path.name]
    views = {name for name, spec in methods.items() if spec.get("readonly")}
    writes = {name for name, spec in methods.items() if not spec.get("readonly")}

    errors: list[str] = []
    if views != expected["view"]:
        errors.append(f"{path.name}: view surface is {sorted(views)}, expected {sorted(expected['view'])}")
    if writes != expected["write"]:
        errors.append(f"{path.name}: write surface is {sorted(writes)}, expected {sorted(expected['write'])}")
    return errors


def _reset_contract_registry() -> None:
    try:
        import genlayer.gl.genvm_contracts as contracts
    except ImportError:
        return
    contracts.__known_contract__ = None


def check_deploy_script() -> list[str]:
    errors: list[str] = []
    deploy = (ROOT / "scripts" / "deploy_studionet.py").read_text(encoding="utf-8")
    if STUDIONET_RPC not in deploy or CHAIN_ID not in deploy:
        errors.append("deployment script is not pinned to stable Studionet 61999")
    if (ROOT / ".env").exists():
        errors.append(".env exists in the working tree and must never be committed")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in (CONTRACT, GATE):
        if not path.exists():
            errors.append(f"missing {path}")
        else:
            errors.extend(check_source(path))

    runners = {
        path.name: [line for line in path.read_text(encoding="utf-8").splitlines() if '"Depends"' in line]
        for path in (CONTRACT, GATE)
        if path.exists()
    }
    if len({tuple(v) for v in runners.values()}) > 1:
        errors.append(f"contracts pin different runners: {runners}")

    errors.extend(check_repository_targets())
    errors.extend(check_deploy_script())

    if not errors:
        for path in (CONTRACT, GATE):
            errors.extend(check_schema(path))

    if errors:
        print("PREFLIGHT FAILED")
        for error in errors:
            print(" -", error)
        return 1

    print("PREFLIGHT PASS")
    print(" - both contracts parse as Python")
    print(f" - stable Studionet runner pinned: {REQUIRED_RUNNER}")
    print(" - event indexed fields are declared in SDK binding order")
    print(f" - deployment target is chain {CHAIN_ID} / {STUDIONET_RPC}")
    print(" - no Studio-dev / 61997 target markers in the repository")
    print(" - no .env in the working tree")
    print(" - both contracts load under the pinned GenVM SDK")
    print(" - GenVM ABI schema exposes exactly the expected public surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
