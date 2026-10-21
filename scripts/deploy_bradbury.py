"""
Deploy PrecedentInterpreter to GenLayer Bradbury testnet and (optionally) build
a small body of case law on it under real validator consensus:

  1. an open-source tooling grant          -> expected approved (novel)
  2. a similar tooling grant               -> expected to cite precedent #1
  3. a token marketing campaign            -> expected rejected
  4. an appeal of the marketing ruling     -> expected affirmed

    # .env
    DEPLOYER_PRIVATE_KEY=0x...   # admin; needs testnet GEN for gas

    python scripts/deploy_bradbury.py           # deploy only
    python scripts/deploy_bradbury.py --demo    # deploy + cases

Writes deployments.json. Bradbury sometimes times out a consensus round
(LEADER_TIMEOUT / VALIDATORS_TIMEOUT) without changing state; interpret() is
retried, since a timed-out round leaves the proposal open.
"""
import json
import os
import sys
import time
from pathlib import Path

from eth_utils import decode_hex
from genlayer_py import create_account, create_client
from genlayer_py.abi import calldata
from genlayer_py.abi.transactions import serialize
from genlayer_py.chains import testnet_bradbury
from genlayer_py.contracts.utils import make_calldata_object
from genlayer_py.exceptions import GenLayerError

ROOT = Path(__file__).resolve().parents[1]
EXPLORER = "https://explorer-bradbury.genlayer.com"
COMMITTED = ("ACCEPTED", "FINALIZED")
TIMEOUTS = ("LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "UNDETERMINED")

POLICY_TITLE = "Community Grants Charter"
POLICY = (
    "1. Grants fund open-source public goods for the ecosystem: tooling, research, education, infrastructure.\n"
    "2. Funded work must be released under an OSI-approved license.\n"
    "3. Grants must not fund marketing campaigns, token promotion, price support or speculation.\n"
    "4. Recipients publish a public progress report each quarter; the committee may attach conditions.\n"
    "5. A single grant may not exceed 50,000 USDC."
)
CORE = "Funds serve public goods only and never benefit a private token's price."

CASES = [
    ("open-source indexer", ["tooling", "infrastructure"],
     "Fund an open-source block indexer",
     "Request 30,000 USDC to build an MIT-licensed block indexer and public API that any wallet or "
     "explorer can self-host. Deliverables: indexer, docs, quarterly reports."),
    ("similar tooling grant", ["tooling"],
     "Fund an open-source transaction simulator",
     "Request 20,000 USDC for an Apache-2.0 transaction simulator CLI for developers, with docs and "
     "quarterly public reports. Builds on the same open tooling approach as earlier indexer grants."),
    ("marketing campaign", ["marketing"],
     "Influencer campaign for the XYZ token",
     "Request 40,000 USDC to pay influencers to promote the XYZ token and run a buyback to support "
     "its price during launch week."),
]
APPEAL = ("The campaign would raise awareness of the ecosystem, which indirectly benefits public goods.")


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def _wait(client, tx_hash) -> dict:
    receipt = client.wait_for_transaction_receipt(transaction_hash=tx_hash, interval=10000, retries=120)
    print(f"    tx {tx_hash}  {receipt.get('status_name')} {receipt.get('result_name') or ''}")
    return receipt


def _committed(receipt) -> bool:
    return (
        receipt.get("status_name") in COMMITTED
        and receipt.get("result_name") in ("AGREE", "MAJORITY_AGREE")
        and receipt.get("tx_execution_result_name") == "FINISHED_WITH_RETURN"
    )


def _send(client, address, method, args, attempts=3):
    """Send a write; resend if Bradbury reverts the EVM wrapper tx (no state change)."""
    for i in range(attempts):
        try:
            tx_hash = client.write_contract(address=address, function_name=method, args=args)
            return tx_hash, _wait(client, tx_hash)
        except GenLayerError as e:
            if "Transaction failed" not in str(e) or i == attempts - 1:
                raise
            print(f"    reverted send, retrying ({i + 1}/{attempts - 1})")
            time.sleep(10)


def _view(client, address, method, *args):
    # Testnet's gen_call wraps the payload as {"data": <hex>}; decode it directly.
    data = serialize([calldata.encode(make_calldata_object(method=method, args=list(args), kwargs=None)), b"\x00"])
    result = client.provider.make_request(method="gen_call", params=[{
        "type": "read", "to": address, "from": client.local_account.address,
        "data": data, "transaction_hash_variant": "latest-nonfinal",
    }])["result"]
    raw = result["data"] if isinstance(result, dict) else result
    out = calldata.decode(decode_hex("0x" + raw))
    return json.loads(out) if isinstance(out, str) else out


def _interpret(client, address, proposal_id: int, label: str) -> dict:
    print(f"case: {label} (proposal {proposal_id})")
    for attempt in range(3):
        tx_hash, r = _send(client, address, "interpret", [proposal_id])
        if _committed(r) or r.get("status_name") not in TIMEOUTS:
            break
        print(f"    consensus round timed out, retrying ({attempt + 1}/2)")
    ruling = _view(client, address, "get_proposal", proposal_id).get("ruling") if _committed(r) else None
    if ruling:
        print(f"    -> {ruling['verdict']} / {ruling['outcome']} / cites {ruling['relevant_precedent_ids']} "
              f"/ {ruling['consistency_with_precedents']} / conf {ruling['confidence']}")
    return {"label": label, "proposal_id": proposal_id, "tx": tx_hash, "status": r.get("status_name"),
            "result": r.get("result_name"), "ruling": ruling}


def main() -> int:
    key = _env("DEPLOYER_PRIVATE_KEY")
    if not key:
        print("DEPLOYER_PRIVATE_KEY is not set (env or .env)")
        return 1
    admin = create_account(key)
    client = create_client(chain=testnet_bradbury, account=admin)
    print(f"admin {admin.address}\ndeploying PrecedentInterpreter...")
    code = (ROOT / "contracts" / "precedent_interpreter.py").read_text()
    tx_hash = client.deploy_contract(code=code, args=[POLICY_TITLE, POLICY, CORE, 60])
    receipt = _wait(client, tx_hash)
    if not _committed(receipt):
        print("deploy did not commit")
        return 1
    address = (receipt.get("tx_data_decoded") or {}).get("contract_address") or receipt["recipient"]
    print(f"  contract {address}\n  {EXPLORER}/address/{address}")
    record = {"network": "testnet_bradbury", "contract": "PrecedentInterpreter", "address": address,
              "admin": admin.address, "deploy_tx": tx_hash, "explorer": f"{EXPLORER}/address/{address}",
              "cases": []}

    def save():
        (ROOT / "deployments.json").write_text(json.dumps(record, indent=2) + "\n")

    save()
    if "--demo" in sys.argv:
        marketing_precedent = 0
        for label, tags, title, desc in CASES:
            _send(client, address, "submit_proposal", [title, desc, tags, []])
            pid = _view(client, address, "get_policy")["proposals"]
            case = _interpret(client, address, pid, label)
            record["cases"].append(case)
            save()
            if label == "marketing campaign" and case["ruling"]:
                marketing_precedent = case["ruling"]["precedent_id"]
        if marketing_precedent:
            _send(client, address, "appeal", [marketing_precedent, APPEAL, []])
            pid = _view(client, address, "get_policy")["proposals"]
            record["cases"].append(_interpret(client, address, pid, f"appeal of #{marketing_precedent}"))
        record["policy"] = _view(client, address, "get_policy")
        record["precedents_in_force"] = [
            {k: p[k] for k in ("id", "title", "verdict", "holding", "relevant_precedent_ids", "affirmations")}
            for p in _view(client, address, "get_recent_precedents", 10, True)]
        save()
    print("wrote deployments.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
