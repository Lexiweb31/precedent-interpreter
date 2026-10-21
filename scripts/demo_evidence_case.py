"""
Add a live-evidence case to the contract in deployments.json: a grant whose
licensing claim is backed by an evidence URL that every validator fetches
inside the consensus round. Appends the result to deployments.json.

    python scripts/demo_evidence_case.py
"""
import json
import sys

from genlayer_py import create_account, create_client
from genlayer_py.chains import testnet_bradbury

from deploy_bradbury import ROOT, _env, _interpret, _send, _view

TITLE = "Fund maintenance of an MIT-licensed JavaScript library"
DESC = ("Request 15,000 USDC for a year of security fixes and docs for an open-source library used across "
        "ecosystem frontends. The license is linked as evidence; quarterly public reports will be published.")
TAGS = ["tooling", "maintenance"]
EVIDENCE = ["https://raw.githubusercontent.com/jquery/jquery/main/LICENSE.txt"]


def main() -> int:
    record = json.loads((ROOT / "deployments.json").read_text())
    client = create_client(chain=testnet_bradbury, account=create_account(_env("DEPLOYER_PRIVATE_KEY")))
    address = record["address"]
    _send(client, address, "submit_proposal", [TITLE, DESC, TAGS, EVIDENCE])
    pid = _view(client, address, "get_policy")["proposals"]
    case = _interpret(client, address, pid, "live evidence URL")
    if case["ruling"]:
        print(f"    sources: {case['ruling']['sources']}")
    record["cases"].append(case)
    record["precedents_in_force"] = [
        {k: p[k] for k in ("id", "title", "verdict", "holding", "relevant_precedent_ids", "affirmations")}
        for p in _view(client, address, "get_recent_precedents", 10, True)]
    (ROOT / "deployments.json").write_text(json.dumps(record, indent=2) + "\n")
    print("updated deployments.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
