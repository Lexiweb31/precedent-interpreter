# Precedent-Based Policy Interpreter

A GenLayer Intelligent Contract that interprets a natural-language policy the way courts interpret law: every ruling is reached by validator consensus, stored as a precedent, and weighed by later cases. Rulings can be appealed and superseded, and amendments to the policy must themselves pass judgment.

- Contract: [contracts/precedent_interpreter.py](contracts/precedent_interpreter.py)
- Design notes (state, Equivalence Principle, edge cases, integration): [docs/precedent-interpreter.md](docs/precedent-interpreter.md)

## Deploy

Constructor: `(policy_title, policy_text, core_principles="", min_precedent_confidence=60)`

Bradbury's deploy gas cap covers source **and** constructor args. The source is kept at 19.3 KB or less and ASCII-only (enforced by `tests/direct/test_contract_size.py`), leaving about 1 KB for the opening policy. Load longer policies with `extend_policy(text)` before the first case. `python scripts/deploy_bradbury.py --demo` deploys and runs a demo; it reads `DEPLOYER_PRIVATE_KEY` from the environment or `.env`.

## Test

```bash
pip install -r requirements.txt
# Direct mode runs in memory with mocked LLM/web. gltest still reads
# gltest.config.yaml, so any dummy key works:
DEPLOYER_PRIVATE_KEY=0x$(printf '1%.0s' {1..64}) pytest tests/direct -v
genvm-lint check contracts/precedent_interpreter.py
```
