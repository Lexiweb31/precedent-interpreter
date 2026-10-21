"""
Direct-mode tests for precedent_interpreter.py.
In-memory, with mocked web/LLM calls; no GenLayer node needed.

Run with:
    pytest tests/direct -v
"""
import json
from pathlib import Path

import pytest
from gltest.direct.loader import create_address

_CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "precedent_interpreter.py"

POLICY = (
    "Community grants fund open-source public goods. Grants must not fund closed-source work, "
    "marketing campaigns, or token speculation. Recipients publish quarterly progress reports."
)
CORE = "Funds serve public goods only."


def _addr(name):
    from gltest.direct.sdk_loader import setup_sdk_paths
    setup_sdk_paths()
    return create_address(name)


def _llm(verdict="approved", relevant=(), departs=(), consistency=None, conditions=(), confidence=85, **extra):
    return json.dumps({
        "verdict": verdict,
        "compatible": verdict.startswith("approved"),
        "relevant_precedent_ids": list(relevant),
        "departs_from_precedent_ids": list(departs),
        "consistency_with_precedents": consistency or ("high" if relevant else "novel"),
        "conditions": list(conditions),
        "key_reasoning": ["The work is open source.", "It benefits the ecosystem."],
        "holding": f"Rule for {verdict}.",
        "confidence": confidence,
        **extra,
    })


def _deploy(direct_deploy, min_conf=60):
    return direct_deploy(str(_CONTRACT), "Grants Charter", POLICY, CORE, min_conf)


def _rule(contract, direct_vm, llm, title="Fund an OSS indexer", desc="Build an open-source block indexer.",
          tags=("tooling",), urls=(), web=None):
    direct_vm.clear_mocks()
    direct_vm.mock_llm(".*", llm)
    if web:
        direct_vm.mock_web(*web)
    pid = contract.submit_proposal(title, desc, list(tags), list(urls))
    return contract.interpret(pid)


class TestSetupAndAccess:
    def test_policy_stored(self, direct_deploy):
        c = _deploy(direct_deploy)
        pol = c.get_policy()
        assert pol["version"] == 1 and pol["core_principles"] == CORE and pol["paused"] is False

    def test_empty_policy_reverts(self, direct_deploy):
        with pytest.raises(Exception):
            direct_deploy(str(_CONTRACT), "T", "   ", "", 60)

    def test_only_admin_amends_and_pauses(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        admin = direct_vm.sender
        direct_vm.sender = _addr("stranger")
        with pytest.raises(Exception):
            c.propose_amendment("x", "y", "new text", [])
        with pytest.raises(Exception):
            c.set_paused(True)
        direct_vm.sender = admin
        c.set_paused(True)
        with pytest.raises(Exception):
            c.submit_proposal("t", "d", [], [])

    def test_input_validation(self, direct_deploy):
        c = _deploy(direct_deploy)
        with pytest.raises(Exception):
            c.submit_proposal("t", "d", [], ["ftp://x"])
        with pytest.raises(Exception):
            c.submit_proposal("t", "d", list("abcdefg"), [])
        with pytest.raises(Exception):
            c.submit_proposal("t", "", [], [])


class TestInterpretation:
    def test_first_case_sets_novel_precedent(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        r = _rule(c, direct_vm, _llm("approved", relevant=[9]))  # #9 doesn't exist: dropped
        assert r["outcome"] == "precedent_set" and r["precedent_id"] == 1
        assert r["relevant_precedent_ids"] == [] and r["consistency_with_precedents"] == "novel"
        p = c.get_precedent(1)
        assert p["verdict"] == "approved" and p["in_force"] and p["tags"] == ["tooling"]
        assert c.get_verdict(1)["compatible"] is True

    def test_second_case_sees_and_cites_first(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("approved"))
        found = c.find_relevant_precedents(["tooling"], "another indexer")
        assert [p["id"] for p in found] == [1]
        r = _rule(c, direct_vm, _llm("approved", relevant=[1]), title="Fund a second indexer")
        assert r["relevant_precedent_ids"] == [1] and r["consistency_with_precedents"] == "high"
        assert c.get_precedent(2)["relevant_precedent_ids"] == [1]

    def test_unrelated_precedent_not_shown(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("approved"))
        assert c.find_relevant_precedents(["events"], "conference catering budget") == []

    def test_conditions_normalise_verdict(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        r = _rule(c, direct_vm, _llm("approved", conditions=["Publish under MIT"]))
        assert r["verdict"] == "approved_with_conditions" and r["conditions"] == ["Publish under MIT"]
        r = _rule(c, direct_vm, _llm("approved_with_conditions"))
        assert r["verdict"] == "approved"
        r = _rule(c, direct_vm, _llm("rejected", conditions=["ignored"]))
        assert r["conditions"] == [] and r["compatible"] is False

    def test_synonyms_and_bad_confidence(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        r = _rule(c, direct_vm, _llm("Reject", confidence="0.9"))
        assert r["verdict"] == "rejected" and r["confidence"] == 90
        r = _rule(c, direct_vm, _llm("approve", confidence="lots"))
        assert r["verdict"] == "approved" and r["confidence"] == 0 and r["outcome"] == "ruled_non_binding"

    def test_malformed_llm_reverts(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        with pytest.raises(Exception):
            _rule(c, direct_vm, "I think it is fine.")
        with pytest.raises(Exception):
            _rule(c, direct_vm, _llm("maybe"))

    def test_insufficient_then_retry_with_evidence(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        r = _rule(c, direct_vm, _llm("insufficient_evidence", confidence=20))
        assert r["outcome"] == "insufficient_evidence" and r["precedent_id"] == 0
        assert c.get_proposal(1)["status"] == "insufficient_evidence"
        assert c.get_policy()["precedents"] == 0
        c.add_evidence(1, "https://repo.example/indexer")
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("approved"))
        direct_vm.mock_web(r"https://repo\.example/.*", {"method": "GET", "status": 200, "body": "MIT licensed"})
        r = c.interpret(1)
        assert r["outcome"] == "precedent_set" and r["sources"][0]["ok"] is True

    def test_failed_fetch_is_recorded(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        r = _rule(c, direct_vm, _llm("insufficient_evidence"), urls=["https://dead.example/x"],
                  web=(".*", {"method": "GET", "status": 404, "body": ""}))
        assert r["sources"][0]["ok"] is False and r["sources"][0]["error"]

    def test_ruled_proposal_cannot_rerun(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("approved"))
        with pytest.raises(Exception):
            c.interpret(1)

    def test_withdraw_only_by_proposer(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        c.submit_proposal("t", "d", [], [])
        me = direct_vm.sender
        direct_vm.sender = _addr("stranger")
        with pytest.raises(Exception):
            c.withdraw(1)
        direct_vm.sender = me
        c.withdraw(1)
        assert c.get_proposal(1)["status"] == "withdrawn"


class TestAppealsAndAmendments:
    def test_appeal_affirms(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("rejected"))
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("rejected"))
        aid = c.appeal(1, "The indexer is actually open source.", [])
        r = c.interpret(aid)
        assert r["outcome"] == "affirmed" and r["precedent_id"] == 0
        p = c.get_precedent(1)
        assert p["affirmations"] == 1 and p["in_force"]

    def test_appeal_overturns_and_supersedes(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("rejected"))
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("approved", confidence=90))
        r = c.interpret(c.appeal(1, "New evidence: MIT license.", []))
        assert r["outcome"] == "overturned" and r["precedent_id"] == 2
        assert c.get_precedent(1)["superseded_by"] == 2
        assert [p["id"] for p in c.get_recent_precedents(10, True)] == [2]
        assert [p["id"] for p in c.find_relevant_precedents(["tooling"], "indexer")] == [2]
        with pytest.raises(Exception):
            c.appeal(1, "again", [])

    def test_low_confidence_cannot_overturn(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        _rule(c, direct_vm, _llm("rejected"))
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("approved", confidence=40))
        r = c.interpret(c.appeal(1, "Please reconsider.", []))
        assert r["outcome"] == "not_overturned_low_confidence"
        assert c.get_precedent(1)["in_force"]

    def test_amendment_adopted_only_when_approved(self, direct_deploy, direct_vm):
        c = _deploy(direct_deploy)
        new_text = POLICY + " Security audits of public infrastructure are eligible."
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("rejected"))
        r = c.interpret(c.propose_amendment("Allow audits", "Audits are public goods.", new_text, []))
        assert r["outcome"] == "amendment_rejected" and c.get_policy()["version"] == 1
        direct_vm.clear_mocks()
        direct_vm.mock_llm(".*", _llm("approved"))
        r = c.interpret(c.propose_amendment("Allow audits", "Audits are public goods.", new_text, []))
        assert r["outcome"] == "amendment_adopted" and r["judged_policy_version"] == 1
        pol = c.get_policy()
        assert pol["version"] == 2 and pol["text"] == new_text
        _rule(c, direct_vm, _llm("approved"))
        assert c.get_precedent(3)["policy_version"] == 2


class TestEquivalence:
    """Re-run the validator against the leader's committed result with a different LLM answer."""

    def _leader(self, direct_deploy, direct_vm, llm, cite_first=False):
        c = _deploy(direct_deploy)
        if cite_first:
            _rule(c, direct_vm, _llm("approved"))
            _rule(c, direct_vm, _llm("approved"), title="Fund an OSS explorer")
        _rule(c, direct_vm, llm, title="Fund an OSS indexer v2")
        direct_vm.clear_mocks()
        return c

    def test_same_decision_different_prose_agrees(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", confidence=80))
        direct_vm.mock_llm(".*", _llm("approved", confidence=70, key_reasoning=["Other words"], holding="Else."))
        assert direct_vm.run_validator() is True

    def test_different_verdict_disagrees(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved"))
        direct_vm.mock_llm(".*", _llm("rejected"))
        assert direct_vm.run_validator() is False

    def test_conditions_vs_plain_approval_disagrees(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved"))
        direct_vm.mock_llm(".*", _llm("approved", conditions=["Quarterly reports"]))
        assert direct_vm.run_validator() is False

    def test_confidence_tolerance(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", confidence=90))
        direct_vm.mock_llm(".*", _llm("approved", confidence=60))
        assert direct_vm.run_validator() is False

    def test_overlapping_citations_agree(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", relevant=[1, 2]), cite_first=True)
        direct_vm.mock_llm(".*", _llm("approved", relevant=[1], consistency="medium"))
        assert direct_vm.run_validator() is True

    def test_disjoint_citations_disagree(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", relevant=[1]), cite_first=True)
        direct_vm.mock_llm(".*", _llm("approved", relevant=[2]))
        assert direct_vm.run_validator() is False

    def test_novel_vs_cited_disagrees(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", relevant=[1]), cite_first=True)
        direct_vm.mock_llm(".*", _llm("approved"))
        assert direct_vm.run_validator() is False

    def test_departure_must_match(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved", relevant=[1, 2], departs=[1], consistency="low"),
                     cite_first=True)
        direct_vm.mock_llm(".*", _llm("approved", relevant=[1, 2], consistency="medium"))
        assert direct_vm.run_validator() is False

    def test_both_insufficient_agree(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("insufficient_evidence", confidence=10))
        direct_vm.mock_llm(".*", _llm("insufficient_evidence", confidence=80))
        assert direct_vm.run_validator() is True

    def test_leader_error_validator_succeeds_disagrees(self, direct_deploy, direct_vm):
        self._leader(direct_deploy, direct_vm, _llm("approved"))
        direct_vm.mock_llm(".*", _llm("approved"))
        assert direct_vm.run_validator(leader_error=Exception("bad json")) is False


def test_equivalence_rejects_doctored_leader(direct_deploy):
    # Pure-function check: a leader citing an id it was never shown, or
    # returning an unnormalised ruling, is rejected before any comparison.
    import sys
    _deploy(direct_deploy)
    mod = next(m for m in list(sys.modules.values()) if hasattr(m, "_rulings_equivalent"))
    mine = {"ruling": mod._normalize_ruling(_llm("approved", relevant=[1]), [1, 2]), "sources": []}
    assert mod._rulings_equivalent(json.loads(json.dumps(mine)), mine, [1, 2]) is True
    forged = json.loads(json.dumps(mine))
    forged["ruling"]["relevant_precedent_ids"] = [1, 7]
    assert mod._rulings_equivalent(forged, mine, [1, 2]) is False
    forged = json.loads(json.dumps(mine))
    forged["ruling"]["compatible"] = False
    assert mod._rulings_equivalent(forged, mine, [1, 2]) is False
    assert mod._rulings_equivalent({"ruling": mine["ruling"], "sources": [{"ok": True}]}, mine, [1, 2]) is False
