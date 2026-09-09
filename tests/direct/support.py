"""Shared Direct Mode helpers for the MergeZero suites."""

import json
from pathlib import Path

CONTRACT = "contracts/mergezero.py"
GATE = "contracts/mergezero_gate.py"

# Matches the first line of semantic_prompt(). Direct Mode routes any prompt
# containing this marker to the mocked verdict.
CLASSIFIER = r"MERGEZERO / SEMANTIC COMMUTATIVITY CHECK"

SCOPE = (
    "Shared service configuration. Authentication policy and recovery policy must remain coherent, "
    "while unrelated notification and observability settings may evolve independently."
)

BASE_STATE = {
    "auth": {"password_login": True, "mfa_required": False},
    "recovery": {"password_recovery": True, "admin_breakglass": False},
    "notifications": {"email": "ops@example.com"},
    "limits": {"daily": 1000},
    "deep": {"a": {"b": {"c": 1, "d": 2}}},
}
BASE = json.dumps(BASE_STATE)


def canonical(value):
    """The exact canonical form MergeZero stores and hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sdk_types():
    """Import SDK types (Address, calldata) without deploying a contract first."""
    from gltest.direct.sdk_loader import setup_sdk_paths

    setup_sdk_paths(Path(GATE).resolve())
    from genlayer import Address
    from genlayer.py import calldata

    return Address, calldata


def deploy_workspace(direct_deploy, scope=SCOPE, state=BASE, name="Service policy"):
    contract = direct_deploy(CONTRACT)
    workspace = contract.create_workspace(name, scope, state)
    initial = contract.get_workspace(workspace)["initial_version_id"]
    return contract, workspace, initial


def sealed_set(contract, workspace, base, title, intent, path, value):
    patch = contract.open_patch(workspace, base, title, intent)
    contract.add_set_operation(patch, path, json.dumps(value))
    version = contract.seal_patch(patch)
    return patch, version


def sealed_delete(contract, workspace, base, title, intent, path):
    patch = contract.open_patch(workspace, base, title, intent)
    contract.add_delete_operation(patch, path)
    version = contract.seal_patch(patch)
    return patch, version


def mock_verdict(vm, verdict, reason="pair is semantically compatible"):
    """Mock the classifier the way the runtime delivers it.

    ``exec_prompt(response_format="json")`` hands the contract a decoded mapping,
    which Direct Mode reproduces by parsing a JSON *string* mock. Passing bytes
    here would model a payload the runtime does not actually produce.
    """
    mock_raw(vm, json.dumps({"verdict": verdict, "reason": reason}))


def mock_raw(vm, payload):
    """Mock an arbitrary (possibly malformed) classifier payload."""
    vm.clear_mocks()
    vm.mock_llm(CLASSIFIER, payload)
