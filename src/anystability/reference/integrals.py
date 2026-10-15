"""Exercise the S2 consumer interface with the existing horizontal box oracle.

Not an ANYgeometry adapter; does not admit tilted hull cuts, B1 or Q08.
"""
from dataclasses import dataclass
from .box import AnalyticBoxProvider, estimated
from ..providers.integrals import (IntegralRequest, IntegralSample, PlaneFrame,
                                  PreparedBinding, WaterplaneMoments)
from ..validation import invalid


@dataclass(frozen=True)
class ReferenceBoxIntegrals:
    box: AnalyticBoxProvider

    def __post_init__(self):
        if not isinstance(self.box, AnalyticBoxProvider):
            invalid("reference integral provider requires an analytical box")

    @property
    def binding(self):
        return PreparedBinding(self.box.binding, "analytical-box", self.box.source.identity,
                               ("external-box",), "anystability-reference-integrals/1",
                               "python-analytical", "horizontal-plus-z-no-boundary-planes")

    def evaluate_integrals(self, request: IntegralRequest):
        if not isinstance(request, IntegralRequest):
            invalid("typed integral request required")
        s = self.box.evaluate_halfspace(request.plane)
        d = request.plane.offset_m
        w = WaterplaneMoments(PlaneFrame((0., 0., d), (1., 0., 0.), (0., 1., 0.)),
                              s.waterplane_area_m2, (estimated(0.), estimated(0.)),
                              (s.waterplane_raw_xx_m4, s.waterplane_raw_yy_m4,
                               s.waterplane_raw_xy_m4), int(0 < d < self.box.height_m), 0)
        return IntegralSample(self.binding, request, s.volume_m3, s.first_moments_m4, w,
                              "empty" if d < 0 else "full" if d > self.box.height_m else "partial", 1)
