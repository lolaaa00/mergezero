#!/usr/bin/env python3
"""Prove that a deployed contract is byte-identical to the source in this repo.

    python3 scripts/verify_deployment.py 0x1FC99a00650a98e0339346506760C5F10931BBAa
    python3 scripts/verify_deployment.py <gate address> --contract contracts/mergezero_gate.py

Fetches the source stored on chain 61999 and compares it byte-for-byte with the
local file. Needs nothing but ``requests``; no account and no signing.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RPC = "https://studio.genlayer.com/api"


def fetch_source(address: str) -> bytes:
    import requests

    response = requests.post(
        RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": "gen_getContractCode", "params": [address]},
        timeout=60,
    )
    payload = response.json()
    if "error" in payload:
        raise SystemExit(f"RPC error: {payload['error']}")
    result = payload["result"]
    raw = bytes.fromhex(result[2:]) if isinstance(result, str) and result.startswith("0x") else str(result).encode()
    return base64.b64decode(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("address", help="deployed contract address on chain 61999")
    parser.add_argument(
        "--contract",
        default="contracts/mergezero.py",
        help="repository source to compare against (default: contracts/mergezero.py)",
    )
    options = parser.parse_args()

    local_path = ROOT / options.contract
    local = local_path.read_bytes()
    deployed = fetch_source(options.address)

    print(f"address   {options.address}")
    print(f"local     {options.contract}  {len(local)} bytes  sha256 {hashlib.sha256(local).hexdigest()}")
    print(f"deployed  {len(deployed)} bytes  sha256 {hashlib.sha256(deployed).hexdigest()}")

    if deployed == local:
        print("\nIDENTICAL: the deployed contract is exactly this source.")
        return 0

    print("\nMISMATCH: the deployed contract is NOT this source.", file=sys.stderr)
    import difflib

    diff = difflib.unified_diff(
        deployed.decode("utf-8", "replace").splitlines(),
        local.decode("utf-8", "replace").splitlines(),
        "deployed",
        "local",
        lineterm="",
    )
    for line in list(diff)[:80]:
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
