"""Live Studionet (chain 61999) lifecycle for MergeZero.

Requires real network transactions and real validator consensus, so it is kept
out of the default ``pytest`` run. Execute explicitly with:

    gltest tests/integration/test_mergezero_studionet.py -v -s --network studionet

Every write below runs with ``leader_only: false`` and waits for FINALIZED, so a
pass means independent validators re-derived each consensus-critical verdict.
The run appends a machine-readable record to ``artifacts/studionet_evidence.json``
which is the only source for the hashes quoted in ``SUBMISSION.md``.
"""

import json
import os
import pathlib

import pytest
from genlayer_py.types import CalldataAddress, TransactionStatus
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

CONTRACT = "mergezero.py"
GATE = "mergezero_gate.py"

# Wait for FINALIZED, not merely ACCEPTED: submission evidence must be final.
TX = {
    "consensus_max_rotations": 3,
    "wait_transaction_status": TransactionStatus.FINALIZED,
    "wait_interval": 10000,
    "wait_retries": 60,
}

EVIDENCE = pathlib.Path("artifacts/studionet_evidence.json")

SCOPE = (
    "Shared service configuration. Authentication policy and recovery policy must remain coherent, "
    "while unrelated notification and request-limit settings may evolve independently."
)
BASE_STATE = {
    "auth": {"password_login": True, "mfa_required": False},
    "recovery": {"password_recovery": True, "admin_breakglass": False},
    "notifications": {"email": "ops@example.com"},
    "limits": {"daily": 1000},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class Recorder:
    """Collects finalized transaction hashes for the submission record."""

    def __init__(self):
        self.steps = []

    def ok(self, label, receipt):
        assert tx_execution_succeeded(receipt), f"{label} failed: {receipt}"
        self.steps.append(
            {
                "step": label,
                "tx_hash": receipt.get("hash") or receipt.get("tx_id"),
                "status": receipt.get("status_name"),
                "result": receipt.get("result_name"),
                "rounds": receipt.get("num_of_rounds"),
                "leader_only": str(receipt.get("leader_only")),
                "validator_votes": len(
                    (receipt.get("consensus_data") or {}).get("votes", {})
                    if isinstance(receipt.get("consensus_data"), dict)
                    else {}
                ),
            }
        )
        return receipt

    def note(self, key, value):
        self.steps.append({"note": key, "value": value})

    def write(self):
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(self.steps, indent=2), encoding="utf-8")
        print("\n=== STUDIONET EVIDENCE ===")
        print(json.dumps(self.steps, indent=2))


@pytest.fixture(scope="module")
def rec():
    recorder = Recorder()
    yield recorder
    recorder.write()


def seal(contract, rec, label, workspace, base, title, intent, path, value):
    rec.ok(f"{label}: open_patch", contract.open_patch([workspace, base, title, intent]).transact(**TX))
    patch = contract.get_counters().call()["next_patch_id"] - 1
    rec.ok(f"{label}: add_set_operation", contract.add_set_operation([patch, path, json.dumps(value)]).transact(**TX))
    rec.ok(f"{label}: seal_patch", contract.seal_patch([patch]).transact(**TX))
    return patch


def test_full_studionet_lifecycle(rec):
    account = get_default_account()
    rec.note("account", account.address)

    factory = get_contract_factory(contract_file_path=CONTRACT)
    # Set MERGEZERO_ADDRESS to continue against an existing deployment instead
    # of paying for a fresh one. The lifecycle below is written so a second
    # actor can extend an existing workspace, which is exactly what a resumed
    # run does.
    reuse = os.environ.get("MERGEZERO_ADDRESS")
    if reuse:
        address = reuse
        rec.note("mergezero_address (reused)", address)
        contract = factory.build_contract(address, account)
    else:
        deploy_receipt = factory.deploy_contract_tx(account=account, **TX)
        rec.ok("deploy MergeZero", deploy_receipt)
        address = deploy_receipt["recipient"]
        rec.note("mergezero_address", address)
        contract = factory.build_contract(address, account)

    # ---------------- workspace ----------------
    if not reuse:
        rec.ok(
            "create_workspace",
            contract.create_workspace(["Service policy", SCOPE, json.dumps(BASE_STATE)]).transact(**TX),
        )
    workspace = contract.get_workspace([1]).call()
    base = workspace["initial_version_id"]
    workspace_hash = workspace["definition_hash"]
    rec.note("workspace_definition_hash", workspace_hash)
    assert contract.get_version([base]).call()["state_json"] == canonical(BASE_STATE)

    # -------- 1. structurally disjoint, semantically conflicting --------
    conflict_a = seal(
        contract, rec, "conflict A", workspace["id"], base,
        "Disable passwords", "Disable password authentication for ordinary access.",
        "/auth/password_login", False,
    )
    conflict_b = seal(
        contract, rec, "conflict B", workspace["id"], base,
        "Keep password recovery", "Keep password recovery as the required ordinary recovery mechanism.",
        "/recovery/password_recovery", True,
    )
    versions_before = contract.get_counters().call()["next_version_id"]
    rec.ok(
        "merge_patches (semantic conflict pair)",
        contract.merge_patches([conflict_a, conflict_b]).transact(**TX),
    )
    conflict_id = contract.get_counters().call()["next_merge_id"] - 1
    conflict = contract.get_merge([conflict_id]).call()
    rec.note("conflict_receipt", conflict)

    # The paths are disjoint, so a structural merge would have accepted them.
    assert conflict["status_name"] != "STRUCTURAL_CONFLICT"
    # Whatever validators concluded, no merged state may exist.
    assert conflict["status_name"] in ("SEMANTIC_CONFLICT", "AMBIGUOUS"), conflict
    assert conflict["merged_version_id"] == 0
    assert conflict["merged_state_hash"] == ""
    assert contract.get_counters().call()["next_version_id"] == versions_before
    assert contract.is_safe_merge([conflict_id, workspace_hash, ""]).call() is False

    # -------- 2. genuinely commuting pair --------
    commute_a = seal(
        contract, rec, "commute C", workspace["id"], base,
        "Route notifications", "Move operational notifications to the platform team mailbox.",
        "/notifications/email", "platform@example.com",
    )
    commute_b = seal(
        contract, rec, "commute D", workspace["id"], base,
        "Raise daily ceiling", "Raise the independent daily request ceiling to 1500.",
        "/limits/daily", 1500,
    )
    rec.ok(
        "merge_patches (commuting pair)",
        contract.merge_patches([commute_a, commute_b]).transact(**TX),
    )
    commute_id = contract.get_counters().call()["next_merge_id"] - 1
    commute = contract.get_merge([commute_id]).call()
    rec.note("commute_receipt", commute)
    assert commute["status_name"] == "COMMUTE", commute
    assert commute["merged_version_id"] != 0

    # The merged bytes are exactly the deterministic application of both patches.
    expected = json.loads(json.dumps(BASE_STATE))
    expected["notifications"]["email"] = "platform@example.com"
    expected["limits"]["daily"] = 1500
    merged = contract.get_version([commute["merged_version_id"]]).call()
    assert merged["state_json"] == canonical(expected), merged["state_json"]
    rec.note("merged_state_json", merged["state_json"])
    rec.note("merged_state_hash", merged["state_hash"])

    parents = {merged["parent_a"], merged["parent_b"]}
    assert parents == {
        contract.get_patch([commute_a]).call()["result_version_id"],
        contract.get_patch([commute_b]).call()["result_version_id"],
    }

    # -------- 3. hash pinning --------
    state_hash = commute["merged_state_hash"]
    assert contract.is_safe_merge([commute_id, workspace_hash, state_hash]).call() is True
    assert contract.is_safe_merge([commute_id, "0" * 64, state_hash]).call() is False
    assert contract.is_safe_merge([commute_id, workspace_hash, "f" * 64]).call() is False
    assert contract.is_safe_merge([conflict_id, workspace_hash, state_hash]).call() is False
    rec.note("is_safe_merge_correct_pins", True)

    # -------- 4. pair idempotency on chain --------
    rec.ok(
        "merge_patches (reversed order, must reuse receipt)",
        contract.merge_patches([commute_b, commute_a]).transact(**TX),
    )
    assert contract.get_merge([commute_id]).call() == commute
    assert contract.get_counters().call()["next_merge_id"] == commute_id + 1

    # -------- 5. consumer contract --------
    gate_factory = get_contract_factory(contract_file_path=GATE)
    # The constructor parameter is typed Address; a bare hex string would be
    # encoded as a calldata string and fail in the storage descriptor.
    gate_receipt = gate_factory.deploy_contract_tx(
        args=[CalldataAddress(address), workspace_hash], account=account, **TX
    )
    rec.ok("deploy MergeZeroGate", gate_receipt)
    gate_address = gate_receipt["recipient"]
    rec.note("gate_address", gate_address)
    gate = gate_factory.build_contract(gate_address, account)

    rec.ok("gate consume (valid receipt)", gate.consume([commute_id, state_hash]).transact(**TX))
    assert gate.was_consumed([commute_id]).call() is True
    assert gate.get_accepted_count().call() == 1

    # The replay must be rejected. Depending on how the client surfaces a
    # reverted transaction this either returns a failing receipt or raises;
    # both outcomes prove the same thing, and the accepted count settles it.
    replay_hash = None
    try:
        replay = gate.consume([commute_id, state_hash]).transact(**TX)
        assert not tx_execution_succeeded(replay), f"replay must be rejected: {replay}"
        replay_hash = replay.get("hash")
        replay_status = replay.get("status_name")
    except AssertionError:
        raise
    except Exception as exc:
        replay_status = f"client raised: {type(exc).__name__}"
    rec.steps.append(
        {
            "step": "gate consume (replay, must be rejected)",
            "tx_hash": replay_hash,
            "status": replay_status,
            "rejected": True,
        }
    )
    assert gate.was_consumed([commute_id]).call() is True
    assert gate.get_accepted_count().call() == 1
