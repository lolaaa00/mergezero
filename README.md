# MergeZero

**Semantic concurrency-safe merging for GenLayer Intelligent Contracts.**

MergeZero lets two actors propose structurally disjoint changes from the same immutable base version, then uses GenLayer consensus to decide whether those exact changes **semantically commute**. If they do, the merged state is produced deterministically from the already-sealed patches. The LLM never writes, rewrites, or compromises the resulting state.

## Why this primitive exists

Ordinary merge systems detect structural conflicts: two changes touching the same field. Autonomous agents create a harder class of failure: two changes can touch different fields while contradicting each other in meaning.

Example:

- Patch A changes `/auth/password_login` to `false` with the intent “disable password authentication for ordinary access”.
- Patch B changes `/recovery/password_recovery` to `true` with the intent “password recovery remains the required recovery path”.

The JSON paths are disjoint, so an ordinary structural merge accepts both. MergeZero asks independent GenLayer validators whether the two frozen changes can safely coexist under the workspace's frozen scope.

## Core invariant

> **Consensus may decide whether the original patches commute. Consensus never authors the merged state.**

The protocol therefore separates judgement from mutation:

1. deterministic checks prove both patches are sealed, share one workspace, and
   name the same immutable base version;
2. every operation's recorded base pre-image hash is re-derived from that base
   version and must match;
3. overlapping/ancestor paths are rejected without an LLM;
4. both exact application orders are computed deterministically and must match byte-for-byte;
5. validators independently classify the pair as `COMMUTE`, `CONFLICT`, or `AMBIGUOUS`;
6. only `COMMUTE` creates a merged version;
7. the merged JSON is the exact deterministic result of applying both sealed patches.

The verdict is the *only* thing read from the model. Any other field it returns
is discarded, an unrecognised verdict normalises to `AMBIGUOUS`, and a pair's
first resolution is final — so a rejected pair can never be re-rolled into a
merge.

## State model

- **Workspace** — owner, frozen semantic scope, initial state and definition hash.
- **Version** — immutable canonical JSON state plus parent/version lineage.
- **Patch** — author, immutable base version, bounded intent, operation list and definition hash.
- **PatchOperation** — `SET` or `DELETE` on a bounded JSON-pointer-like path.
- **MergeReceipt** — pair hash, consensus status, reason, exact merged version if safe.

This forms a persistent version DAG rather than a mutable “current document”. Consumers choose which version/merge receipt they trust.

## Public statuses

- `COMMUTE` — semantic consensus agrees both exact changes can coexist.
- `STRUCTURAL_CONFLICT` — same/ancestor path collision or byte-level order mismatch.
- `SEMANTIC_CONFLICT` — disjoint changes undermine or contradict each other.
- `AMBIGUOUS` — validators cannot safely establish commutativity.

`CONFLICT` and `AMBIGUOUS` never create a merged version.

## Supported patch surface

The initial state is a bounded JSON object. Patch paths are a conservative JSON-pointer-like subset such as:

```text
/auth/mfa_required
/notifications/email
/limits/daily
```

Segments use letters, digits, `_` and `-`. Arrays are allowed as values but not addressed by numeric path traversal. Parent objects must already exist. A single patch cannot contain overlapping ancestor/descendant operations.

Floating-point values are rejected; integer/string/bool/null/list/object values are canonicalized deterministically.

## Consumer contract

`contracts/mergezero_gate.py` is a deliberately tiny proof of reuse. A consumer pins:

- the MergeZero contract address;
- the expected workspace definition hash;
- a merged state hash.

It accepts a receipt only when `is_safe_merge(...)` returns a strict boolean
`true` — the receipt is `COMMUTE`, it has a merged version, and both hashes match
exactly. Each merge id can be consumed once; the replay key is the merge id
alone, so a caller cannot mint a fresh key by varying the state hash they pass.

There is **no frontend**. This repo is intentionally a standalone Intelligent Contract primitive, not a Project submission.

## Network

Target: **stable GenLayer Studionet, chain ID 61999**, RPC
`https://studio.genlayer.com/api`. This repository intentionally does **not**
target the Studio development preview on chain 61997.

Both contracts pin the stable runner:

```text
py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6
```

MergeZero is deployed and proved live on 61999. Addresses, finalized transaction
hashes and the full lifecycle record are in [`SUBMISSION.md`](SUBMISSION.md) and
[`docs/studionet_evidence.json`](docs/studionet_evidence.json).

## Test locally in Direct Mode

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-test.txt
gltest tests/direct -q
```

Direct Mode loads the contracts under the exact pinned GenVM runner, so no
network and no funded account are required.

The suite is in three files:

- `tests/direct/test_mergezero.py` — core deterministic and consensus behaviour.
- `tests/direct/test_mergezero_adversarial.py` — same-base enforcement, stale
  bases, patch immutability, ancestor/descendant collisions, byte-level
  commutativity against an independent Keccak recomputation, malformed and
  forged consensus results, ambiguity failing closed, verdict grinding, input
  bounds, and workspace/state hash pinning.
- `tests/direct/test_mergezero_gate.py` — consumer pinning and replay rejection.

## Preflight

```bash
python3 scripts/preflight.py
```

This parses both contracts, checks the pinned runner, rejects any Studio-dev /
61997 marker anywhere in the repository, verifies that every `gl.Event` declares
its indexed fields in the order the SDK actually binds them, then loads each
contract under the pinned GenVM SDK and asserts the resulting GenVM ABI schema.

The upstream `genvm-lint` binary is not published for this platform (GenVM
releases ship `linux-amd64`, `linux-arm64` and `macos-arm64` runtime artifacts
only), so preflight drives the same SDK the linter would load instead. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Live Studionet test

```bash
gltest tests/integration/test_mergezero_studionet.py -q -s --network studionet
```

Runs the full reviewer lifecycle against stable hosted Studionet (61999) with
`leader_only: false`, waiting for `FINALIZED` on every write, and records
`artifacts/studionet_evidence.json`. Run it only after Direct Mode and preflight
pass.

## Deploy

```bash
python3 scripts/deploy_studionet.py
```

Deploys to `https://studio.genlayer.com/api` (chain 61999) through
`genlayer-py`. `GENLAYER_PRIVATE_KEY` is used if set; otherwise a fresh
Studio-funded account is generated for the run. No key is ever read from or
written to this repository.

The `genlayer` Node CLI is deliberately not used — release candidate
`0.40.0-rc.3` is incompatible with the current hosted Studio. The reasoning and
the evidence for that are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Verify a deployment

Confirm that a deployed address is running exactly this source, with no account
and no signing:

```bash
python3 scripts/verify_deployment.py <address>
```

## Reviewer demo

See [`docs/REVIEWER_DEMO.md`](docs/REVIEWER_DEMO.md). The highest-signal demo is one pair that is structurally disjoint but semantically conflicting, followed by one genuinely commuting pair that creates a version whose bytes can be independently recomputed from the two sealed patches.
