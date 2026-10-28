"""Versioned S2 consumer records. These names are NOT guessed owner APIs.

Records carry declarations, not admission authority. No constructor, JSON
receipt or certificate reference can enable the production provider selector.
S1 records and persisted analytical results remain byte-semantically unchanged.
"""
from dataclasses import dataclass
import math
from typing import Protocol
from ..conventions import cross
from ..errors import ErrorCode, StabilityError
from ..validation import (content_hash, digest, exact, integer, invalid,
                          real, sequence, text, vector)
from .bounds import Interval
from .protocol import HalfSpace, ProviderBinding, Quantity

VERSION = "anystability-integrals-v1"


def _qs(values, count, name):
    values = sequence(values, name, count)
    if len(values) != count or any(not isinstance(q, Quantity) for q in values):
        invalid(f"{name} requires {count} Quantity records")
    return values


def _q(data):
    return Quantity(**exact(data, {"value", "error", "assurance"}, "quantity"))


@dataclass(frozen=True)
class PreparedBinding:
    source: ProviderBinding
    model_id: str
    revision: str
    boundary_ids: tuple[str, ...]
    owner_api: str
    backend: str
    supported_domain: str
    artifact_sha256: str | None = None
    verifier_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.source, ProviderBinding):
            invalid("prepared binding requires a ProviderBinding")
        for name in ("model_id", "revision", "owner_api", "backend", "supported_domain"):
            text(getattr(self, name), name)
        if self.source.geometry_assurance == "owner_certified":
            digest(self.artifact_sha256, "declared geometry artifact SHA-256")
            text(self.verifier_id, "declared owner verifier identity")
        elif self.artifact_sha256 is not None or self.verifier_id is not None:
            invalid("analytical references cannot declare an owner artifact/verifier")
        ids = sequence(self.boundary_ids, "physical boundary selections")
        for item in ids:
            text(item, "boundary identity")
        if not ids or len(set(ids)) != len(ids):
            invalid("physical boundary selection must be nonempty and unique")
        object.__setattr__(self, "boundary_ids", tuple(sorted(ids)))

    def to_dict(self):
        return dict(source=self.source.to_dict(), model_id=self.model_id, revision=self.revision,
                    boundary_ids=list(self.boundary_ids), owner_api=self.owner_api,
                    backend=self.backend, supported_domain=self.supported_domain,
                    artifact_sha256=self.artifact_sha256, verifier_id=self.verifier_id,
                    units="m", frame="BODY")

    @property
    def identity(self):
        return content_hash(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"source", "model_id", "revision", "boundary_ids", "owner_api",
                         "backend", "supported_domain", "artifact_sha256", "verifier_id",
                         "units", "frame"}, "prepared binding")
        if d.pop("units") != "m" or d.pop("frame") != "BODY":
            invalid("integral geometry must use metres and BODY coordinates")
        d["source"] = ProviderBinding(**exact(d["source"], {"provider_id", "source_hash",
                                         "implementation", "geometry_assurance"}, "source"))
        return cls(**d)


@dataclass(frozen=True)
class Accuracy:
    """Maximum absolute input-quantity errors in the named SI units."""
    volume_m3: float = 1e-8
    first_moments_m4: float = 1e-7
    waterplane_area_m2: float = 1e-8
    waterplane_first_m3: float = 1e-7
    waterplane_second_m4: float = 1e-6

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, real(getattr(self, name), name, nonnegative=True))

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data):
        return cls(**exact(data, set(cls.__dataclass_fields__), "absolute quantity-error requests"))


@dataclass(frozen=True)
class IntegralRequest:
    query_id: str
    plane: HalfSpace
    accuracy: Accuracy = Accuracy()
    max_work_units: int = 100000

    def __post_init__(self):
        text(self.query_id, "query identity")
        if not isinstance(self.plane, HalfSpace) or not isinstance(self.accuracy, Accuracy):
            invalid("typed plane and accuracy required")
        integer(self.max_work_units, "geometry work limit", 1, 10000000)

    def to_dict(self):
        return dict(query_id=self.query_id, plane=self.plane.to_dict(),
                    accuracy=self.accuracy.to_dict(), max_work_units=self.max_work_units)

    def cache_identity(self, binding: PreparedBinding):
        # No rounded coordinates, fuzzy matching or relaxed accuracy cache keys.
        return content_hash(dict(version=VERSION, binding=binding.to_dict(), request=self.to_dict()))

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"query_id", "plane", "accuracy", "max_work_units"}, "integral request")
        d["plane"] = HalfSpace(**exact(d["plane"], {"normal", "offset_m"}, "plane"))
        d["accuracy"] = Accuracy.from_dict(d["accuracy"])
        return cls(**d)


@dataclass(frozen=True)
class PlaneFrame:
    origin_body_m: tuple[float, float, float]
    u_body: tuple[float, float, float]
    v_body: tuple[float, float, float]

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, vector(getattr(self, name), name))
        u, v = self.u_body, self.v_body
        if (abs(math.hypot(*u)-1) > 1e-12 or abs(math.hypot(*v)-1) > 1e-12
                or abs(math.fsum(a*b for a, b in zip(u, v))) > 1e-12):
            invalid("waterplane axes must already be orthonormal; no repair")

    def validate_plane(self, plane: HalfSpace):
        n = cross(self.u_body, self.v_body)
        if any(abs(a-b) > 1e-12 for a, b in zip(n, plane.normal)):
            invalid("waterplane frame winding/normal mismatch")
        try:
            residual = math.fsum(a*b for a, b in zip(plane.normal, self.origin_body_m))-plane.offset_m
        except (OverflowError, ValueError):
            invalid("waterplane origin evaluation exceeds finite arithmetic range")
        scale = max(1., math.hypot(*self.origin_body_m), abs(plane.offset_m))
        if not math.isfinite(residual) or abs(residual) > 1e-12*scale:
            invalid("waterplane origin is not on the query plane")

    def to_dict(self):
        return {name: list(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class WaterplaneMoments:
    frame: PlaneFrame
    area_m2: Quantity
    first_m3: tuple[Quantity, Quantity]  # integral u, integral v
    second_m4: tuple[Quantity, Quantity, Quantity]  # integral u^2, v^2, uv (NOT torque tensor)
    components: int
    holes: int

    def __post_init__(self):
        if not isinstance(self.frame, PlaneFrame) or not isinstance(self.area_m2, Quantity):
            invalid("typed waterplane frame and area required")
        object.__setattr__(self, "first_m3", _qs(self.first_m3, 2, "waterplane first moments"))
        object.__setattr__(self, "second_m4", _qs(self.second_m4, 3, "waterplane second moments"))
        integer(self.components, "section components", 0, 1000000)
        integer(self.holes, "section holes", 0, 1000000)
        if self.area_m2.value < 0:
            invalid("waterplane area cannot be negative")
        if self.components == 0 and (self.holes or any(q.value != 0 for q in self.quantities())):
            invalid("absent section must have zero moments and no holes")
        # Raw and central second moments must not be definitely nonphysical.
        a, b, c = (Interval.of(q) for q in self.second_m4)
        if a.upper < 0 or b.upper < 0 or (a*b-c.square()).upper < 0:
            invalid("waterplane raw moments are definitely not positive semidefinite")
        area = Interval.of(self.area_m2)
        if area.lower > 0:
            u, v = (Interval.of(q) for q in self.first_m3)
            a, b, c = a-u.square()/area, b-v.square()/area, c-u*v/area
            if a.upper < 0 or b.upper < 0 or (a*b-c.square()).upper < 0:
                invalid("waterplane centroidal moments are definitely not positive semidefinite")

    def quantities(self):
        return (self.area_m2, *self.first_m3, *self.second_m4)

    def to_dict(self):
        return dict(frame=self.frame.to_dict(), area_m2=self.area_m2.to_dict(),
                    first_m3=[q.to_dict() for q in self.first_m3],
                    second_m4=[q.to_dict() for q in self.second_m4],
                    components=self.components, holes=self.holes, convention="raw_u2_v2_uv")

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"frame", "area_m2", "first_m3", "second_m4", "components", "holes",
                         "convention"}, "waterplane moments")
        if d.pop("convention") != "raw_u2_v2_uv":
            invalid("unrecognized waterplane moment convention")
        d["frame"] = PlaneFrame(**exact(d["frame"], set(PlaneFrame.__dataclass_fields__), "plane frame"))
        d["area_m2"] = _q(d["area_m2"])
        for name, count in (("first_m3", 2), ("second_m4", 3)):
            d[name] = tuple(_q(v) for v in sequence(d[name], name, count))
        return cls(**d)


@dataclass(frozen=True)
class IntegralSample:
    binding: PreparedBinding
    request: IntegralRequest
    volume_m3: Quantity
    first_moments_m4: tuple[Quantity, Quantity, Quantity]
    waterplane: WaterplaneMoments | None
    immersion: str
    work_units: int
    certificate_ref: str | None = None
    section_ref: str | None = None
    events: tuple[str, ...] = ()

    def __post_init__(self):
        if (not isinstance(self.binding, PreparedBinding) or not isinstance(self.request, IntegralRequest)
                or not isinstance(self.volume_m3, Quantity)
                or (self.waterplane is not None and not isinstance(self.waterplane, WaterplaneMoments))):
            invalid("integral sample requires typed binding, request and quantities")
        object.__setattr__(self, "first_moments_m4", _qs(self.first_moments_m4, 3, "volume first moments"))
        if self.waterplane is None:
            if self.binding.source.geometry_assurance != "owner_certified" or self.immersion not in {"empty", "full"}:
                invalid("absent waterplane requires owner-certified empty/full occupancy")
        else:
            self.waterplane.frame.validate_plane(self.request.plane)
        integer(self.work_units, "actual provider work units", 0, 10000000)
        if not isinstance(self.immersion, str) or self.immersion not in {"empty", "full", "partial", "boundary"} or self.volume_m3.value < 0:
            invalid("invalid immersion or negative volume")
        if self.immersion == "full" and self.volume_m3.value == 0:
            invalid("a full displacement domain must have positive volume")
        if self.immersion == "empty" and any(q.value != 0 for q in (self.volume_m3, *self.first_moments_m4)):
            invalid("empty displacement must have zero volume and first moments")
        if self.immersion in {"empty", "full"} and self.waterplane is not None and self.waterplane.components:
            invalid("empty/full away from the boundary cannot contain a section")
        for name in ("certificate_ref", "section_ref"):
            if getattr(self, name) is not None:
                text(getattr(self, name), name)
        events = sequence(self.events, "section events", 1000)
        for event in events:
            text(event, "owner section event code")
        object.__setattr__(self, "events", events)
        qs = (self.volume_m3, *self.first_moments_m4, *(self.waterplane.quantities() if self.waterplane is not None else ()))
        if self.binding.source.geometry_assurance == "analytical_reference":
            if self.certificate_ref is not None or any(q.assurance != "roundoff_estimate" for q in qs):
                invalid("reference records cannot claim owner certificates/bounds")
        elif self.certificate_ref is None or any(q.assurance != "owner_certified_bound" for q in qs):
            invalid("declared owner sample needs a certificate reference and bounds for every quantity")
        # Above are transport consistency checks, NOT calls to an owner verifier.

    def to_dict(self):
        return dict(version=VERSION, binding=self.binding.to_dict(), request=self.request.to_dict(),
                    volume_m3=self.volume_m3.to_dict(),
                    first_moments_m4=[q.to_dict() for q in self.first_moments_m4],
                    waterplane=None if self.waterplane is None else self.waterplane.to_dict(), immersion=self.immersion,
                    work_units=self.work_units, certificate_ref=self.certificate_ref,
                    section_ref=self.section_ref, events=list(self.events))

    @classmethod
    def from_dict(cls, data):
        d = exact(data, set(cls.__dataclass_fields__) | {"version"}, "integral sample")
        if d.pop("version") != VERSION:
            invalid("unsupported integral-record version")
        d["binding"] = PreparedBinding.from_dict(d["binding"])
        d["request"] = IntegralRequest.from_dict(d["request"])
        d["volume_m3"] = _q(d["volume_m3"])
        d["first_moments_m4"] = tuple(_q(v) for v in sequence(d["first_moments_m4"], "J", 3))
        d["waterplane"] = None if d["waterplane"] is None else WaterplaneMoments.from_dict(d["waterplane"])
        return cls(**d)


class IntegralProvider(Protocol):
    @property
    def binding(self) -> PreparedBinding: ...
    def evaluate_integrals(self, request: IntegralRequest) -> IntegralSample: ...


def checked_query(provider: IntegralProvider, request: IntegralRequest) -> IntegralSample:
    if not isinstance(request, IntegralRequest) or not isinstance(provider.binding, PreparedBinding):
        invalid("typed request and prepared provider required")
    binding = provider.binding
    try:
        sample = provider.evaluate_integrals(request)
    except StabilityError as exc:
        if provider.binding != binding:
            raise StabilityError(ErrorCode.SOURCE_STALE, "source changed during refused query",
                                 provider_cause=exc.to_dict()) from exc
        raise  # Original typed code, message, details and cause retained.
    if not isinstance(sample, IntegralSample):
        invalid("provider returned an untyped integral sample")
    if sample.binding != binding or provider.binding != binding:
        raise StabilityError(ErrorCode.SOURCE_STALE, "prepared source changed during query")
    if sample.request != request:
        raise StabilityError(ErrorCode.SOURCE_STALE, "provider substituted plane/accuracy/query identity",
                             requested=request.to_dict(), received=sample.request.to_dict())
    if sample.work_units > request.max_work_units:
        raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "provider exceeded declared work limit",
                             work_units=sample.work_units, limit=request.max_work_units)
    a, w = request.accuracy, sample.waterplane
    groups = (("V", (sample.volume_m3,), a.volume_m3),
              ("J", sample.first_moments_m4, a.first_moments_m4))
    if w is not None:
        groups += (("A_wp", (w.area_m2,), a.waterplane_area_m2),
              ("J_wp", w.first_m3, a.waterplane_first_m3),
              ("I_wp", w.second_m4, a.waterplane_second_m4))
    for name, qs, limit in groups:
        if any(q.error > limit for q in qs):
            raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "returned errors exceed requested accuracy",
                                 quantity=name, requested_absolute_error=limit,
                                 received_errors=[q.error for q in qs])
    return sample


def checked_batch(provider: IntegralProvider, requests, *, max_queries=1000):
    """Sequential bounded batch. Refusals are explicit; no gap filling or nudges.

    All requests are validated before work. A broken binding/protocol aborts the
    batch. Earlier successful queries are retained evidence, not overall success.
    There is no native batching or throughput qualification claim here.
    """
    integer(max_queries, "batch query limit", 1, 100000)
    requests = sequence(requests, "batch requests", 100000)
    if not requests:
        invalid("a batch must contain at least one request")
    if len(requests) > max_queries:
        raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "batch exceeds query limit before execution")
    if any(not isinstance(q, IntegralRequest) for q in requests):
        invalid("batch requires typed requests")
    if len({q.query_id for q in requests}) != len(requests):
        invalid("duplicate batch query identities")
    binding = provider.binding
    if not isinstance(binding, PreparedBinding):
        invalid("batch requires a prepared binding")
    entries, aborted = [], False
    recoverable = {ErrorCode.QUERY_DEGENERATE, ErrorCode.ACCURACY_UNRESOLVED,
                   ErrorCode.WORK_BUDGET_EXCEEDED, ErrorCode.CAPABILITY_UNSUPPORTED}
    for request in requests:
        if aborted:
            entries.append(dict(request=request.to_dict(), status="not_executed"))
            continue
        try:
            if provider.binding != binding:
                raise StabilityError(ErrorCode.SOURCE_STALE, "source changed between batch queries")
            sample = checked_query(provider, request)
            entries.append(dict(request=request.to_dict(), status="evaluated", sample=sample.to_dict()))
        except StabilityError as exc:
            entries.append(dict(request=request.to_dict(), status="refused", error=exc.to_dict()))
            aborted = exc.code not in recoverable
    complete = all(e["status"] == "evaluated" for e in entries)
    # Detached plain JSON output: mutating it cannot mutate provider or inputs.
    return dict(version=VERSION, binding=binding.to_dict(), mode="sequential_checked_batch",
                status="all_queries_evaluated" if complete else "incomplete", entries=entries,
                requested_count=len(requests), attempted_count=sum(e["status"] != "not_executed" for e in entries),
                production_admission="not_conferred_by_transport")
