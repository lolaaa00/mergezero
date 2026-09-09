"""Direct Mode coverage for the MergeZeroGate consumer contract.

Direct Mode loads exactly one contract per test and does not execute real
cross-contract calls, so ``is_safe_merge`` is answered here by a stub installed
on the VM. That isolates the property these tests exist to prove: the gate's own
pinning and replay logic. The end-to-end cross-contract path is proved on chain
(see ``docs/DEPLOYMENT.md``).
"""

import pytest

from support import GATE, sdk_types

WORKSPACE_HASH = "a" * 64
STATE_HASH = "b" * 64


@pytest.fixture
def gate(direct_vm, direct_deploy):
    Address, _ = sdk_types()
    source = Address(bytes.fromhex("11" * 20))
    return direct_deploy(GATE, source, WORKSPACE_HASH)


def stub_source(direct_vm, answer, *, calls=None):
    """Answer the gate's cross-contract ``is_safe_merge`` view with *answer*."""
    _, calldata = sdk_types()

    def hook(vm, request):
        call = request.get("CallContract")
        if call is None:
            return None
        if calls is not None:
            calls.append(call["calldata"])
        return bytes([0]) + calldata.encode(answer)

    direct_vm._gl_call_hook = hook


def test_gate_starts_empty(gate):
    assert gate.get_accepted_count() == 0
    assert gate.was_consumed(1) is False


def test_gate_forwards_its_pinned_workspace_hash(direct_vm, gate):
    calls = []
    stub_source(direct_vm, True, calls=calls)
    gate.consume(1, STATE_HASH)
    assert len(calls) == 1
    assert calls[0]["method"] == "is_safe_merge"
    # The caller supplies the merge id and state hash; the workspace hash is the
    # one burned into the gate at construction and can never be overridden.
    assert calls[0]["args"] == [1, WORKSPACE_HASH, STATE_HASH]


def test_gate_accepts_a_safe_receipt_once(direct_vm, gate):
    stub_source(direct_vm, True)
    gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 1
    assert gate.was_consumed(7) is True


def test_gate_rejects_replay_of_a_consumed_receipt(direct_vm, gate):
    calls = []
    stub_source(direct_vm, True, calls=calls)
    gate.consume(7, STATE_HASH)
    with direct_vm.expect_revert("already consumed"):
        gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 1
    # Replay short-circuits before the cross-contract call is made at all.
    assert len(calls) == 1


def test_replay_cannot_be_bypassed_by_varying_the_state_hash(direct_vm, gate):
    """The replay key is the merge id, not the caller-supplied hash."""
    stub_source(direct_vm, True)
    gate.consume(7, STATE_HASH)
    with direct_vm.expect_revert("already consumed"):
        gate.consume(7, "c" * 64)
    assert gate.get_accepted_count() == 1


def test_gate_rejects_a_receipt_the_source_does_not_vouch_for(direct_vm, gate):
    stub_source(direct_vm, False)
    with direct_vm.expect_revert("not a safe pinned merge"):
        gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 0
    assert gate.was_consumed(7) is False


def test_a_rejected_receipt_can_still_be_consumed_later(direct_vm, gate):
    """A failed consume writes no state, so it does not burn the merge id."""
    stub_source(direct_vm, False)
    with direct_vm.expect_revert("not a safe pinned merge"):
        gate.consume(7, STATE_HASH)
    stub_source(direct_vm, True)
    gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 1


def test_gate_fails_closed_when_the_source_is_unreachable(direct_vm, gate):
    """No hook installed: the cross-contract view yields nothing usable."""
    with direct_vm.expect_revert():
        gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 0
    assert gate.was_consumed(7) is False


@pytest.mark.parametrize("answer", [None, 0, "", "true", [], {}])
def test_gate_rejects_non_true_answers_from_the_source(direct_vm, gate, answer):
    stub_source(direct_vm, answer)
    with direct_vm.expect_revert():
        gate.consume(7, STATE_HASH)
    assert gate.get_accepted_count() == 0


def test_distinct_receipts_are_tracked_independently(direct_vm, gate):
    stub_source(direct_vm, True)
    gate.consume(1, STATE_HASH)
    gate.consume(2, "c" * 64)
    assert gate.get_accepted_count() == 2
    assert gate.was_consumed(1) is True
    assert gate.was_consumed(2) is True
    assert gate.was_consumed(3) is False
