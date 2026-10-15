"""Consumer-owned S1 contract, NOT an assertion of an existing ANYgeometry API."""
from dataclasses import dataclass
import math
from typing import Protocol
from ..validation import digest, invalid, real, text, vector


@dataclass(frozen=True)
class Quantity:
    value: float
    error: float
    assurance: str = "roundoff_estimate"

    def __post_init__(self):
        object.__setattr__(self, "value", real(self.value, "quantity value"))
        object.__setattr__(self, "error", real(self.error, "quantity error", nonnegative=True))
        if not isinstance(self.assurance, str) or self.assurance not in {"roundoff_estimate", "owner_certified_bound"}:
            invalid("unknown quantity assurance")

    def to_dict(self):
        return dict(value=self.value, error=self.error, assurance=self.assurance)


@dataclass(frozen=True)
class HalfSpace:
    normal: tuple[float, float, float]
    offset_m: float

    def __post_init__(self):
        n = vector(self.normal, "plane normal")
        if abs(math.hypot(*n) - 1.0) > 1e-12:
            invalid("plane normal must already be unit length")
        object.__setattr__(self, "normal", n)
        object.__setattr__(self, "offset_m", real(self.offset_m, "plane offset"))

    def to_dict(self):
        return dict(normal=list(self.normal), offset_m=self.offset_m)


@dataclass(frozen=True)
class ProviderBinding:
    provider_id: str
    source_hash: str
    implementation: str
    geometry_assurance: str

    def __post_init__(self):
        text(self.provider_id, "provider identity")
        digest(self.source_hash, "geometry source hash")
        text(self.implementation, "provider implementation")
        if not isinstance(self.geometry_assurance, str) or self.geometry_assurance not in {"analytical_reference", "owner_certified"}:
            invalid("unknown geometry assurance")

    def to_dict(self):
        return dict(provider_id=self.provider_id, source_hash=self.source_hash,
                    implementation=self.implementation, geometry_assurance=self.geometry_assurance)


@dataclass(frozen=True)
class HydrostaticSample:
    binding: ProviderBinding
    plane: HalfSpace
    volume_m3: Quantity
    first_moments_m4: tuple[Quantity, Quantity, Quantity]
    waterplane_area_m2: Quantity
    # Reference basis: body x/y, origin (0,0,offset), normal +z in S1.
    # General H1 basis/centroid support must be admitted in S2, never guessed.
    waterplane_raw_xx_m4: Quantity
    waterplane_raw_yy_m4: Quantity
    waterplane_raw_xy_m4: Quantity

    def __post_init__(self):
        if not isinstance(self.binding, ProviderBinding) or not isinstance(self.plane, HalfSpace):
            invalid("sample requires a typed provider binding and plane")
        moments = tuple(self.first_moments_m4)
        quantities = (self.volume_m3, self.waterplane_area_m2, *moments,
                      self.waterplane_raw_xx_m4, self.waterplane_raw_yy_m4, self.waterplane_raw_xy_m4)
        if len(moments) != 3 or any(not isinstance(v, Quantity) for v in quantities):
            invalid("sample requires validated quantity records")
        object.__setattr__(self, "first_moments_m4", moments)
        if self.volume_m3.value < 0 or self.waterplane_area_m2.value < 0:
            invalid("negative volume or waterplane area")
        if self.binding.geometry_assurance == "analytical_reference" and any(
                q.assurance != "roundoff_estimate" for q in quantities):
            invalid("reference calculations cannot claim owner-certified quantities")

    @property
    def center_of_buoyancy_m(self):
        if self.volume_m3.value <= self.volume_m3.error:
            return None
        return vector(tuple(q.value / self.volume_m3.value for q in self.first_moments_m4), "CB")

    def to_dict(self):
        return dict(binding=self.binding.to_dict(), plane=self.plane.to_dict(),
                    volume_m3=self.volume_m3.to_dict(),
                    first_moments_m4=[v.to_dict() for v in self.first_moments_m4],
                    center_of_buoyancy_body_m=self.center_of_buoyancy_m,
                    waterplane_area_m2=self.waterplane_area_m2.to_dict(),
                    waterplane_moment_basis="body_xy_at_plane_offset",
                    waterplane_raw_xx_m4=self.waterplane_raw_xx_m4.to_dict(),
                    waterplane_raw_yy_m4=self.waterplane_raw_yy_m4.to_dict(),
                    waterplane_raw_xy_m4=self.waterplane_raw_xy_m4.to_dict())


class HydrostaticsProvider(Protocol):
    @property
    def binding(self) -> ProviderBinding: ...

    def evaluate_halfspace(self, plane: HalfSpace) -> HydrostaticSample: ...

    def vertical_search_domain(self) -> tuple[float, float]: ...
