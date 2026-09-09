# Reviewer demo

The whole sequence below is automated as a single live test:

```bash
gltest tests/integration/test_mergezero_studionet.py -q -s --network studionet
```

It runs against stable Studionet (chain 61999) with `leader_only: false`, waits
for `FINALIZED` on every write, and writes `artifacts/studionet_evidence.json`.
The finalized results of the run quoted in `SUBMISSION.md` came from exactly
this test.

## 1. Deploy

Deploy `contracts/mergezero.py` to `https://studio.genlayer.com/api`.

## 2. Create a workspace

Initial state:

```json
{
  "auth": {"password_login": true, "mfa_required": false},
  "recovery": {"password_recovery": true, "admin_breakglass": false},
  "notifications": {"email": "ops@example.com"},
  "limits": {"daily": 1000}
}
```

Scope:

> Shared service configuration. Authentication policy and recovery policy must
> remain coherent, while unrelated notification and request-limit settings may
> evolve independently.

## 3. Prove hidden semantic conflict

Both patches are opened on the same initial version.

| | Patch A | Patch B |
|---|---|---|
| path | `/auth/password_login` | `/recovery/password_recovery` |
| value | `false` | `true` |
| intent | Disable password authentication for ordinary access. | Keep password recovery as the required ordinary recovery mechanism. |

The JSON paths are structurally disjoint, so an ordinary structural merge would
accept the pair. Call `merge_patches(A, B)` and show:

- the receipt status is `SEMANTIC_CONFLICT` (not `STRUCTURAL_CONFLICT` — the
  deterministic layer had no objection);
- `merged_version_id == 0` and `merged_state_hash == ""`;
- `get_counters().next_version_id` is unchanged, so no version was created;
- `is_safe_merge(...)` is false for this receipt under any pins.

## 4. Prove genuine commutativity

From the same initial version:

| | Patch C | Patch D |
|---|---|---|
| path | `/notifications/email` | `/limits/daily` |
| value | `"platform@example.com"` | `1500` |
| intent | Move operational notifications to the platform team mailbox. | Raise the independent daily request ceiling to 1500. |

Call `merge_patches(C, D)` and show:

- status `COMMUTE` with a non-zero `merged_version_id`;
- the merged version's parents are C's and D's result versions;
- the merged `state_json` equals the base state with exactly those two fields
  changed, in canonical form — recomputable off-chain;
- `merged_state_hash` is the Keccak-256 of those exact bytes;
- `is_safe_merge(merge_id, workspace_hash, state_hash)` is `true`;
- it is `false` with a wrong workspace hash, a wrong state hash, or the conflict
  receipt's id.

## 5. Prove pair idempotency on chain

Call `merge_patches(D, C)` — reversed order. The receipt is byte-identical to
the one from step 4, `next_merge_id` does not advance, and no second consensus
round is spent.

## 6. Consumer proof

Deploy `mergezero_gate.py` with the MergeZero address and the workspace
definition hash, then:

- `consume(merge_id, merged_state_hash)` succeeds once — `accepted_count` becomes
  1 and `was_consumed(merge_id)` becomes true;
- calling `consume` again for the same merge id is rejected as already consumed,
  and `accepted_count` stays 1.

This is optional proof of reuse; the core submission remains the MergeZero
primitive.
