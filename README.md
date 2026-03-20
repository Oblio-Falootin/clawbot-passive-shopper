# clawbot-passive-shopper

> You describe what you want. The agent figures out what you actually need, then watches the market until it finds it.

## The idea

You want a telescope. Or a laptop. Or a camera. You know roughly what you want but not the exact model. Normal shopping: hours of tab hell, conflicting reviews, and eventually buying the wrong thing out of exhaustion.

This agent inverts that flow:

1. **Interview** — asks the right questions to build a precise requirement model
2. **Research** — finds matching options
3. **Score** — ranks against your weighted criteria (deal-breakers enforced)
4. **Monitor** — checks prices and new listings passively in the background
5. **Alert** — only interrupts you when something crosses your buy threshold

You answer questions once. The agent does the legwork. You buy when it tells you it found a great deal.

## Quick start

```python
from passive_shopper import PassiveShopper

shopper = PassiveShopper(backend='cloud', brave_api_key='...')

# Describe your goal
session = shopper.start_session(
    goal="I want a telescope for visual planetary observing, budget $300, beginner"
)

# Get clarifying questions
questions = shopper.get_next_questions(session)
for q in questions:
    print(f"{q.label}  [{q.ctype}]")

# Answer them
session = shopper.answer_questions(session, {
    "use_case": "visual only",
    "objects": "planets/moon",
    "aperture_min": 130,
    "portability": "balcony/home",
})

# See what matches
candidates = shopper.get_candidates(session)
for c in candidates:
    print(f"{c.score:.1f}/10  ${c.price}  {c.name}")

# Get alerts (candidates crossing your threshold)
alerts = shopper.get_alerts(session)
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design.

```
CriteriaModel       ← question trees per product category
CandidateScorer     ← weighted scoring, must_have deal-breakers
ListingMonitor      ← Brave Search + planned Amazon/eBay/Reddit
AlertEngine         ← threshold evaluation, sorted alerts
PassiveShopper      ← orchestrator + SQL persistence
```

## Running tests

```bash
pytest tests/test_passive_shopper.py -v
```

27 tests, all green.

## Supported categories

| Category | Status |
|---|---|
| telescope | ✅ Full question tree |
| laptop | ✅ Full question tree |
| camera | 🔲 Skeleton |
| headphones | 🔲 Skeleton |
| keyboard | 🔲 Skeleton |
| monitor | 🔲 Skeleton |
| gpu | 🔲 Skeleton |
| generic | ✅ Budget + brand + condition |

## SQL schema

State stored in `memory.Memories` (category='shopping_session') initially.
Dedicated tables planned: `ShoppingSessions`, `ShoppingCriteria`, `ShoppingCandidates`, `ShoppingAlerts`.

## License

MIT
