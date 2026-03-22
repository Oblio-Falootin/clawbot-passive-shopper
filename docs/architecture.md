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

## How Property Weighting Works

This is the core concept that makes passive shopping different from a search engine.

Every criterion has two numbers the user never has to think about:

| Field | Values | Meaning |
|-------|--------|---------|
| `ctype` | `must_have` \| `want` \| `nice_to_have` | tier of importance |
| `weight` | 1–10 | relative importance within tier |

**Score formula:**

```
Score = Σ(weight × criterion_score_0_to_1) / Σ(all weights) × 10
```

A `must_have` with a score of 0 **short-circuits to 0** immediately — deal-breaker,
product removed, no matter how good everything else is.

### Real Example — Beach Drone

The user says: *"cheap drone, fly at the beach, remote control, built-in camera."*
The agent maps this to:

```
budget_cap        must_have  w=10  → "cheap" → ask for hard cap
built_in_camera   must_have  w=10  → stated requirement
wind_resistance   must_have  w=9   → beach = coastal wind (inferred from context)
flight_time       want       w=8   → longer is better; 10 min is ok for casual use
gps_stabilization want       w=7   → hover-hold useful for beach photography
camera_resolution want       w=6   → 1080p acceptable, 4K better
folding/portable  nice       w=4   → beach bag friendly is a bonus
spare_parts_avail nice       w=3   → cheap drones are often disposable
```

Two products, same price:
- Drone A: great camera, no wind resistance, no GPS → must_have fails → **score 0.0**
- Drone B: decent camera, wind resistant, GPS hover → **score 7.8** → ALERT

The user only answered "cheap, beach, camera." The agent did the rest.

### How Weights Are Set

- Weights are **preset per category** based on what actually matters for that product type.
- Users never touch weights. They answer plain conversational questions.
- Context inference: "beach" → bumps `wind_resistance`; "astrophotography" → bumps `aperture_min`.
- **Advanced mode**: user says "I really care about battery life" → agent bumps `flight_time` weight up.
- **Learning mode** (future): if user buys the $229 scope despite low aperture score → aperture weight
  was too high for this user. Feeds back into per-user weight profiles over time.

---

## Product Parameter Education

When a user picks a category, the agent can optionally explain the key parameters
*before* asking questions. This surfaces domain knowledge the user may not have.

Examples:
- **Telescope**: "Aperture is king. A 130mm scope gathers 3× more light than a 70mm."
- **Drone**: "FAA requires registration for drones over 250g. Most 'cheap' beach drones are under."
- **Laptop**: "RAM cannot be upgraded on most modern laptops — get what you need now."

This is the `parameter_education` feature — queued as a future implementation item (FALOO-XX).
Goal: reduce clarifying question round-trips by giving users the vocabulary to answer confidently.

---

## Category Gap Analysis (from Live Test Sessions)

### Session 1 — Telescope (2026-03-22)
**Inquiry:** "I'd like a telescope for my back deck. I want it to be Bluetooth enabled.
And can take pictures with my phone or stream to the computer."

**What worked:** Category detected correctly. 8 criteria loaded. Scoring functional.

**Gaps found:**
- `bluetooth_enabled` — not in question tree → misses entire smart telescope category
- `phone_compatible` — not modeled
- `streaming_support` — not modeled
- **Missing subcategory:** `smart_telescope` (Celestron Origin, Unistellar eVscope, Vaonis Stellina)
  — price range $800–$4,000+; completely different feature set from optical scopes

**Tickets created:** FALOO-XX (see Jira FALOO project)

---

### Session 2 — Drone (2026-03-22)
**Inquiry:** "I'd like to buy a cheap drone that I can fly at the beach.
It is remote control and has a built-in camera."

**What worked:** Budget extraction ready. Scoring logic works.

**Gaps found:**
- `drone` classified as `camera` — needs its own top-level category
- No drone question tree exists — fell back to `generic` (only 3 questions)
- Missing drone-specific criteria:
  - `flight_time` (battery endurance, minutes)
  - `wind_resistance` (critical for coastal/beach use)
  - `camera_resolution` (1080p vs 4K)
  - `range` (meters)
  - `gps_stabilization` (hover-hold capability)
  - `faa_registration_required` (>250g triggers FAA reg — regulatory must_have)
  - `folding_design` (portability for beach bag)
  - `spare_parts_available` (cheap drones are often disposable)
- No mock listings for drone category
- Context inference not wired: "beach" should raise wind_resistance weight automatically

**Tickets created:** FALOO-XX (see Jira FALOO project)

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
- Planned: Amazon product search API, eBay Finding API, Reddit (r/deals, category subs),
  CamelCamelCamel (price history)
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

### Phase 1 (implemented)
- telescope ✅ question tree done
- laptop ✅ question tree done
- camera, headphones, keyboard, monitor, gpu — skeletons only
- generic — fallback (budget + brand + condition)

### Phase 2 (tickets filed)
- **drone** — full question tree needed (see gap analysis above)
- smart_telescope subcategory — bluetooth/phone/streaming criteria
- car (make/model/year/mileage/trim/location)
- house (location/sqft/beds/price/commute)
- software/SaaS (features/pricing/integrations)

### Phase 3 (future)
- context inference engine ("beach" → boost wind_resistance automatically)
- parameter education delivery before question loop
- per-user weight profiles (learning from past purchases)

---

## Context Inference Engine (planned)

The goal is to extract implicit requirements from natural language that the user
didn't spell out, but are obviously implied.

Examples:
- "at the beach" → `wind_resistance` weight bumped to 9; `saltwater_safe` added
- "back deck at night" → `use_case=astrophotography` pre-filled; `portability=balcony/home`
- "for my kid" → `durability` weight raised; `price` ceiling lowered
- "for travel" → `folding=true` added as want; `weight_max` criterion added

Implementation: keyword → criterion mapping table, run against goal string before
presenting first question. Reduces round-trips significantly.

---

## Integration Points

- **Oblio heartbeat**: surface active sessions with new matches
- **Jira**: each shopping session gap becomes a FALOO task; agent transitions when done
- **Discord/Telegram**: alerts delivered as rich messages with buy links
- **CamelCamelCamel**: price history charts for Amazon products
- **SQL memory**: full history of what was considered and why
- **Amazon Product Advertising API**: live product data with specs, prices, reviews
- **eBay Finding API**: used/refurb listings; auction monitoring
