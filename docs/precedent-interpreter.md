# Precedent-Based Policy Interpreter: design notes

Source: [contracts/precedent_interpreter.py](../contracts/precedent_interpreter.py). The contract keeps its in-source docs short, because Bradbury rejects deploys over roughly 20 KB of source. This file holds the full rationale.

## What it is

A reusable GenLayer Intelligent Contract that stores a natural-language policy, such as a constitution, grant charter, research protocol or agent mandate. It accumulates **precedents**: structured rulings that later cases must weigh.

Token voting can't interpret the spirit of a written rule consistently. Deterministic code can't interpret it at all. A single hosted model isn't neutral. This contract has independent validators, each running its own LLM, agree on every ruling, and it makes every ruling citable, appealable and binding on later cases.

## Lifecycle

```
submit_proposal / propose_amendment (admin) / appeal(precedent)
        |
        v
   PENDING --interpret()--> RULED                  (verdict recorded)
      ^  |                   +- confidence >= min  -> new Precedent
      |  |                   +- confidence <  min  -> "ruled_non_binding"
      |  +--> INSUFFICIENT_EVIDENCE --add_evidence()--> interpret() again (max 3 attempts)
      +-- withdraw() by proposer
```

`interpret()` is permissionless. Anyone may pay to have an open case judged.

| Case kind | Outcomes |
|---|---|
| `action` | `precedent_set`, `ruled_non_binding`, `insufficient_evidence` |
| `amendment` | `amendment_adopted` (only on a plain `approved`), `amendment_rejected` |
| `appeal` | `affirmed` (same verdict: affirmations +1), `overturned` (new precedent; old one gets `superseded_by`), `not_overturned_low_confidence` |

## State design

| Field | Why |
|---|---|
| `policy_text`, `policy_version`, `policy_updated_at` | The current law. Each precedent records the version it was judged under, and the prompt tells the model to weigh older-version rulings less where the text changed. |
| `core_principles` | Entrenched at deploy and never writable. Amendments are judged against it, so the admin can't amend the policy into something else. |
| `proposals: DynArray[Proposal]` | Every case, with status, attempts, evidence URLs and the last full ruling (`ruling_json`). Ids are 1-based, so 0 means none. |
| `precedents: DynArray[Precedent]` | Append-only case law. Typed fields hold what retrieval and appeals use (`verdict`, `holding`, `superseded_by`, `affirmations`, `appeals`, `policy_version`). The full normalised ruling plus evidence fetch status sits in `ruling_json`. |
| `tag_index: TreeMap[str, DynArray[u256]]` | Tag to precedent ids, so retrieval doesn't scan all history. |
| `keywords` (per precedent) | Deterministic keyword set from the title, description and holding, used for scoring. |
| `admin`, `paused` | Deliberately weak. The admin can pause and propose amendments. It can't edit policy, rulings or precedents. |

The **holding** (a one-sentence general rule, without names) is what makes precedents reusable. Later prompts show holdings and conditions, not the whole earlier case.

### Deterministic precedent retrieval

`_select_candidates()` runs **outside** the non-deterministic block, so the leader and every validator judge against exactly the same candidate set:

- Pool: the newest 24 precedents, plus the newest 48 ids under each of the case's tags.
- Score: 3 per shared tag, plus 1 per shared keyword, plus affirmations (capped at 3). Superseded precedents are skipped, because they're no longer good law. Under an appeal, the precedent being appealed is excluded from the pool and shown separately.
- The top 8 by score are kept, with ties going to the newest. A case with no overlap gets none, which makes it a case of first impression.

`find_relevant_precedents(tags, text)` exposes the same function, so a frontend can show a proposer exactly which precedents their case will be judged against before they submit it.

## How consensus and the Equivalence Principle work

`interpret()` reads storage, builds a plain-value context and calls `gl.vm.run_nondet(leader_fn, validator_fn)`:

1. **Leader:** fetches every evidence URL live (`gl.nondet.web.render`), builds the prompt and calls `gl.nondet.exec_prompt`. It then normalises the answer into a fixed schema and returns `{ruling, sources}`.
2. **Validator:** runs the **same `leader_fn` independently**: its own fetches, its own LLM call, its own normalisation. It never sees the leader's answer before forming its own, so it can't rubber-stamp. It then calls `_rulings_equivalent(leader, mine)`.
3. State is written in `_apply()`, **only after** consensus returns.

### `_rulings_equivalent` rules

| # | Rule | Why |
|---|---|---|
| 0 | The leader's ruling must survive re-normalisation unchanged, and cite only precedent ids that were shown | Normalisation is idempotent, so a doctored or malformed leader result (invented ids, `compatible` contradicting `verdict`, unclamped confidence) fails here. |
| 0 | The same evidence sources must be readable (per-URL `ok` flags) | Stops a leader from claiming a source failed in order to suppress it, and stops agreement over different evidence. |
| 1 | `verdict` must be identical (`compatible` is derived from it) | The verdict is the on-chain consequence. `approved` and `approved_with_conditions` are distinct, because whether obligations attach is a decision. |
| 1b | Both `insufficient_evidence`: agree | Abstaining changes no law. Only the case record changes. |
| 2 | Both must agree on whether the ruling **departs from precedent** | Breaking with case law is the most consequential interpretive act, so it must be shared. |
| 3 | Cited precedent sets need Jaccard overlap of at least 0.5, and "novel" only if both cite none | "Substantially the same precedents" without demanding identical lists. |
| 3b | `consistency_with_precedents` within one step (low/medium/high) | A graded judgment, so a band is fair. |
| 4 | `confidence` within 20 points | It feeds the binding threshold, so wildly different certainty is not agreement. |
| – | `key_reasoning`, `holding` and `conditions` text are **never compared** | Wording legitimately differs between models. The holding and reasoning stored are the leader's. |

**Normalisation** (`_normalize_ruling`), applied identically by everyone, makes these checks crisp:

- It canonicalises verdict synonyms.
- It derives `compatible` from the verdict.
- It makes approval with conditions `approved_with_conditions`, and approval without conditions `approved`.
- It drops conditions on rejections.
- It keeps only shown precedent ids, and folds departures into the relevant set.
- It forces `novel` when nothing is cited.
- It scales a 0–1 confidence and clamps it to 0–100.

**Why not `prompt_comparative`?** That puts a second subjective LLM in charge of deciding whether two rulings match. Here the decision fields are already enumerable after normalisation, so deterministic rules give a sharper and auditable vote. LLM subjectivity is confined to the one place it belongs: interpreting the policy. **Why not `strict_eq`?** Two honest models will never produce byte-identical reasoning.

**Borderline cases fail on purpose.** If honest validators split on approve versus reject, consensus fails and GenLayer rotates the leader or the transaction ends undetermined. That is better than committing a coin-flip ruling that would then bind every later case.

**Leader errors.** If the leader raised (for example, the LLM returned non-JSON), validators agree only if their own run also raises a `UserError`, so the transaction reverts cleanly with no state change.

## Edge cases handled

| Case | Handling |
|---|---|
| No precedents, or none relevant | Prompt says "first impression". Ruling is forced to `novel` with no citations. |
| LLM cites a non-existent or unshown precedent | Dropped by `_id_list`. A leader that keeps it fails rule 0. |
| Conflicting precedents | The model must list any it departs from (`departs_from_precedent_ids`). Departure caps consistency at `medium`, and validators must agree a departure happened. |
| Evidence fetch failure | Recorded per URL with an error, and the prompt shows `UNAVAILABLE ... do not guess`. Validators must see the same availability. |
| Thin evidence | `insufficient_evidence` changes no law. The proposer can `add_evidence` and retry (max 3 attempts, max 4 URLs). |
| Malformed or non-JSON LLM output | `_parse_json` extracts the first `{...}`, tolerating code fences. Unknown verdict values raise `UserError`, so the transaction reverts and nothing is stored. |
| Float or string confidence | Parsed in the contract (`response_format="text"`), so floats never cross calldata. `0.9` becomes 90 and junk becomes 0. |
| Low-confidence ruling | Recorded on the case as `ruled_non_binding`. It doesn't become precedent and can't overturn one. |
| Prompt injection in proposal or evidence | Case text is fenced as untrusted data. Validators run their own models, so one hijacked model can't decide alone. |
| Policy amendment | Admin-only proposal, judged against `core_principles` and settled precedent. Only a plain `approved` adopts it, and the version increments. Pending cases are judged under the version current at `interpret()` time, recorded as `judged_policy_version`. |
| Appeal spam | At most 3 appeals per precedent. Superseded precedents can't be appealed. |
| Emergency | `set_paused(True)` blocks new cases and interpretation. Reads still work. |
| Unbounded growth | Retrieval is bounded (24 recent plus 48 per tag). View lists are capped at 50. |

## Using it from a frontend

- `get_policy()`: text, version, core principles, counts.
- `find_relevant_precedents(tags, text)`: preview the exact case law a new proposal will face.
- `submit_proposal(...)`, then `interpret(id)`, then read the returned ruling or `get_proposal(id)["ruling"]`.
- `get_recent_precedents(limit, in_force_only=True)`: the current body of law.
- `get_precedent(id)`: full ruling, including `in_force`, `superseded_by`, `affirmations`, cited ids and evidence status.

## Using it from another contract

A treasury, DAO executor or agent-permission contract can gate an action on a ruling:

```python
interp = gl.get_contract_at(Address(INTERPRETER))
v = interp.view().get_verdict(proposal_id)
# {"status": "ruled", "verdict": "approved_with_conditions", "compatible": True,
#  "conditions": [...], "precedent_id": 7, "outcome": "precedent_set"}
if v["status"] != "ruled" or not v["compatible"]:
    raise gl.vm.UserError("Action not approved under policy")
```

Cross-contract calls happen in deterministic code, never inside a non-det block.

## Limits

| Constant | Value |
|---|---|
| Policy text | 8000 chars |
| Core principles | 2000 chars |
| Title | 160 chars |
| Description | 4000 chars |
| Tags | 6 |
| Evidence URLs per case | 4 (5000 fetched chars each) |
| Candidate precedents per case | 8 |
| Attempts per case | 3 |
| Appeals per precedent | 3 |
| Confidence tolerance | ±20 |
| Citation overlap | Jaccard 0.5 |
| Default binding confidence | 60 (set at deploy) |
