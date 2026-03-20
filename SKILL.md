---
name: passive-shopper
version: 0.1.0
description: >
  Passive purchase decision agent. Given a product goal, builds a structured
  requirement model (criteria, deal-breakers, nice-to-haves), then monitors
  listings/deals passively until criteria are met or a human decision is needed.
  Think of it as a tireless researcher who never forgets your shopping list.
author: Oblio-Falootin
tags: [shopping, research, decision-making, monitoring, passive]
requires:
  python: ">=3.10"
  packages:
    - requests
    - python-dotenv
    - pymssql
entrypoint: passive_shopper.py
---

# Passive Shopper Skill

## Overview

You are shopping for something. You have a vague idea of what you want but
not the exact model/price/specs. The passive shopper:

1. **Interviews** — asks the right questions to build a precise requirement model
2. **Researches** — finds options matching your model (web search, product APIs)
3. **Scores** — ranks candidates against your weighted criteria
4. **Monitors** — watches for price drops, new listings, deal alerts
5. **Alerts** — notifies you when a candidate crosses your buy threshold
6. **Learns** — updates weights from your feedback over time

## The Telescope Problem (canonical example)

> "I want a telescope."

That's too vague to act on. The agent needs to whittle it down:

- **Use case**: Visual observing? Astrophotography? Both?
- **Objects**: Planets, deep sky, Moon, or all?
- **Experience**: Beginner? Intermediate?
- **Budget**: Hard cap? Soft cap?
- **Portability**: Apartment balcony? Dark site trips? Both?
- **Mount**: GoTo? Manual? Dobsonian?
- **Aperture floor**: 70mm? 90mm? 130mm?

Each answer eliminates entire categories and surfaces the right 3–5 options.

## Usage

```python
from passive_shopper import PassiveShopper

shopper = PassiveShopper(backend='cloud')

# Start a new shopping session
session = shopper.start_session(
    goal="I want a telescope for visual planetary observing, budget $300",
    context={"experience": "beginner", "location": "urban balcony"}
)

# Get clarifying questions (returns list of Question objects)
questions = shopper.get_next_questions(session.id)

# Answer questions
shopper.answer_questions(session.id, {
    "use_case": "visual only",
    "objects": "planets and moon",
    "budget_hard_cap": 350,
    "portability": "balcony storage ok"
})

# Get ranked candidates
candidates = shopper.get_candidates(session.id)

# Start monitoring (runs as background task)
shopper.start_monitoring(session.id, check_interval_hours=4)

# Get current best deal
best = shopper.get_best_deal(session.id)
```

## SQL Schema

All state stored in `memory.ShoppingSession`, `memory.ShoppingCriteria`,
`memory.ShoppingCandidate`, `memory.ShoppingAlert` tables.

## Monitoring Sources

Configurable per-session. Default sources:
- Web search (Brave API)
- Amazon product search (unofficial)
- eBay listings
- Reddit r/deals, r/<hobby> mentions
- CamelCamelCamel price history (Amazon)

## Decision Model

Each criterion has a weight (0–10) and type:
- `must_have` — deal-breaker if not met (weight=∞)
- `want` — scored 0–10, weighted sum
- `nice_to_have` — bonus points only

Score = Σ(criterion_weight × criterion_score) / Σ(weights)
Alert threshold = score ≥ user-defined minimum (default: 7.5/10)
