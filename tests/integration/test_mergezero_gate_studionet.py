"""Live consumer proof against an already-deployed MergeZero on Studionet 61999.

The consumer needs an existing `COMMUTE` receipt, so it is driven separately
from the main lifecycle rather than redeploying MergeZero for it. Supply the
deployment produced by ``test_mergezero_studionet.py``:

    MERGEZERO_ADDRESS=0x... MERGEZERO_MERGE_ID=2 \\
    gltest tests/integration/test_mergezero_gate_studionet.py -q -s --network studionet

Proves one successful consumption and one rejected replay, both finalized.
"""

import json
import os
import pathlib

import pytest
from genlayer_py.types import CalldataAddress, TransactionStatus
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

GATE = "mergezero_gate.py"
SOURCE = "mergezero.py"

TX = {
    "consensus_max_rotations": 3,
    "wait_transaction_status": TransactionStatus.FINALIZED,
    "wait_interval": 10000,
    "wait_retries": 60,
}

EVIDENCE = pathlib.Path("artifacts/studionet_gate_evidence.json")


@pytest.fixture(scope="module")
def deployment():
    address = os.environ.get("MERGEZERO_ADDRESS")
    if not address:
        pytest.skip("set MERGEZERO_ADDRESS to a deployed MergeZero on chain 61999")
    return address, int(os.environ.get("MERGEZERO_MERGE_ID", "2"))


def test_gate_consumes_once_and_rejects_replay(deployment):
    address, merge_id = deployment
    account = get_default_account()
    steps = []

    source = get_contract_factory(contract_file_path=SOURCE).build_contract(address, account)
    receipt = source.get_merge([merge_id]).call()
    assert receipt["status_name"] == "COMMUTE", receipt
    workspace_hash = source.get_workspace([receipt["workspace_id"]]).call()["definition_hash"]
    state_hash = receipt["merged_state_hash"]
    assert state_hash

    # The constructor parameter is typed Address; a bare hex string would be
    # encoded as a calldata string and fail in the storage descriptor.
    gate_factory = get_contract_factory(contract_file_path=GATE)
    deploy_receipt = gate_factory.deploy_contract_tx(
        args=[CalldataAddress(address), workspace_hash], account=account, **TX
    )
    assert tx_execution_succeeded(deploy_receipt), deploy_receipt
    gate_address = deploy_receipt["recipient"]
    steps.append({"step": "deploy MergeZeroGate", "tx_hash": deploy_receipt["hash"], "status": deploy_receipt["status_name"], "result": deploy_receipt["result_name"], "address": gate_address})
    gate = gate_factory.build_contract(gate_address, account)

    # The binding is verifiable on chain and has no setter.
    pins = gate.get_pins().call()
    assert pins["mergezero_address"].lower() == address.lower()
    assert pins["expected_workspace_hash"] == workspace_hash
    assert gate.get_accepted_count().call() == 0

    # 1. A receipt pinned to the wrong state hash is refused, and writes nothing.
    try:
        bad = gate.consume([merge_id, "f" * 64]).transact(**TX)
        assert not tx_execution_succeeded(bad), f"wrong state hash must be refused: {bad}"
        bad_status = bad.get("status_name")
        bad_hash = bad.get("hash")
    except AssertionError:
        raise
    except Exception as exc:
        bad_status, bad_hash = f"client raised: {type(exc).__name__}", None
    steps.append({"step": "consume with wrong state hash (must be refused)", "tx_hash": bad_hash, "status": bad_status, "rejected": True})
    assert gate.get_accepted_count().call() == 0
    assert gate.was_consumed([merge_id]).call() is False

    # 2. The correct pins are accepted exactly once.
    good = gate.consume([merge_id, state_hash]).transact(**TX)
    assert tx_execution_succeeded(good), good
    steps.append({"step": "consume with correct pins", "tx_hash": good["hash"], "status": good["status_name"], "result": good["result_name"]})
    assert gate.was_consumed([merge_id]).call() is True
    assert gate.get_accepted_count().call() == 1

    # 3. Replay of the same receipt is rejected and does not double-count.
    try:
        replay = gate.consume([merge_id, state_hash]).transact(**TX)
        assert not tx_execution_succeeded(replay), f"replay must be rejected: {replay}"
        replay_status = replay.get("status_name")
        replay_hash = replay.get("hash")
    except AssertionError:
        raise
    except Exception as exc:
        replay_status, replay_hash = f"client raised: {type(exc).__name__}", None
    steps.append({"step": "consume replay (must be rejected)", "tx_hash": replay_hash, "status": replay_status, "rejected": True})
    assert gate.get_accepted_count().call() == 1

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    record = {"mergezero_address": address, "merge_id": merge_id, "gate_address": gate_address, "workspace_hash": workspace_hash, "merged_state_hash": state_hash, "steps": steps}
    EVIDENCE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("\n=== GATE EVIDENCE ===")
    print(json.dumps(record, indent=2))
