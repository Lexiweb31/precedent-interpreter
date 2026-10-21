# Precedent-Based Policy Interpreter: GenLayer Project Submission

## One-line description

A GenLayer Intelligent Contract that interprets a natural-language policy the way courts interpret law. Every ruling is reached by validator consensus, stored as a citable precedent, and weighed by later cases. Rulings can be appealed and superseded, and amendments to the policy must themselves pass judgment.

## The problem

Communities, DAOs, grant programs, research collaborations and agent operators all govern themselves with written rules: constitutions, guidelines, protocols, mandates. Applying those rules to a new case is interpretation, not computation.

- Token voting turns interpretation into popularity, and is inconsistent from one vote to the next.
- Deterministic code can't read the rule at all.
- A single hosted model can read it, but it's a trusted third party, and it forgets: nothing makes today's ruling consistent with last month's.

## How it works

1. A policy is deployed with **core principles** that can never be amended. Longer policies are loaded with `extend_policy` before the first case.
2. Anyone submits a proposal: a title, description, tags and optional evidence URLs.
3. Anyone triggers `interpret()`. The contract deterministically selects the most relevant **in-force precedents** from storage, using its tag index, keyword overlap and how often a precedent has been affirmed.
4. Validators fetch the evidence live and each judge the case against the policy text and those precedents with their own LLM. They must agree on a structured ruling: verdict, cited precedents, whether the ruling departs from precedent, consistency, conditions, confidence, and a one-sentence **holding**.
5. A confident ruling becomes a new precedent. Later cases are shown its holding and must follow it or explicitly depart from it.
6. **Appeals** re-decide a precedent's original case. The same verdict affirms the precedent, and affirmations raise its weight in retrieval. A different, confident verdict overturns it, marking the old precedent superseded.
7. **Amendments** (admin-proposed only) are judged against the core principles and settled precedent, and adopted only on a plain `approved` verdict.
8. Other contracts gate actions with `get_verdict(proposal_id)`, which returns status, verdict, compatibility and binding conditions.

The admin is deliberately weak: it can pause, propose amendments, and draft the policy before the first case. It can never edit the policy directly once cases exist, and never edit rulings or precedents.

## Why GenLayer is essential

The core decision is about meaning: is this action compatible with the letter and spirit of a written rule, read in light of how it has been read before? Only GenLayer lets independent validators each read live evidence, each run their own model, and commit one agreed ruling that becomes shared, permanent, citable state for every later case and every other contract.

## Equivalence Principle design

Two models never write the same reasoning, so `strict_eq` can't work. `prompt_comparative` would hand the "do these match?" decision to yet another subjective LLM. This contract uses a custom validator (`gl.vm.run_nondet`):

- Each validator **re-runs the full interpretation independently**: its own fetches, its own LLM, never seeing the leader's answer first.
- Both answers go through the same normalisation, and validators then compare decision fields with deterministic rules.

| Rule | Purpose |
|---|---|
| The leader's ruling must be unchanged by re-normalisation and cite only precedents it was shown | Catches doctored or malformed leader results. |
| The same evidence sources must be readable | Stops a leader from hiding evidence by claiming a fetch failed. |
| Identical verdict | The on-chain consequence. Approval with and without binding conditions are distinct verdicts. |
| Same answer to "does this ruling depart from precedent?" | Breaking with case law is the most consequential interpretive act. |
| Cited precedents overlap (Jaccard ≥ 0.5) | "Substantially the same precedents", without demanding identical lists. |
| Consistency within one step; confidence within 20 points | Graded judgments get bands. |

Reasoning and holding text are never compared. Borderline cases disagree on purpose, so GenLayer rotates the leader instead of committing a coin-flip ruling that would bind every later case.

## What judges can verify

- Source: https://github.com/Lexiweb31/precedent-interpreter
- Contract: [contracts/precedent_interpreter.py](contracts/precedent_interpreter.py) (class `PrecedentInterpreter`)
- Design notes (state, equivalence, edge cases, integration): [docs/precedent-interpreter.md](docs/precedent-interpreter.md)
- Network: GenLayer Bradbury testnet

- Deployed contract: [`0xa6D97D6dc275F67D4467e409C01327F1bDAd7b37`](https://explorer-bradbury.genlayer.com/address/0xa6D97D6dc275F67D4467e409C01327F1bDAd7b37)
- Deployment record: [deployments.json](deployments.json)

### Live consensus on Bradbury

The deployed contract holds a 5-clause Community Grants Charter and the following case law. Each ruling was decided by validator consensus (`AGREE`). Case 1 is `FINALIZED`; cases 2–4 are `READY_TO_FINALIZE`, past their appeal window.

| # | Case | Verdict | Cites | Consistency | Conf. | Outcome | Transaction |
|---|---|---|---|---|---|---|---|
| 1 | Open-source block indexer grant | approved_with_conditions | none | novel | 95 | precedent #1 | [0x095281…1e014](https://explorer-bradbury.genlayer.com/tx/0x095281cfa76f3a2d08c49a07044778e6b66f6eb7eb0e9e61a56ba9028b01e014) |
| 2 | Open-source transaction simulator grant | approved_with_conditions | #1 | high | 95 | precedent #2 | [0x1d9a3c…a00cb](https://explorer-bradbury.genlayer.com/tx/0x1d9a3cf5b9aa7d6d79a17852278e649c2101965b53eacaedd2abde75e7da00cb) |
| 3 | Influencer campaign + buyback for a token | rejected | #1, #2 | high | 99 | precedent #3 | [0xc2c0d4…fbd06](https://explorer-bradbury.genlayer.com/tx/0xc2c0d445e449bfd44ff1080b37853117b3db6972cb0bd4c0de2e03a0504fbd06) |
| 4 | Appeal of #3 ("raises ecosystem awareness") | rejected | #1, #2 | high | 100 | #3 affirmed | [0x612344…e1dd9](https://explorer-bradbury.genlayer.com/tx/0x61234421492b1e90e57fead73220a3c29fa7fa1815f0f597ff95a2cd77ce1dd9) |

Holding stored for precedent #3: *"Grants for public-good open-source work are permissible only when they are not used for marketing, token promotion, or price support, and they must serve the ecosystem rather than a private token's price."*

### Live evidence fetching: honest status

- **First contract:** a case with an evidence URL timed out in all five rounds tried. The evidence fetcher then used only the browser renderer (`web.render`).
- **Fix:** the current source fetches with plain `web.get` first and renders only HTML pages. It's deployed at [`0xfE3DE78e…57262`](https://explorer-bradbury.genlayer.com/address/0xfE3DE78ef881cb471C00d8316759DfAd27657262). There, the evidence case's first round was `ACCEPTED / AGREE`: every validator fetched the license file (`ok: true`) and agreed on *approved_with_conditions*, citing precedent #1.
- **Re-runs:** that round and two others on this contract were later re-run by validators and ended `UNDETERMINED`, so none of their rulings was applied ([deployments-v2.json](deployments-v2.json)). A likely cause is that the equivalence rule treats *approved* and *approved_with_conditions* as different verdicts. The larger validator set re-running a round can split on whether to attach conditions. That trade-off is open: it makes conditional rulings strict but harder to finalise.

Known network behaviour: Bradbury frequently ends rounds with `LEADER_TIMEOUT` / `VALIDATORS_TIMEOUT` (no state change), occasionally reverts the outer EVM transaction, and dropped RPC connections twice during these runs. The scripts retry all three.

### Tests

- `tests/direct/`: 33 in-memory tests with mocked web and LLM calls. They cover precedent creation and citation, retrieval, conditions and verdict normalisation, malformed output, insufficient evidence with retry, failed fetches, appeals (affirm, overturn, low-confidence), amendments, policy drafting, access control, and each equivalence rule, by re-running the validator against different mocked answers.
- `tests/direct/test_contract_size.py`: Bradbury's deploy gas covers source **and** constructor args. This test holds the source at 19.3 KB or less and ASCII-only.

## Recommended live demonstration

1. On the deployed contract, call `get_policy()` to see the charter, its core principles and the case count.
2. Call `get_recent_precedents(10, true)` to see the in-force case law, with holdings, citations and affirmations.
3. Call `find_relevant_precedents(["tooling"], "open-source wallet SDK")` to see exactly which precedents a new grant would be judged against.
4. Call `get_verdict(3)` to see the compact answer another contract would gate on.
5. To reproduce: put a funded Bradbury key in `.env` as `DEPLOYER_PRIVATE_KEY`, then run `python scripts/deploy_bradbury.py --demo && python scripts/demo_evidence_case.py`. `demo_evidence_case.py <id>` retries an existing proposal.
