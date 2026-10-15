"""Mass ledger aggregation with translated moments and stable summation."""
from dataclasses import dataclass
import math
from .domain import LoadingCondition
from .validation import invalid, real, vector


@dataclass(frozen=True)
class MassSummary:
    mass_kg: float
    cg_body_m: tuple[float, float, float]
    included_item_ids: tuple[str, ...]

    def to_dict(self):
        return dict(mass_kg=self.mass_kg, cg_body_m=list(self.cg_body_m),
                    included_item_ids=list(self.included_item_ids))


def aggregate_mass(condition: LoadingCondition) -> MassSummary:
    if not isinstance(condition, LoadingCondition):
        invalid("aggregate_mass requires a LoadingCondition")
    try:
        mass = math.fsum(v.mass_kg for v in condition.items)
        real(mass, "aggregate mass", positive=True)
        anchor = condition.items[0].cg_body_m
        cg = tuple(anchor[j] + math.fsum((v.mass_kg / mass) * (v.cg_body_m[j] - anchor[j])
                                       for v in condition.items) for j in range(3))
        vector(cg, "aggregate CG")
    except (OverflowError, ValueError) as exc:
        invalid(f"mass aggregation outside numeric range: {exc}")
    return MassSummary(mass, cg, tuple(v.item_id for v in condition.items))
