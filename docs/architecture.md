# Passive Shopper — Architecture

## The Problem

You know *roughly* what you want. You don't know the exact model.
Traditional search: you type things, get overwhelmed, give up or buy the wrong thing.

The passive shopper inverts this: **you answer questions once, then go live your life.**
The agent handles the research, comparison, monitoring, and only interrupts when it's worth your attention.

---

## The Mental Model

```
GOAL (vague)
  "I want a telescope"
       ↓
CRITERIA MODEL (structured)
  use_case:     visual only        [must_have, weight=10]
  objects:      planets/moon       [must_have, weight=9]
  budget_cap:   $300               [must_have, weight=10]
  aperture_min: 130mm              [want,      weight=8]
  portability:  balcony/home       [want,      weight=7]
  mount_pref:   equatorial/dob     [want,      weight=6]
       ↓
CANDIDATE POOL (fetched, scored)
  Celestron AstroMaster 130EQ   → $229  score: 8.4/10  ✅ ALERT
  Orion SkyQuest XT6 Dobsonian  → $299  score: 7.9/10  ✅ ALERT  
  Sky-Watcher 8" Dob            → $399  score: 0.0/10  ❌ deal-breaker (over budget)
  Celestron NexStar 130SLT GoTo → $499  score: 0.0/10  ❌ deal-breaker (over budget)
       ↓
MONITORING (passive, background)
  - check every N hours
  - alert on: new listing, price drop, crossing threshold
  - user only sees: "Found a great match — $229, score 8.4/10. Buy now?"
```

---

## Components

### CriteriaModel
- Detects product category from natural language goal
- Owns the question tree for each category (weighted, typed)
- Returns unanswered questions in priority order (must_have first)
- Pre-fills criteria from goal string (budget, experience level, etc.)
- **Extension point**: add new category question trees without touching scorer

### CandidateScorer
- Scores a candidate against all answered criteria
- must_have + score=0 → immediate deal-breaker (returns 0.0)
- want + nice_to_have → weighted average
- Returns (float score 0–10, breakdown dict)
- **Extension point**: custom score functions per criterion (score_fn field)

### ListingMonitor
- Builds targeted search queries from answered criteria
- Sources: Brave Search API (live), mock mode (testing)
- Planned: Amazon, eBay, Reddit, CamelCamelCamel
- Returns raw listing dicts; scorer handles ranking

### AlertEngine
- Evaluates candidates against session.alert_threshold (default 7.5)
- Returns sorted alert list with score, price, URL, reason
- User sees only alerts — not the full candidate pool

### PassiveShopper (orchestrator)
- Wraps all components
- Persists state to SQL via SQLMemoryConnector (category=shopping_session)
- start_session → get_next_questions → answer_questions → get_candidates → get_alerts
- start_monitoring queues a recurring task to queue_daemon

---

## Data Model (SQL)

Stored as structured JSON in `memory.Memories` (category='shopping_session') initially.
Planned dedicated tables once schema is validated:

```sql
memory.ShoppingSessions     -- id, goal, category, status, alert_threshold, created_at
memory.ShoppingCriteria     -- id, session_id, name, ctype, weight, value, answered_at
memory.ShoppingCandidates   -- id, session_id, name, source, url, price, specs_json, score, checked_at
memory.ShoppingAlerts       -- id, session_id, candidate_id, score, reason, notified_at, dismissed
```

---

## The Weights Philosophy

Every criterion has:
- `ctype`: `must_have` | `want` | `nice_to_have`
- `weight`: 0–10 (how much it matters within its tier)

Score = Σ(weight × score_0_1) / Σ(weights) × 10

A must_have with score=0 short-circuits to 0 (deal-breaker).
The user never has to think about weights — they answer questions, weights are preset per category.
Advanced users can override.

---

## Monitoring Flow

```
queue_daemon receives task: {agent: 'passive_shopper', task_type: 'check_session', session_id: N}
       ↓
passive_shopper agent runs get_candidates()
       ↓
AlertEngine.evaluate()
       ↓
if alerts → queue notification task → user gets pinged
       ↓
re-queue check_session for N hours later (adaptive: shorter interval if price is dropping)
```

---

## Category Roadmap

Phase 1 (implemented):
- telescope, laptop (question trees done)
- camera, headphones, keyboard, monitor, gpu (skeletons)
- generic (fallback, budget + brand + condition)

Phase 2:
- car (make/model/year/mileage/trim)
- house (location/sqft/beds/price/commute)
- software/SaaS (features/pricing/integrations)

---

## Future: Learning

After a user buys (or passes), the agent updates criterion weights:
- "Bought the $229 one even though aperture was only 130mm" → aperture weight was too high for this user
- Feed back into per-user weight profiles over time
- Eventually: "Based on your past 3 purchases, here's what you actually care about"

---

## Integration Points

- **Oblio heartbeat**: surface active sessions with new matches
- **Jira**: each shopping session becomes a FALOO (or KAN) task
- **Discord/Telegram**: alerts delivered as rich messages with buy links
- **CamelCamelCamel**: price history charts for Amazon products
- **SQL memory**: full history of what was considered and why
