# Precedent-Based Policy Interpreter

A GenLayer Intelligent Contract that interprets a natural-language policy the way courts interpret law: every ruling is reached by validator consensus, stored as a precedent, and weighed by later cases. Rulings can be appealed and superseded, and amendments to the policy must themselves pass judgment.

- Contract: [contracts/precedent_interpreter.py](contracts/precedent_interpreter.py)
- Design notes (state, Equivalence Principle, edge cases, integration): [docs/precedent-interpreter.md](docs/precedent-interpreter.md)
- Submission summary: [PROJECT_SUBMISSION.md](PROJECT_SUBMISSION.md)

## Deploy

Constructor: `(policy_title, policy_text, core_principles="", min_precedent_confidence=60)`

Bradbury's deploy gas cap covers source **and** constructor args. The source is kept at 19.3 KB or less and ASCII-only (enforced by `tests/direct/test_contract_size.py`), leaving about 1 KB for the opening policy. Load longer policies with `extend_policy(text)` before the first case. `python scripts/deploy_bradbury.py --demo` deploys and runs a demo; it reads `DEPLOYER_PRIVATE_KEY` from the environment or `.env`.

## Live on Bradbury testnet

Contract [`0x048A6D9a69173D6AB7272f2d5611af51CBDe3981`](https://explorer-bradbury.genlayer.com/address/0x048A6D9a69173D6AB7272f2d5611af51CBDe3981), deployed with a 5-clause Community Grants Charter. Every ruling below was reached by validator consensus; full records are in [deployments.json](deployments.json).

| # | Case | Verdict | Cites | Consistency | Conf. | Outcome | Transaction |
|---|---|---|---|---|---|---|---|
| 1 | Open-source block indexer grant | approved_with_conditions | none | novel | 95 | precedent #1 | [0x83a2cb…78d50](https://explorer-bradbury.genlayer.com/tx/0x83a2cb9ba13b4b0e0e623c019ca561d0accc5e63febdc91d3bcab7c494e78d50) |
| 2 | Library maintenance grant, **license URL fetched live by validators** | approved_with_conditions | #1 | high | 100 | precedent #2 | [0x717661…6a3f0](https://explorer-bradbury.genlayer.com/tx/0x717661259cee8ad086639d4f1bdad110ea784dc408c8f4b35ef9d85dbfa6a3f0) |
| 3 | Open-source transaction simulator grant | approved_with_conditions | #1, #2 | high | 95 | precedent #3 | [0xfb7691…fe6a2](https://explorer-bradbury.genlayer.com/tx/0xfb769104e0b370d813fbbbe3e4e0086d86cb43db12d999eaa7b65f7af7cfe6a2) |
| 4 | Influencer campaign + buyback for a token | rejected | none | novel | 90 | precedent #4 | [0xc08bf6…58972](https://explorer-bradbury.genlayer.com/tx/0xc08bf6c37f5809f16b797c541f058e2f9f15c785ca01cb824b891120e5658972) |
| 5 | Appeal of #4 ("raises ecosystem awareness") | rejected | #1, #2, #3 | high | 100 | #4 affirmed | [0x2d026d…dc701](https://explorer-bradbury.genlayer.com/tx/0x2d026d1d6fda48e677c9087e7e9a8065e13ac24e880d9434711aeee9c88dc701) |

Cases 1–4 are `READY_TO_FINALIZE` (past their appeal window); the appeal was still `ACCEPTED` (inside its window) at the last check.

Case 2 shows the full Intelligent Contract path: each validator fetched `https://raw.githubusercontent.com/jquery/jquery/main/LICENSE.txt` inside the consensus round (`sources: ok`) and independently agreed the grant is compatible, citing precedent #1.

Earlier deployments ([deployments-v1.json](deployments-v1.json), [deployments-v2.json](deployments-v2.json)) showed two problems this version fixes:

- Fetching evidence with the browser renderer timed out every round, so the contract now uses `web.get` first.
- Requiring validators to agree on *whether* conditions attach made re-runs by larger validator sets end `UNDETERMINED`, so the vote is now on approve versus reject.

Bradbury still often times out rounds (no state change) and intermittently reverts the outer transaction. The deploy script retries both, and `--check` re-reads final statuses later.

## Test

```bash
pip install -r requirements.txt
# Direct mode runs in memory with mocked LLM/web. gltest still reads
# gltest.config.yaml, so any dummy key works:
DEPLOYER_PRIVATE_KEY=0x$(printf '1%.0s' {1..64}) pytest tests/direct -v
genvm-lint check contracts/precedent_interpreter.py
```
