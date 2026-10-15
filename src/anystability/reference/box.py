"""Horizontal-plane box formulas only. No mesh, hull clipping or B1 emulation."""
from dataclasses import dataclass, field
import math
from ..domain import GeometrySource
from ..errors import ErrorCode, StabilityError
from ..providers.protocol import HalfSpace, HydrostaticSample, ProviderBinding, Quantity
from ..validation import canonical_bytes, exact, real

PROVIDER_ID = "reference_box_v1"


def estimated(value):
    # A conservative engineering roundoff allowance, NOT an interval proof.
    # Reject overflow through Quantity instead of propagating infinity/NaN.
    return Quantity(value, 32 * math.ulp(value))


@dataclass(frozen=True)
class AnalyticBoxProvider:
    length_m: float
    breadth_m: float
    height_m: float
    _source: GeometrySource | None = field(default=None, repr=False)

    def __post_init__(self):
        for name in ("length_m", "breadth_m", "height_m"):
            object.__setattr__(self, name, real(getattr(self, name), name, positive=True))
        area = self.length_m * self.breadth_m
        volume = area * self.height_m
        for name, value in (("area", area), ("capacity", volume),
                            ("vertical search bound", 2*self.height_m),
                            ("volume first moment", volume*self.height_m/2),
                            ("waterplane xx", area*self.length_m*self.length_m/12),
                            ("waterplane yy", area*self.breadth_m*self.breadth_m/12)):
            real(value, name, positive=True)
        if self._source is not None:
            data = exact(self._source.to_dict()["definition"],
                         {"length_m", "breadth_m", "height_m"}, "reference box")
            if self._source.provider_id != PROVIDER_ID or any(
                    real(data[k], k, positive=True) != getattr(self, k) for k in data):
                raise StabilityError(ErrorCode.SOURCE_STALE, "bound box definition differs")

    @property
    def source(self):
        if self._source is not None:
            return self._source
        data = dict(length_m=self.length_m, breadth_m=self.breadth_m, height_m=self.height_m)
        return GeometrySource(PROVIDER_ID, canonical_bytes(data).decode())

    @property
    def binding(self):
        return ProviderBinding(PROVIDER_ID, self.source.identity, "analytic-box/1", "analytical_reference")

    def vertical_search_domain(self):
        # Outside the box, avoiding ambiguous tangent waterplanes at z=0,H.
        return -self.height_m, 2*self.height_m

    def evaluate_halfspace(self, plane):
        if not isinstance(plane, HalfSpace):
            raise StabilityError(ErrorCode.INPUT_INVALID, "a typed half-space is required")
        if plane.normal != (0.0, 0.0, 1.0):
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED,
                                 "reference box admits only the exact +z plane normal",
                                 query=plane.to_dict())
        d = plane.offset_m
        if d == 0.0 or d == self.height_m:
            raise StabilityError(ErrorCode.QUERY_DEGENERATE,
                                 "waterplane coincides with the box bottom or top; area derivative is one-sided",
                                 query=plane.to_dict())
        depth = min(self.height_m, max(0.0, d))
        area = self.length_m*self.breadth_m
        volume = area*depth
        wet_area = area if 0.0 < d < self.height_m else 0.0
        return HydrostaticSample(
            self.binding, plane, estimated(volume),
            (estimated(0.0), estimated(0.0), estimated(volume*depth/2)),
            estimated(wet_area), estimated(wet_area*self.length_m*self.length_m/12),
            estimated(wet_area*self.breadth_m*self.breadth_m/12), estimated(0.0))

    @classmethod
    def from_source(cls, source):
        if source.provider_id != PROVIDER_ID:
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "not a reference-box source")
        data = source.to_dict()["definition"]
        return cls(**exact(data, {"length_m", "breadth_m", "height_m"}, "reference box"), _source=source)
