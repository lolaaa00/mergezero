# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *


@gl.contract_interface
class IMergeZero:
    class View:
        def is_safe_merge(
            self,
            merge_id: u256,
            expected_workspace_hash: str,
            expected_state_hash: str,
        ) -> bool: ...

    class Write:
        pass


class MergeZeroGate(gl.Contract):
    """Minimal consumer proving that MergeZero receipts are reusable on-chain."""

    mergezero_address: Address
    expected_workspace_hash: str
    consumed: TreeMap[str, bool]
    accepted_count: u256

    def __init__(self, mergezero_address: Address, expected_workspace_hash: str):
        self.mergezero_address = mergezero_address
        self.expected_workspace_hash = str(expected_workspace_hash)
        self.accepted_count = u256(0)

    @gl.public.write
    def consume(self, merge_id: u256, expected_state_hash: str) -> None:
        # The replay key is the merge id alone. A merge receipt has exactly one
        # merged state hash, so keying on the caller-supplied hash as well would
        # let a caller vary the key without varying the receipt being consumed.
        key = str(int(merge_id))
        if bool(self.consumed.get(key, False)):
            raise gl.vm.UserError("EXPECTED: merge receipt already consumed")
        source = IMergeZero(self.mergezero_address)
        ok = source.view().is_safe_merge(
            merge_id,
            self.expected_workspace_hash,
            str(expected_state_hash),
        )
        # Require a strict boolean true. The pinned source is expected to be
        # MergeZero, but a consumer must never treat an arbitrary truthy value
        # (a non-empty string, a number) as an approval.
        if ok is not True:
            raise gl.vm.UserError("EXPECTED: MergeZero receipt is not a safe pinned merge")
        self.consumed[key] = True
        self.accepted_count = u256(int(self.accepted_count) + 1)

    @gl.public.view
    def was_consumed(self, merge_id: u256) -> bool:
        return bool(self.consumed.get(str(int(merge_id)), False))

    @gl.public.view
    def get_accepted_count(self) -> u256:
        return self.accepted_count

    @gl.public.view
    def get_pins(self) -> dict:
        """What this consumer is bound to. Both are set at construction and
        have no setter, so a reader can verify the binding on chain."""
        return {
            "mergezero_address": str(self.mergezero_address),
            "expected_workspace_hash": str(self.expected_workspace_hash),
        }
