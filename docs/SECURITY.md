# Security model

## The one thing consensus is allowed to decide

Validators answer exactly one question about two already-frozen patches:

> Under this workspace's frozen scope, do these two exact changes semantically commute?

The answer is one of `COMMUTE`, `CONFLICT`, `AMBIGUOUS`. Nothing else the model
emits is read. Every byte of a merged version is recomputed by the contract from
the two sealed operation lists.

## Fail-closed boundaries

Deterministic, checked before any consensus round is spent:

- a patch cannot be merged with itself;
- both patches must be `SEALED` (drafts and cancelled patches are rejected);
- both patches must belong to the same workspace;
- both patches must name the same immutable base version;
- every sealed operation's recorded base pre-image hash is re-derived from that
  base version and must match, so "authored against this exact base" is a
  checked property rather than an assumption;
- same-path and ancestor/descendant path pairs are `STRUCTURAL_CONFLICT`;
- `A→B` and `B→A` must produce byte-identical canonical JSON;
- a merged document larger than the state bound is rejected outright;
- if deterministic application fails for any other reason, the call reverts:
  no version, no receipt, no consensus round.

After consensus:

- only `COMMUTE` creates a version;
- `SEMANTIC_CONFLICT` and `AMBIGUOUS` create a receipt and nothing else;
- any malformed, missing, or unrecognised verdict normalises to `AMBIGUOUS`;
- a classification that throws for any reason returns `AMBIGUOUS`;
- instruction-like control text anywhere in the semantic context (scope, base
  state, either patch payload) short-circuits to `AMBIGUOUS` before the model is
  invoked at all.

## Validator independence

The leader proposes only `{verdict, reason}`. Every validator independently
re-runs the same bounded classification and compares its own verdict against the
leader's. Diagnostic wording need not match; the verdict must.

A validator rejects a leader result that is:

- not a `gl.vm.Return` (the leader errored);
- not a mapping;
- a mapping whose normalised verdict differs from its own.

Because unknown verdict tokens normalise to `AMBIGUOUS`, a leader cannot smuggle
a merge through by inventing a verdict string.

## The first resolution is final

A pair key commits to the workspace, the common base version, both patch ids and
both patch definition hashes. Once a pair resolves, every later
`merge_patches` call for that pair — in either argument order — returns the
original receipt without re-running consensus.

This is deliberate. It makes pair resolution idempotent and order-independent,
and it removes verdict grinding: an attacker cannot re-roll a `CONFLICT` or
`AMBIGUOUS` pair until a model happens to answer `COMMUTE`.

## Deterministic output guarantee

Even a valid `COMMUTE` leader cannot influence output bytes. The contract
recomputes the merged state itself from the sealed operation records, then
canonicalises and hashes it. A leader that returns extra fields
(`merged_state`, `state_json`, …) has them discarded; only `verdict` and a
length-bounded `reason` survive.

## Consumer pinning

`is_safe_merge(merge_id, expected_workspace_hash, expected_state_hash)` returns
true only when the receipt is `COMMUTE`, has a merged version, and both hashes
match exactly.

The workspace definition hash commits to **owner, name, scope and initial state
hash**. Without the owner, two parties could publish identically defined
workspaces and a consumer pinned to one would accept the other's receipts.

`contracts/mergezero_gate.py` shows the intended consumption pattern: the source
address and workspace hash are burned in at construction and have no setter, the
answer must be a strict boolean `true`, and each merge id can be consumed once.
The replay key is the merge id alone — keying on the caller-supplied state hash
would let a caller vary the key without varying the receipt.

## Prompt-injection posture

Workspace name, workspace scope and patch title/intent are rejected at write
time if they contain known control phrases. The same phrase list is applied to
the whole assembled semantic context (scope, base state, both patch payloads)
immediately before classification; a hit returns `AMBIGUOUS` without invoking
the model. Patch values are bounded JSON and reach the model only as quoted
data inside a prompt that states the data is untrusted.

This is conservative by design: a legitimate document containing one of those
phrases becomes unmergeable rather than a possible injection vector.

## Known limits

- MergeZero does not judge whether either patch is good in isolation.
- It does not perform three-way text merging and does not auto-resolve anything.
- Semantic relationships that are not derivable structurally depend on the
  workspace scope and patch intents being descriptive.
- `merge_patches` is permissionless. Anyone can resolve a pair of sealed
  patches, and because the first resolution is final, a third party can settle a
  pair before its authors do. The outcome is still derived only from immutable
  data, but participants who need to control *when* a pair is judged should not
  seal both patches before they are ready.
- Path traversal covers object keys only. Arrays are supported as values but are
  not addressable element-by-element.
- A legitimate state containing common prompt-control phrases is treated
  conservatively as ambiguous.
