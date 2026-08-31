# Git & Conflict Management Guide

## The Problem

All four members touch the same three core files: `hospital.py`, `clinic.py`, and `cloud.py`. Without coordination, this will cause merge conflicts.

---

## The Fix: Module Extraction

Instead of everyone editing the core files directly, each member writes their logic in their own separate module file. The core files just import and call it. That way, edits to the core files are minimal and don't overlap.

### Each Member's Module File

| Member | Module to create | What goes in it |
|---|---|---|
| **A** | `rho_blinding.py` | `generate_rho()`, `extend_weight_vector()`, `extend_patient_vector()`, `correct_blinded_result()` |
| **B** | `bucketing.py` + `bucket_config.py` | Bucket groupings, padding functions, batch payload builder |
| **C** | `security.py` | Rate limiter class, nonce validator, key rotation logic |
| **D** | `pathway_xai.py` | GMT loader, pathway weight builder, pathway key generator |

`bsgs.py` (Member A) is already its own standalone file — no conflicts there either.

### What the Core Files Look Like After

The core files become thin wrappers that import from each member's module:

```python
# hospital.py — example of what each member's addition looks like
from rho_blinding import generate_rho, extend_weight_vector   # Member A
from bucketing import get_bucket_dim, pad_weights             # Member B
from security import RateLimiter, KeyRotationManager          # Member C
# Member D adds /get_pathway_keys endpoint calling pathway_xai.py
```

```python
# clinic.py
from rho_blinding import extend_patient_vector, correct_blinded_result  # Member A
from bucketing import build_batch_payload                                # Member B
from security import make_query_id                                       # Member C
```

```python
# cloud.py
from bsgs import bsgs_discrete_log        # Member A
from security import validate_query_id    # Member C
# Member B adds /evaluate_batch endpoint
# Member D adds /evaluate_pathways endpoint
```

---

## The One Coordination Rule

The only thing you need to agree on upfront is **who adds the import line** for their module into each core file. That is literally one line per member per file — zero chance of conflicting logic.

Do this at the start of the week before anyone writes real code:
1. Each member opens their own git branch
2. Each member adds their `import` line to the relevant core files
3. Merge those import-only branches first (trivial to resolve)
4. Everyone then works entirely in their own module file

---

## Conflict Map (What to Watch Out For)

| Location | Members | Risk | How to resolve |
|---|---|---|---|
| `cloud.py` `/evaluate` function | A (replaces decrypt line) + C (adds validation before it) | 🟡 Medium | A owns line 47, C inserts at the top of the function. Agree on this once. |
| `hospital.py` startup block | A (extends weight vector) + B (changes model index) | 🟡 Medium | B commits their change first (Day 1), A builds on top of it |
| `clinic.py` payload block (lines 39–54) | A + B + C all add to this | 🔴 High | Each member moves their payload logic into their module. Core file just calls it. |
| New endpoints in `hospital.py`/`cloud.py` | C and D add new routes | 🟢 None | Adding new `@app.route` functions never conflicts |
| New standalone files | All members | 🟢 None | `bsgs.py`, `bucket_config.py`, `pathway_xai.py`, `security.py` — no conflicts |

---

## Recommended Merge Order (End of Week)

If you're merging branches at the end of the week, do it in this order to make conflicts easiest to resolve:

```
1. Member B  →  configurable model selection (touches startup, cleanest baseline)
2. Member A  →  rho blinding + BSGS (builds on B's startup changes)
3. Member C  →  security hardening (additive: new checks and endpoints)
4. Member D  →  pathway XAI (all new endpoints and module, no conflicts)
```

---

## Quick Git Workflow

```bash
# At the start — each member creates their branch
git checkout -b feature/member-a-rho-blinding
git checkout -b feature/member-b-bucketing
git checkout -b feature/member-c-security
git checkout -b feature/member-d-xai

# During the week — commit often to your own branch
git add rho_blinding.py bsgs.py hospital.py clinic.py cloud.py
git commit -m "Add BSGS solver and rho blinding skeleton"

# End of week — merge in order
git checkout main
git merge feature/member-b-bucketing
git merge feature/member-a-rho-blinding
git merge feature/member-c-security
git merge feature/member-d-xai
```

If a merge conflict comes up, it will almost always be in the `import` block or the payload dict — both are easy 5-second fixes.
