"""Stage 3.5 - the no-loss proof + AI guardrail.

coverage() proves the bijection: every source content atom is placed exactly
once, with nothing invented. validate_plan() is the gate every AI-produced plan
must pass before it can touch the builder -- this is what makes using AI safe.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List

from .ir import Deck
from .planner import SlidePlan, referenced_ids


@dataclass
class Coverage:
    source: int
    placed: int
    lost: List[int]          # in source, never placed  -> content loss
    invented: List[int]      # placed, not in source     -> hallucination
    duplicated: List[int]    # placed more than once
    flagged: int             # placed but into a review bucket (still counted)

    @property
    def ok(self):
        return not self.lost and not self.invented and not self.duplicated and not self.flagged


def coverage(deck: Deck, plans: List[SlidePlan]) -> Coverage:
    source = set(deck.atoms.keys())
    placed_multiset = Counter()
    flagged = 0
    for p in plans:
        placed_multiset.update(referenced_ids(p))
        flagged += len(p.flagged)
    placed = set(placed_multiset.keys())
    lost = sorted(source - placed)
    invented = sorted(placed - source)
    duplicated = sorted(i for i, n in placed_multiset.items() if n > 1)
    return Coverage(source=len(source), placed=len(placed), lost=lost,
                    invented=invented, duplicated=duplicated, flagged=flagged)


def validate_plan(deck: Deck, plan: SlidePlan) -> List[str]:
    """Reject a single slide-plan if it references unknown ids or duplicates.
    Returns a list of error strings (empty => valid). Used to gate AI output."""
    errors = []
    if plan.flagged:
        errors.append('unresolved content cannot count as placed')
    slide_atoms = {a.id for a in deck.slide_atoms(plan.index)}
    refs = referenced_ids(plan)
    seen = Counter(refs)
    for i, n in seen.items():
        if i not in deck.atoms:
            errors.append(f"invented atom id {i} (not in source)")
        elif i not in slide_atoms:
            errors.append(f"atom id {i} belongs to another slide")
        if n > 1:
            errors.append(f"atom id {i} placed {n} times")
    missing = slide_atoms - set(refs)
    if missing:
        errors.append(f"omitted {len(missing)} atoms: {sorted(missing)[:8]}...")
    return errors
