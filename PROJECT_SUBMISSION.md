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
6. **Appeals** re-decide a precedent's original case. The same approve/reject outcome affirms the precedent, and affirmations raise its weight in retrieval. A different, confident verdict overturns it, marking the old precedent superseded.
7. **Amendments** (admin-proposed only) are judged against the core principles and settled precedent, and adopted only if approved.
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
| Same approve/reject outcome (and the same kind of non-approval) | The on-chain consequence. Conditions aren't voted on, and the leader's are stored. Requiring them to match made re-runs by larger validator sets end undetermined. |
| Same answer to "does this ruling depart from precedent?" | Breaking with case law is the most consequential interpretive act. |
| Cited precedents overlap (Jaccard ≥ 0.5) | "Substantially the same precedents", without demanding identical lists. |
| Consistency within one step; confidence within 20 points | Graded judgments get bands. |

Reasoning and holding text are never compared. Borderline cases disagree on purpose, so GenLayer rotates the leader instead of committing a coin-flip ruling that would bind every later case.

## What judges can verify

- Source: https://github.com/Lexiweb31/precedent-interpreter
- Contract: [contracts/precedent_interpreter.py](contracts/precedent_interpreter.py) (class `PrecedentInterpreter`)
- Design notes (state, equivalence, edge cases, integration): [docs/precedent-interpreter.md](docs/precedent-interpreter.md)
- Network: GenLayer Bradbury testnet

- Deployed contract: [`0x048A6D9a69173D6AB7272f2d5611af51CBDe3981`](https://explorer-bradbury.genlayer.com/address/0x048A6D9a69173D6AB7272f2d5611af51CBDe3981)
- Deployment record: [deployments.json](deployments.json)

### Live consensus on Bradbury

The deployed contract holds a 5-clause Community Grants Charter and the following case law, each ruling decided by validator consensus (`AGREE`):

| # | Case | Verdict | Cites | Consistency | Conf. | Outcome | Transaction |
|---|---|---|---|---|---|---|---|
| 1 | Open-source block indexer grant | approved_with_conditions | none | novel | 95 | precedent #1 | [0x83a2cb…78d50](https://explorer-bradbury.genlayer.com/tx/0x83a2cb9ba13b4b0e0e623c019ca561d0accc5e63febdc91d3bcab7c494e78d50) |
| 2 | Library maintenance grant, **license URL fetched live by validators** | approved_with_conditions | #1 | high | 100 | precedent #2 | [0x717661…6a3f0](https://explorer-bradbury.genlayer.com/tx/0x717661259cee8ad086639d4f1bdad110ea784dc408c8f4b35ef9d85dbfa6a3f0) |
| 3 | Open-source transaction simulator grant | approved_with_conditions | #1, #2 | high | 95 | precedent #3 | [0xfb7691…fe6a2](https://explorer-bradbury.genlayer.com/tx/0xfb769104e0b370d813fbbbe3e4e0086d86cb43db12d999eaa7b65f7af7cfe6a2) |
| 4 | Influencer campaign + buyback for a token | rejected | none | novel | 90 | precedent #4 | [0xc08bf6…58972](https://explorer-bradbury.genlayer.com/tx/0xc08bf6c37f5809f16b797c541f058e2f9f15c785ca01cb824b891120e5658972) |
| 5 | Appeal of #4 ("raises ecosystem awareness") | rejected | #1, #2, #3 | high | 100 | #4 affirmed | [0x2d026d…dc701](https://explorer-bradbury.genlayer.com/tx/0x2d026d1d6fda48e677c9087e7e9a8065e13ac24e880d9434711aeee9c88dc701) |

Cases 1–4 are `READY_TO_FINALIZE` (past their appeal window); the appeal was still `ACCEPTED` (inside its window) at the last check.

Case 2 shows the full Intelligent Contract path: each validator fetched `https://raw.githubusercontent.com/jquery/jquery/main/LICENSE.txt` inside the consensus round (`sources: ok`) and independently agreed the grant is compatible, citing precedent #1.

### What earlier deployments taught

Earlier deployments ([deployments-v1.json](deployments-v1.json), [deployments-v2.json](deployments-v2.json)) showed two problems this version fixes:

- Fetching evidence with the browser renderer timed out every round, so the contract now uses `web.get` first.
- Requiring validators to agree on *whether* conditions attach made re-runs by larger validator sets end `UNDETERMINED`, so the vote is now on approve versus reject.

Bradbury still often times out rounds (no state change) and intermittently reverts the outer transaction. The deploy script retries both, and `--check` re-reads final statuses later.

### Tests

- `tests/direct/`: 33 in-memory tests with mocked web and LLM calls. They cover precedent creation and citation, retrieval, conditions and verdict normalisation, malformed output, insufficient evidence with retry, failed fetches, appeals (affirm, overturn, low-confidence), amendments, policy drafting, access control, and each equivalence rule, by re-running the validator against different mocked answers.
- `tests/direct/test_contract_size.py`: Bradbury's deploy gas covers source **and** constructor args. This test holds the source at 19.3 KB or less and ASCII-only.

## Recommended live demonstration

1. On the deployed contract, call `get_policy()` to see the charter, its core principles and the case count.
2. Call `get_recent_precedents(10, true)` to see the in-force case law, with holdings, citations and affirmations.
3. Call `find_relevant_precedents(["tooling"], "open-source wallet SDK")` to see exactly which precedents a new grant would be judged against.
4. Call `get_verdict(3)` to see the compact answer another contract would gate on.
5. To reproduce: put a funded Bradbury key in `.env` as `DEPLOYER_PRIVATE_KEY`, then run `python scripts/deploy_bradbury.py --demo`, and later `--check` to re-read final statuses.
