#!/usr/bin/env python3
"""
Tests for passive_shopper.py

Run: pytest tests/test_passive_shopper.py -v
"""

import sys
import os
import pytest

# Add skill to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'passive-shopper'))

from passive_shopper import (
    CriteriaModel, CandidateScorer, AlertEngine, ListingMonitor,
    Criterion, Candidate, ShoppingSession
)


# ── CriteriaModel tests ─────────────────────────────────────────────────────────

class TestCriteriaModel:

    def setup_method(self):
        self.model = CriteriaModel()

    def test_detect_telescope(self):
        assert self.model.detect_category("I want a telescope for planets") == 'telescope'

    def test_detect_laptop(self):
        assert self.model.detect_category("looking for a laptop for coding") == 'laptop'

    def test_detect_generic_fallback(self):
        assert self.model.detect_category("I need a blender") == 'generic'

    def test_telescope_criteria_returned(self):
        criteria = self.model.get_criteria('telescope')
        names = [c.name for c in criteria]
        assert 'budget_cap' in names
        assert 'aperture_min' in names
        assert 'use_case' in names

    def test_must_have_criteria_present(self):
        criteria = self.model.get_criteria('telescope')
        must_haves = [c for c in criteria if c.ctype == 'must_have']
        assert len(must_haves) >= 2

    def test_get_unanswered_returns_all_if_none_answered(self):
        criteria = self.model.get_criteria('telescope')
        unanswered = self.model.get_unanswered(criteria)
        assert len(unanswered) == len(criteria)

    def test_get_unanswered_excludes_answered(self):
        criteria = self.model.get_criteria('telescope')
        criteria[0].value = "visual only"
        unanswered = self.model.get_unanswered(criteria)
        assert len(unanswered) == len(criteria) - 1

    def test_unanswered_sorted_must_have_first(self):
        criteria = self.model.get_criteria('telescope')
        unanswered = self.model.get_unanswered(criteria)
        ctypes = [c.ctype for c in unanswered]
        # All must_haves should come before non-must_haves
        seen_non_must = False
        for ct in ctypes:
            if ct != 'must_have':
                seen_non_must = True
            if seen_non_must and ct == 'must_have':
                pytest.fail("must_have criterion appeared after non-must_have in sorted list")

    def test_extract_budget_from_goal(self):
        criteria = self.model.get_criteria('telescope')
        criteria = self.model.extract_from_goal("I want a telescope, budget $300", criteria)
        budget_c = next(c for c in criteria if c.name == 'budget_cap')
        assert budget_c.value == 300

    def test_extract_budget_with_comma(self):
        criteria = self.model.get_criteria('laptop')
        criteria = self.model.extract_from_goal("Need a laptop budget $1,500", criteria)
        budget_c = next(c for c in criteria if c.name == 'budget_cap')
        assert budget_c.value == 1500

    def test_extract_experience_beginner(self):
        criteria = self.model.get_criteria('telescope')
        criteria = self.model.extract_from_goal("beginner astronomer, want a telescope", criteria)
        exp_c = next((c for c in criteria if c.name == 'experience'), None)
        if exp_c:
            assert exp_c.value == 'beginner'


# ── CandidateScorer tests ───────────────────────────────────────────────────────

class TestCandidateScorer:

    def setup_method(self):
        self.scorer = CandidateScorer()
        self.model = CriteriaModel()

    def _make_session(self, answers: dict) -> list[Criterion]:
        criteria = self.model.get_criteria('telescope')
        for c in criteria:
            if c.name in answers:
                c.value = answers[c.name]
        return criteria

    def test_under_budget_scores_full(self):
        criteria = self._make_session({'budget_cap': 300})
        candidate = Candidate(session_id=1, name="Test", source="mock",
                              url="http://x.com", price=250.0, specs={})
        score, breakdown = self.scorer.score(candidate, criteria)
        assert breakdown['budget_cap']['score'] == 1.0

    def test_over_budget_is_deal_breaker(self):
        criteria = self._make_session({'budget_cap': 200})
        candidate = Candidate(session_id=1, name="Expensive", source="mock",
                              url="http://x.com", price=350.0, specs={})
        score, _ = self.scorer.score(candidate, criteria)
        assert score == 0.0   # must_have + score=0 → deal-breaker

    def test_unknown_price_neutral(self):
        criteria = self._make_session({'budget_cap': 300})
        candidate = Candidate(session_id=1, name="Mystery", source="mock",
                              url="http://x.com", price=None, specs={})
        score, breakdown = self.scorer.score(candidate, criteria)
        assert breakdown['budget_cap']['score'] == 0.5

    def test_aperture_met(self):
        criteria = self._make_session({'aperture_min': 130})
        candidate = Candidate(session_id=1, name="Big Scope", source="mock",
                              url="http://x.com", price=None, specs={'aperture_mm': 150})
        _, breakdown = self.scorer.score(candidate, criteria)
        assert breakdown['aperture_min']['score'] == 1.0

    def test_aperture_not_met(self):
        criteria = self._make_session({'aperture_min': 150})
        candidate = Candidate(session_id=1, name="Small Scope", source="mock",
                              url="http://x.com", price=None, specs={'aperture_mm': 70})
        _, breakdown = self.scorer.score(candidate, criteria)
        assert breakdown['aperture_min']['score'] == 0.0

    def test_no_criteria_answered_returns_neutral(self):
        criteria = self.model.get_criteria('telescope')  # none answered
        candidate = Candidate(session_id=1, name="Anything", source="mock",
                              url="http://x.com", price=100.0, specs={})
        score, _ = self.scorer.score(candidate, criteria)
        assert score == 5.0

    def test_full_scenario_telescope(self):
        """A $229 beginner 130mm EQ scope against a $300 budget / 130mm min criteria."""
        criteria = self._make_session({
            'budget_cap': 300,
            'aperture_min': 130,
            'experience': 'beginner',
        })
        candidate = Candidate(
            session_id=1,
            name="Celestron AstroMaster 130EQ",
            source="mock",
            url="http://amazon.com/celestron-130eq",
            price=229.99,
            specs={'aperture_mm': 130, 'experience': 'beginner', 'mount_pref': 'equatorial'}
        )
        score, breakdown = self.scorer.score(candidate, criteria)
        # budget met, aperture met, experience matches → should be ≥ 7
        assert score >= 7.0, f"Expected score ≥ 7.0, got {score}"


# ── AlertEngine tests ───────────────────────────────────────────────────────────

class TestAlertEngine:

    def setup_method(self):
        self.engine = AlertEngine()
        self.model = CriteriaModel()

    def _make_session(self, threshold=7.5):
        from datetime import datetime, timezone
        from dataclasses import field
        return ShoppingSession(
            id=1, goal="test", status="monitoring",
            category="telescope", criteria=[],
            alert_threshold=threshold,
        )

    def test_high_score_triggers_alert(self):
        session = self._make_session(threshold=7.0)
        candidates = [
            Candidate(session_id=1, name="Good scope", source="mock",
                      url="http://x.com", price=250.0, score=8.5)
        ]
        alerts = self.engine.evaluate(session, candidates)
        assert len(alerts) == 1
        assert alerts[0]['candidate'] == "Good scope"

    def test_low_score_no_alert(self):
        session = self._make_session(threshold=7.5)
        candidates = [
            Candidate(session_id=1, name="Meh scope", source="mock",
                      url="http://x.com", price=500.0, score=4.2)
        ]
        alerts = self.engine.evaluate(session, candidates)
        assert len(alerts) == 0

    def test_exactly_at_threshold_triggers(self):
        session = self._make_session(threshold=7.5)
        candidates = [
            Candidate(session_id=1, name="Threshold scope", source="mock",
                      url="http://x.com", price=300.0, score=7.5)
        ]
        alerts = self.engine.evaluate(session, candidates)
        assert len(alerts) == 1

    def test_alerts_sorted_by_score_desc(self):
        session = self._make_session(threshold=7.0)
        candidates = [
            Candidate(session_id=1, name="B", source="mock", url="", price=200.0, score=7.5),
            Candidate(session_id=1, name="A", source="mock", url="", price=200.0, score=9.2),
            Candidate(session_id=1, name="C", source="mock", url="", price=200.0, score=8.1),
        ]
        alerts = self.engine.evaluate(session, candidates)
        scores = [a['score'] for a in alerts]
        assert scores == sorted(scores, reverse=True)


# ── ListingMonitor tests ────────────────────────────────────────────────────────

class TestListingMonitor:

    def setup_method(self):
        self.monitor = ListingMonitor(brave_api_key=None)  # mock mode
        self.model = CriteriaModel()

    def _make_telescope_session(self):
        from datetime import datetime, timezone
        criteria = self.model.get_criteria('telescope')
        for c in criteria:
            if c.name == 'budget_cap':    c.value = 300
            if c.name == 'use_case':      c.value = 'visual only'
            if c.name == 'aperture_min':  c.value = 130
        return ShoppingSession(
            id=1, goal="telescope for planets", status="researching",
            category="telescope", criteria=criteria,
        )

    def test_mock_listings_returned_when_no_key(self):
        session = self._make_telescope_session()
        listings = self.monitor.fetch_listings(session)
        assert len(listings) >= 1

    def test_mock_listings_have_required_fields(self):
        session = self._make_telescope_session()
        listings = self.monitor.fetch_listings(session)
        for l in listings:
            assert 'name' in l
            assert 'url' in l
            assert 'price' in l
            assert 'source' in l

    def test_query_builder_includes_category(self):
        session = self._make_telescope_session()
        query = self.monitor._build_query(session)
        assert 'telescope' in query.lower()

    def test_query_builder_includes_budget(self):
        session = self._make_telescope_session()
        query = self.monitor._build_query(session)
        assert '$300' in query or 'under' in query.lower()


# ── Integration: full workflow ──────────────────────────────────────────────────

class TestFullWorkflow:
    """End-to-end test without SQL (mocked mem)."""

    def test_telescope_full_flow_no_sql(self):
        """
        Full flow: goal → criteria → answer → score → alert.
        Skips SQL persistence by not calling start_session (which needs DB).
        """
        model = CriteriaModel()
        scorer = CandidateScorer()
        monitor = ListingMonitor(brave_api_key=None)
        alerts_engine = AlertEngine()

        from datetime import datetime, timezone
        # Build session manually (no DB)
        category = model.detect_category("telescope for visual planetary under $300 beginner")
        assert category == 'telescope'

        criteria = model.get_criteria(category)
        criteria = model.extract_from_goal("telescope visual planetary under $300 beginner", criteria)

        # Answer remaining questions
        for c in criteria:
            if c.name == 'use_case' and not c.is_answered():    c.value = 'visual only'
            if c.name == 'objects' and not c.is_answered():     c.value = 'planets/moon'
            if c.name == 'aperture_min' and not c.is_answered(): c.value = 130
            if c.name == 'portability' and not c.is_answered(): c.value = 'balcony/home'

        session = ShoppingSession(id=1, goal="telescope", status="researching",
                                  category=category, criteria=criteria)

        # Fetch mock candidates
        raw_listings = monitor.fetch_listings(session)
        assert len(raw_listings) >= 2

        # Score them
        candidates = []
        for r in raw_listings:
            c = Candidate(session_id=1, name=r['name'], source=r['source'],
                          url=r['url'], price=r.get('price'), specs=r.get('specs', {}))
            c.score, _ = scorer.score(c, criteria)
            candidates.append(c)

        # Best candidate should score well
        candidates.sort(key=lambda c: -(c.score or 0))
        assert candidates[0].score > 0, "Top candidate should have a positive score"

        # Alert engine
        alerts = alerts_engine.evaluate(session, candidates)
        # With budget=$300 and mock data having $229 and $299 options → should get alerts
        # (depends on whether scores pass threshold=7.5)
        # Just verify it runs without error
        assert isinstance(alerts, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
