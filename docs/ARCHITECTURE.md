# Architecture

## Trust boundary

MergeZero deliberately gives the LLM one narrow authority: classify **pairwise semantic commutativity** for two frozen, structurally disjoint patches created from the same immutable base.

It cannot:

- choose a base version;
- alter either patch;
- add an operation;
- change an operation path or value;
- create a compromise;
- select the output state;
- approve structurally overlapping changes;
- make `AMBIGUOUS` mergeable.

## Deterministic pipeline

```text
same workspace + same base?
        |
        v
sealed immutable patches
        |
        v
path overlap? -------- yes ------> STRUCTURAL_CONFLICT
        |
       no
        v
A then B bytes == B then A bytes?
        |
        no ----------------------> STRUCTURAL_CONFLICT
        |
       yes
        v
GenLayer semantic consensus
    /       |       \
COMMUTE  CONFLICT  AMBIGUOUS
   |         |         |
   v         v         v
create      no        no
version    state     state
```

The merged version is generated from exact original operations after consensus; no LLM output is used as data for the state transition except the bounded verdict.

## Version DAG

Each sealed patch creates an immutable child version. A successful pair merge creates a new version whose two parents are the patch child versions. This preserves complete lineage without pretending the workspace has one globally canonical head.

## Pair idempotency

The pair key commits to the workspace, the common base version, both patch IDs
and both patch definition hashes. Reversing the caller order returns the same
existing merge receipt and does not spend another consensus round.

Because the first resolution is final, a pair cannot be re-judged. That is what
prevents verdict grinding: an attacker cannot retry a `CONFLICT` or `AMBIGUOUS`
pair until some model run happens to answer `COMMUTE`.

## Base binding

Each sealed operation stores the Keccak-256 hash of the value its path held in
the base version at the time the operation was added (or a sentinel of 64 zeros
if the path was absent). At merge time the contract re-derives all of those
hashes from the common base version and requires an exact match, so "both
patches were authored against this exact immutable base" is verified rather than
assumed. Those same hashes are folded into the patch definition hash, which is
in turn folded into the pair key.

## Event topics

`gl.Event` binds positional-only (indexed) arguments to the **sorted** tuple of
their names rather than to declaration order. Every event here therefore
declares its indexed fields alphabetically, and `scripts/preflight.py` fails the
build if that ordering is ever broken — otherwise the emitted topics and blob
keys silently describe the wrong values.
