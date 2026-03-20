#!/usr/bin/env python3
"""
passive_shopper.py — Core passive shopping agent
=================================================
Manages shopping sessions: criteria modeling, candidate scoring,
passive monitoring, and deal alerts.

Architecture:
    PassiveShopper         ← main entry point
    ├── CriteriaModel      ← builds/updates the requirement model
    ├── CandidateScorer    ← scores options against criteria
    ├── ListingMonitor     ← fetches + caches fresh listings
    └── AlertEngine        ← evaluates threshold, queues notifications
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

log = logging.getLogger(__name__)


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class Criterion:
    """A single requirement dimension."""
    name: str
    label: str
    ctype: str          # 'must_have' | 'want' | 'nice_to_have'
    weight: float       # 0–10
    value: Optional[str | int | float | bool] = None   # answered value
    score_fn: Optional[str] = None  # name of scoring function key

    def is_answered(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShoppingSession:
    id: int
    goal: str
    status: str          # 'interviewing' | 'researching' | 'monitoring' | 'closed'
    category: str        # e.g. 'telescope', 'laptop', 'camera'
    criteria: list[Criterion] = field(default_factory=list)
    alert_threshold: float = 7.5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict = field(default_factory=dict)


@dataclass
class Candidate:
    session_id: int
    name: str
    source: str           # 'amazon' | 'ebay' | 'web' | 'reddit'
    url: str
    price: Optional[float]
    specs: dict = field(default_factory=dict)
    score: Optional[float] = None   # computed by CandidateScorer
    alerts: list[str] = field(default_factory=list)  # why it was flagged


# ── Criteria Model ─────────────────────────────────────────────────────────────

class CriteriaModel:
    """
    Knows the question tree for common product categories.
    Given a goal string, identifies the category and returns
    prioritized clarifying questions.
    """

    # Category detection keywords
    CATEGORIES = {
        'telescope':    ['telescope', 'scope', 'star', 'astronomy', 'planet', 'astrophoto'],
        'laptop':       ['laptop', 'notebook', 'macbook', 'thinkpad', 'ultrabook'],
        'camera':       ['camera', 'dslr', 'mirrorless', 'lens', 'photography'],
        'headphones':   ['headphones', 'earbuds', 'headset', 'audio', 'speakers'],
        'keyboard':     ['keyboard', 'mechanical', 'keycap', 'switch'],
        'monitor':      ['monitor', 'display', 'screen', 'ultrawide'],
        'gpu':          ['gpu', 'graphics card', 'video card', 'rtx', 'rx'],
        'generic':      [],  # fallback
    }

    # Question trees per category
    QUESTION_TREES: dict[str, list[dict]] = {
        'telescope': [
            {'name': 'use_case',     'label': 'Primary use?',
             'options': ['visual only', 'astrophotography', 'both'], 'weight': 10, 'ctype': 'must_have'},
            {'name': 'objects',      'label': 'Primary targets?',
             'options': ['planets/moon', 'deep sky', 'both/all sky'], 'weight': 9, 'ctype': 'must_have'},
            {'name': 'experience',   'label': 'Experience level?',
             'options': ['beginner', 'intermediate', 'advanced'], 'weight': 7, 'ctype': 'want'},
            {'name': 'budget_cap',   'label': 'Hard budget cap? ($)',
             'options': None, 'weight': 10, 'ctype': 'must_have', 'dtype': 'number'},
            {'name': 'portability',  'label': 'Portability needs?',
             'options': ['balcony/home', 'car transport', 'backpack'], 'weight': 8, 'ctype': 'want'},
            {'name': 'mount_pref',   'label': 'Mount preference?',
             'options': ['manual/alt-az', 'equatorial', 'goto/motorized', 'dobsonian', "don't care"],
             'weight': 6, 'ctype': 'want'},
            {'name': 'aperture_min', 'label': 'Minimum aperture (mm)?',
             'options': ['70', '90', '114', '130', '150', '200+'],
             'weight': 8, 'ctype': 'want', 'dtype': 'number'},
            {'name': 'location',     'label': 'Observing location?',
             'options': ['urban/suburban', 'rural/dark site', 'both'], 'weight': 5, 'ctype': 'nice_to_have'},
        ],
        'laptop': [
            {'name': 'primary_use',  'label': 'Primary use?',
             'options': ['dev/coding', 'creative/design', 'gaming', 'office/school', 'general'],
             'weight': 10, 'ctype': 'must_have'},
            {'name': 'os_pref',      'label': 'OS preference?',
             'options': ['Windows', 'macOS', 'Linux', "don't care"], 'weight': 9, 'ctype': 'want'},
            {'name': 'budget_cap',   'label': 'Budget cap ($)?',
             'options': None, 'weight': 10, 'ctype': 'must_have', 'dtype': 'number'},
            {'name': 'portability',  'label': 'Weight/size priority?',
             'options': ['max portability (<3lb)', 'balanced', 'power over portability'],
             'weight': 7, 'ctype': 'want'},
            {'name': 'ram_min',      'label': 'Minimum RAM (GB)?',
             'options': ['8', '16', '32', '64'], 'weight': 8, 'ctype': 'want', 'dtype': 'number'},
            {'name': 'storage_min',  'label': 'Minimum storage (GB)?',
             'options': ['256', '512', '1000', '2000'], 'weight': 6, 'ctype': 'want', 'dtype': 'number'},
        ],
        'generic': [
            {'name': 'budget_cap',   'label': 'Budget cap ($)?',
             'options': None, 'weight': 10, 'ctype': 'must_have', 'dtype': 'number'},
            {'name': 'brand_pref',   'label': 'Brand preferences or exclusions?',
             'options': None, 'weight': 5, 'ctype': 'nice_to_have', 'dtype': 'text'},
            {'name': 'condition',    'label': 'New only, or open to used/refurb?',
             'options': ['new only', 'open to refurb', 'used ok if deal is right'],
             'weight': 6, 'ctype': 'want'},
        ],
    }

    def detect_category(self, goal: str) -> str:
        goal_lower = goal.lower()
        for cat, keywords in self.CATEGORIES.items():
            if any(kw in goal_lower for kw in keywords):
                return cat
        return 'generic'

    def get_criteria(self, category: str) -> list[Criterion]:
        tree = self.QUESTION_TREES.get(category, self.QUESTION_TREES['generic'])
        return [
            Criterion(
                name=q['name'],
                label=q['label'],
                ctype=q['ctype'],
                weight=q['weight'],
                score_fn=q.get('score_fn'),
            )
            for q in tree
        ]

    def get_unanswered(self, criteria: list[Criterion]) -> list[Criterion]:
        """Return unanswered criteria sorted by priority (must_have first, then weight desc)."""
        unanswered = [c for c in criteria if not c.is_answered()]
        return sorted(unanswered, key=lambda c: (0 if c.ctype == 'must_have' else 1, -c.weight))

    def extract_from_goal(self, goal: str, criteria: list[Criterion]) -> list[Criterion]:
        """
        Pre-fill criteria from natural language goal string.
        E.g. "budget $300" → budget_cap=300
        """
        import re
        goal_lower = goal.lower()

        # Budget extraction
        budget_match = re.search(r'\$\s*(\d[\d,]*)', goal)
        if budget_match:
            budget_val = int(budget_match.group(1).replace(',', ''))
            for c in criteria:
                if c.name == 'budget_cap' and not c.is_answered():
                    c.value = budget_val
                    log.info(f"Pre-filled budget_cap={budget_val} from goal string")

        # Experience extraction
        for exp in ['beginner', 'intermediate', 'advanced']:
            if exp in goal_lower:
                for c in criteria:
                    if c.name == 'experience' and not c.is_answered():
                        c.value = exp

        return criteria


# ── Candidate Scorer ───────────────────────────────────────────────────────────

class CandidateScorer:
    """
    Scores a candidate product against a criteria model.
    Returns 0–10 score and a breakdown dict.
    """

    def score(self, candidate: Candidate, criteria: list[Criterion]) -> tuple[float, dict]:
        breakdown = {}
        total_weight = 0.0
        weighted_sum = 0.0

        for c in criteria:
            if not c.is_answered():
                continue

            score = self._score_criterion(c, candidate)
            breakdown[c.name] = {'score': score, 'weight': c.weight, 'ctype': c.ctype}

            if c.ctype == 'must_have' and score == 0:
                # Deal-breaker
                return 0.0, {**breakdown, '_deal_breaker': c.name}

            total_weight += c.weight
            weighted_sum += c.weight * score

        if total_weight == 0:
            return 5.0, breakdown   # no criteria answered → neutral score

        final = (weighted_sum / total_weight) * 10
        return round(final, 2), breakdown

    def _score_criterion(self, c: Criterion, candidate: Candidate) -> float:
        """
        Return 0–1 score for a single criterion against a candidate.
        Uses candidate.specs dict for lookup.
        """
        specs = candidate.specs

        if c.name == 'budget_cap':
            if candidate.price is None:
                return 0.5   # unknown price → neutral
            return 1.0 if candidate.price <= float(c.value) else 0.0

        if c.name == 'aperture_min':
            aperture = specs.get('aperture_mm')
            if aperture is None:
                return 0.5
            return 1.0 if float(aperture) >= float(c.value) else 0.0

        # Generic: if spec matches value → 1.0, present but different → 0.5, missing → 0.3
        spec_val = specs.get(c.name)
        if spec_val is None:
            return 0.3
        if str(spec_val).lower() == str(c.value).lower():
            return 1.0
        return 0.5


# ── Listing Monitor ─────────────────────────────────────────────────────────────

class ListingMonitor:
    """
    Fetches fresh listings from configured sources.
    Currently: web search via Brave API.
    Designed for extension: Amazon, eBay, Reddit.
    """

    def __init__(self, brave_api_key: Optional[str] = None):
        self.brave_key = brave_api_key

    def fetch_listings(self, session: ShoppingSession, limit: int = 10) -> list[dict]:
        """
        Generate search queries from session criteria and fetch results.
        Returns raw listing dicts (name, url, price_hint, source, specs).
        """
        query = self._build_query(session)
        log.info(f"Fetching listings for session {session.id}: {query!r}")

        results = []
        if self.brave_key:
            results = self._brave_search(query, limit)
        else:
            log.warning("No BRAVE_API_KEY — listing fetch skipped (mock mode)")
            results = self._mock_listings(session)

        return results

    def _build_query(self, session: ShoppingSession) -> str:
        """Build a targeted product search query from answered criteria."""
        parts = [session.category]
        for c in session.criteria:
            if not c.is_answered():
                continue
            if c.name == 'budget_cap':
                parts.append(f"under ${c.value}")
            elif c.name == 'aperture_min':
                parts.append(f"{c.value}mm aperture")
            elif c.name in ('use_case', 'objects', 'mount_pref'):
                parts.append(str(c.value))
        parts.append("buy review price")
        return " ".join(parts)

    def _brave_search(self, query: str, limit: int) -> list[dict]:
        """Call Brave Search API and parse results."""
        import os, requests
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {"Accept": "application/json", "X-Subscription-Token": self.brave_key}
        params = {"q": query, "count": limit, "freshness": "pm"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("web", {}).get("results", []):
                results.append({
                    "name": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "source": "brave_web",
                    "price": None,
                    "specs": {},
                })
            return results
        except Exception as e:
            log.error(f"Brave search failed: {e}")
            return []

    def _mock_listings(self, session: ShoppingSession) -> list[dict]:
        """Return mock listings for testing without API key."""
        if session.category == 'telescope':
            return [
                {"name": "Celestron AstroMaster 130EQ", "url": "https://example.com/130eq",
                 "source": "mock", "price": 229.99,
                 "specs": {"aperture_mm": 130, "mount_pref": "equatorial", "experience": "beginner"}},
                {"name": "Orion SkyQuest XT6 Dobsonian", "url": "https://example.com/xt6",
                 "source": "mock", "price": 299.00,
                 "specs": {"aperture_mm": 150, "mount_pref": "dobsonian", "experience": "beginner"}},
                {"name": "Sky-Watcher 8\" Dobsonian", "url": "https://example.com/sw8",
                 "source": "mock", "price": 399.00,
                 "specs": {"aperture_mm": 200, "mount_pref": "dobsonian", "experience": "intermediate"}},
                {"name": "Celestron NexStar 130SLT GoTo", "url": "https://example.com/130slt",
                 "source": "mock", "price": 499.00,
                 "specs": {"aperture_mm": 130, "mount_pref": "goto/motorized", "experience": "beginner"}},
            ]
        return [{"name": "Mock Product A", "url": "https://example.com/a",
                 "source": "mock", "price": 199.0, "specs": {}}]


# ── Alert Engine ────────────────────────────────────────────────────────────────

class AlertEngine:
    """
    Evaluates candidates against session threshold.
    Returns list of alert messages for candidates that should notify the user.
    """

    def evaluate(self, session: ShoppingSession, candidates: list[Candidate]) -> list[dict]:
        alerts = []
        for c in candidates:
            if c.score is None:
                continue
            if c.score >= session.alert_threshold:
                alerts.append({
                    "candidate": c.name,
                    "score": c.score,
                    "price": c.price,
                    "url": c.url,
                    "reason": f"Score {c.score:.1f}/10 ≥ threshold {session.alert_threshold}",
                })
        return sorted(alerts, key=lambda a: -a['score'])


# ── Main PassiveShopper ─────────────────────────────────────────────────────────

class PassiveShopper:
    """
    Orchestrates the full passive shopping workflow.
    Persists all state to SQL.
    """

    def __init__(self, backend: str = 'cloud', brave_api_key: Optional[str] = None):
        self.backend = backend
        self._mem = None
        self._model = CriteriaModel()
        self._scorer = CandidateScorer()
        self._monitor = ListingMonitor(brave_api_key=brave_api_key)
        self._alerts = AlertEngine()

    @property
    def mem(self):
        if self._mem is None:
            import sys, os
            ws = os.getenv('WORKSPACE', os.path.expanduser('~/.openclaw/workspace'))
            infra = os.path.join(ws, 'infrastructure')
            if infra not in sys.path:
                sys.path.insert(0, infra)
            from sql_memory_connector import SQLMemoryConnector
            self._mem = SQLMemoryConnector(self.backend)
        return self._mem

    def start_session(self, goal: str, context: dict | None = None) -> ShoppingSession:
        """Create a new shopping session and persist it."""
        context = context or {}
        category = self._model.detect_category(goal)
        criteria = self._model.get_criteria(category)
        criteria = self._model.extract_from_goal(goal, criteria)

        # Persist to SQL memory as a structured memory entry
        session_data = {
            "goal": goal,
            "category": category,
            "status": "interviewing",
            "criteria": [c.to_dict() for c in criteria],
            "alert_threshold": 7.5,
            "context": context,
        }
        self.mem.remember(
            category='shopping_session',
            key=f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            content=json.dumps(session_data),
            importance=6,
            tags='passive_shopper,active',
        )

        log.info(f"Started shopping session for '{goal}' (category={category})")
        return ShoppingSession(
            id=0,  # real ID assigned by DB
            goal=goal,
            status='interviewing',
            category=category,
            criteria=criteria,
            context=context,
        )

    def get_next_questions(self, session: ShoppingSession) -> list[Criterion]:
        """Return unanswered criteria in priority order."""
        return self._model.get_unanswered(session.criteria)

    def answer_questions(self, session: ShoppingSession, answers: dict) -> ShoppingSession:
        """Apply answers to session criteria."""
        for c in session.criteria:
            if c.name in answers:
                c.value = answers[c.name]
                log.info(f"Answered {c.name}={c.value!r}")
        return session

    def get_candidates(self, session: ShoppingSession) -> list[Candidate]:
        """Fetch, score, and rank candidates for the current session state."""
        raw = self._monitor.fetch_listings(session)
        candidates = []
        for r in raw:
            c = Candidate(
                session_id=session.id,
                name=r.get('name', 'Unknown'),
                source=r.get('source', 'web'),
                url=r.get('url', ''),
                price=r.get('price'),
                specs=r.get('specs', {}),
            )
            score, breakdown = self._scorer.score(c, session.criteria)
            c.score = score
            candidates.append(c)

        return sorted(candidates, key=lambda c: -(c.score or 0))

    def get_best_deal(self, session: ShoppingSession) -> Optional[Candidate]:
        """Return highest-scoring candidate, or None if none qualify."""
        candidates = self.get_candidates(session)
        if not candidates:
            return None
        best = candidates[0]
        return best if (best.score or 0) >= session.alert_threshold else None

    def get_alerts(self, session: ShoppingSession) -> list[dict]:
        """Run the alert engine and return any candidates crossing the threshold."""
        candidates = self.get_candidates(session)
        return self._alerts.evaluate(session, candidates)
