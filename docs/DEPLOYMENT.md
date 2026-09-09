# Deployment

## Required target

- Network: **GenLayer Studionet**
- Chain ID: **61999**
- RPC: `https://studio.genlayer.com/api`
- Explorer: `https://genlayer-explorer.vercel.app`

Do not use `studio-dev`, `studio_devnet`, `studio-dev.genlayer.com`, or chain
61997 for this submission. `scripts/preflight.py` fails the build if any of
those markers appear in the repository.

## Toolchain note: use the Python client, not the Node CLI

Deployments here go through `genlayer-py` (via `gltest` or
`scripts/deploy_studionet.py`), **not** the `genlayer` Node CLI.

The CLI version available at the time of this submission (`0.40.0-rc.3`) is not
compatible with the current hosted Studio:

- `genlayer estimate-fees` fails with `Method not found: sim_getFeeConfig`;
- `genlayer deploy --rpc https://studio.genlayer.com/api` submits a transaction
  that finalizes as `NO_MAJORITY` with `activator: ''`, `num_of_rounds: 0` and
  zero votes committed — the transaction is never activated, so no validator
  ever executes it.

This was confirmed to be a client problem, not a contract or network problem, by
deploying a fifteen-line contract with no logic through the same CLI: it failed
identically. The same contracts deploy and reach `MAJORITY_AGREE` with five
validators through `genlayer-py`.

## Steps

1. Install the test/deployment dependencies:

   ```bash
   pip install -r requirements-test.txt
   ```

2. Run Direct Mode tests:

   ```bash
   gltest tests/direct -q
   ```

3. Run preflight (contract load + GenVM ABI validation):

   ```bash
   python3 scripts/preflight.py
   ```

4. Deploy. `GENLAYER_PRIVATE_KEY` is used if set; otherwise a fresh
   Studio-funded account is generated for the run. Never put a key in this
   repository.

   ```bash
   python3 scripts/deploy_studionet.py
   ```

   To also deploy the consumer, pass the workspace definition hash it should
   pin:

   ```bash
   python3 scripts/deploy_studionet.py --gate <workspace_definition_hash>
   ```

5. Run the full reviewer lifecycle against the live network:

   ```bash
   gltest tests/integration/test_mergezero_studionet.py -q -s --network studionet
   ```

   Every write waits for `FINALIZED` and runs with `leader_only: false`. The run
   writes `artifacts/studionet_evidence.json`, which is the only source for the
   transaction hashes quoted in `SUBMISSION.md`.

   To continue against an existing deployment instead of paying for a new one:

   ```bash
   MERGEZERO_ADDRESS=0x... gltest tests/integration/test_mergezero_studionet.py -q -s --network studionet
   ```

6. Record the finalized addresses, transaction hashes and source commit in
   `SUBMISSION.md`.

## `genvm-lint`

The upstream GenVM linter is not available in this environment: the `genvm`
releases publish only `linux-amd64`, `linux-arm64` and `macos-arm64` artifacts,
and none of them is a linter build. `scripts/preflight.py` covers the same
ground by loading each contract under the exact pinned runner SDK and asserting
the GenVM ABI schema it produces, plus repo-specific static checks. See the
"Preflight" section of the README.

## Secrets

Never put a private key or seed phrase into this repository, a shell transcript,
or submission documentation. `.env` is git-ignored and preflight fails if one
exists in the working tree.
