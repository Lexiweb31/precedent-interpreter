# Precedent-Based Policy Interpreter

A GenLayer Intelligent Contract that interprets a natural-language policy the way courts interpret law: every ruling is reached by validator consensus, stored as a precedent, and weighed by later cases. Rulings can be appealed and superseded, and amendments to the policy must themselves pass judgment.

- Contract: [contracts/precedent_interpreter.py](contracts/precedent_interpreter.py)
- Design notes (state, Equivalence Principle, edge cases, integration): [docs/precedent-interpreter.md](docs/precedent-interpreter.md)
- Submission summary: [PROJECT_SUBMISSION.md](PROJECT_SUBMISSION.md)

## Deploy

Constructor: `(policy_title, policy_text, core_principles="", min_precedent_confidence=60)`

Bradbury's deploy gas cap covers source **and** constructor args. The source is kept at 19.3 KB or less and ASCII-only (enforced by `tests/direct/test_contract_size.py`), leaving about 1 KB for the opening policy. Load longer policies with `extend_policy(text)` before the first case. `python scripts/deploy_bradbury.py --demo` deploys and runs a demo; it reads `DEPLOYER_PRIVATE_KEY` from the environment or `.env`.

## Live on Bradbury testnet

Contract [`0xa6D97D6dc275F67D4467e409C01327F1bDAd7b37`](https://explorer-bradbury.genlayer.com/address/0xa6D97D6dc275F67D4467e409C01327F1bDAd7b37), deployed with a 5-clause Community Grants Charter. Every ruling below was reached by validator consensus; full records are in [deployments.json](deployments.json).

| # | Case | Verdict | Cites | Consistency | Conf. | Outcome |
|---|---|---|---|---|---|---|
| 1 | Open-source block indexer grant | approved_with_conditions | none | novel | 95 | precedent #1 |
| 2 | Open-source transaction simulator grant | approved_with_conditions | #1 | high | 95 | precedent #2 |
| 3 | Influencer campaign + buyback for a token | rejected | #1, #2 | high | 99 | precedent #3 |
| 4 | Appeal of #3 ("raises ecosystem awareness") | rejected | #1, #2 | high | 100 | #3 affirmed |

Holding stored for #3: *"Grants for public-good open-source work are permissible only when they are not used for marketing, token promotion, or price support, and they must serve the ecosystem rather than a private token's price."*

A fifth case with a live evidence URL timed out in every round on this contract. The source now fetches with `web.get` before falling back to the browser renderer. On a redeploy of that fix, validators fetched the evidence and agreed in the first round, but the rounds were then re-run and ended undetermined. See [PROJECT_SUBMISSION.md](PROJECT_SUBMISSION.md#live-evidence-fetching-honest-status) and [deployments-v2.json](deployments-v2.json).

Some rounds needed retries: one `NO_MAJORITY` (validators split, so the equivalence check refused to commit) and several leader or validator timeouts, which are common on Bradbury and leave state unchanged.

## Test

```bash
pip install -r requirements.txt
# Direct mode runs in memory with mocked LLM/web. gltest still reads
# gltest.config.yaml, so any dummy key works:
DEPLOYER_PRIVATE_KEY=0x$(printf '1%.0s' {1..64}) pytest tests/direct -v
genvm-lint check contracts/precedent_interpreter.py
```
