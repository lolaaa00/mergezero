#!/usr/bin/env python3
"""Deploy MergeZero to stable GenLayer Studionet (chain 61999).

Target is always https://studio.genlayer.com/api — never studio-dev (61997).

The account is taken from ``GENLAYER_PRIVATE_KEY`` if it is set in the
environment; otherwise a fresh Studio-funded account is generated for this run.
No key is ever read from, or written to, this repository.

Usage::

    python3 scripts/deploy_studionet.py                 # MergeZero only
    python3 scripts/deploy_studionet.py --gate <hash>   # also the consumer

Run it with the same interpreter that runs ``gltest`` so ``genlayer_py`` is
importable. The ``genlayer`` Node CLI is deliberately not used: release
candidate 0.40.0-rc.3 calls ``sim_getFeeConfig``, which the current Studio does
not implement, and its deploys finalize as NO_MAJORITY without ever being
activated. See docs/DEPLOYMENT.md.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "mergezero.py"
GATE = ROOT / "contracts" / "mergezero_gate.py"
PREFLIGHT = ROOT / "scripts" / "preflight.py"
STUDIONET_RPC = "https://studio.genlayer.com/api"
EXPECTED_CHAIN_ID = 61999


def deploy(client, account, path: pathlib.Path, args: list) -> str:
    from genlayer_py.types import TransactionStatus

    print(f"+ deploying {path.name}", flush=True)
    tx_hash = client.deploy_contract(
        code=path.read_text(encoding="utf-8"),
        args=args,
        account=account,
        consensus_max_rotations=3,
        leader_only=False,
    )
    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=TransactionStatus.FINALIZED,
        interval=10000,
        retries=60,
    )
    address = receipt["recipient"]
    print(f"  tx        {tx_hash}")
    print(f"  status    {receipt.get('status_name')} / {receipt.get('result_name')}")
    print(f"  address   {address}")
    if receipt.get("result_name") != "MAJORITY_AGREE":
        raise SystemExit(f"deployment did not reach validator majority: {receipt.get('result_name')}")
    return address


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gate",
        metavar="WORKSPACE_DEFINITION_HASH",
        help="also deploy mergezero_gate.py pinned to this workspace definition hash",
    )
    options = parser.parse_args()

    completed = subprocess.run([sys.executable, str(PREFLIGHT)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    try:
        from genlayer_py import create_account, create_client
        from genlayer_py.chains import studionet
    except ImportError as exc:
        print(f"ERROR: genlayer_py is not importable ({exc}).", file=sys.stderr)
        print("Install requirements-test.txt and run this with that interpreter.", file=sys.stderr)
        return 2

    if int(studionet.id) != EXPECTED_CHAIN_ID:
        print(f"ERROR: genlayer_py studionet is chain {studionet.id}, expected {EXPECTED_CHAIN_ID}.", file=sys.stderr)
        return 2

    account = create_account(os.environ.get("GENLAYER_PRIVATE_KEY") or None)
    client = create_client(chain=studionet, account=account, endpoint=STUDIONET_RPC)

    print(f"Target: stable Studionet chain {EXPECTED_CHAIN_ID} ({STUDIONET_RPC})")
    print(f"Account: {account.address}")

    result = {"chain_id": EXPECTED_CHAIN_ID, "rpc": STUDIONET_RPC, "account": account.address}
    result["mergezero"] = deploy(client, account, CONTRACT, [])
    if options.gate:
        from genlayer_py.types import CalldataAddress

        # Typed Address parameter: a bare hex string encodes as a calldata string.
        result["gate"] = deploy(
            client, account, GATE, [CalldataAddress(result["mergezero"]), options.gate]
        )

    out = ROOT / "artifacts" / "studionet_deployment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
