"""Opt-in adapter to the real H1 quadrature API; NEVER certified admission.

The pinned owner returns one normalized order-doubling indicator, not errors
for individual quantities. Do not convert these results into IntegralSample or
Quantity(owner_certified_bound). No private geometry, plane nudge or fallback.
"""
from dataclasses import dataclass
from importlib import metadata, util
from pathlib import Path
import hashlib
import json
import math
import time

from ..conventions import cross
from ..errors import ErrorCode, StabilityError
from ..validation import (canonical_bytes, content_hash, decode_json, exact,
                          integer, invalid, real, sequence, vector)
from .protocol import HalfSpace

OWNER_COMMIT = "21d0637bc7f090e03b88f785f75ea1821489db6d"
OWNER_PAYLOAD_SHA256 = "2c8c0cf0fae861b88f966db9960c15add693fb4e6214befd77e1fec84467b5aa"
OWNER_FILES = 134
SNAPSHOT_KIND = "anystability-h1-development-geometry-v1"
RESULT_KIND = "anystability-h1-development-query-v1"


def _opt_in(allowed):
    if type(allowed) is not bool or not allowed:
        raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED,
                             "H1 quadrature requires explicit allow_development=True; not certified production")


def _payload_digest(root):
    """Hash installed Python bytes before importing the optional owner package."""
    entries, size = [], 0
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "linked owner package members are refused")
        if p.is_file() and p.suffix.lower() in {".so", ".pyd", ".dll", ".dylib"}:
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "this H1 adapter admits only the pinned Python build")
        if not p.is_file() or p.suffix != ".py":
            continue
        size += p.stat().st_size
        if size > 64 * 1024 * 1024 or len(entries) >= 2000:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "owner source inventory exceeds inspection limit")
        name = "anygeometry/" + p.relative_to(root).as_posix()
        entries.append((name, hashlib.sha256(p.read_bytes()).hexdigest()))
    payload = "\n".join(f"{name} {sha}" for name, sha in sorted(entries)).encode()
    return hashlib.sha256(payload).hexdigest(), len(entries)


def verify_installed_owner(*, allow_development=False):
    """Source equivalence, not publisher authentication or numerical certification.

    Requires a non-editable wheel with the observed complete Python payload.
    The scientific environment is trusted; this is not a hostile-process sandbox.
    """
    _opt_in(allow_development)
    try:
        dist = metadata.distribution("ANYgeometry")
    except metadata.PackageNotFoundError as exc:
        raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, "the pinned ANYgeometry wheel is not installed") from exc
    spec = util.find_spec("anygeometry")
    root = Path(dist.locate_file("anygeometry")).absolute()
    if (spec is None or spec.origin is None or root.is_symlink()
            or Path(spec.origin).resolve() != (root / "__init__.py").resolve()):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "ANYgeometry import path differs from installed distribution")
    direct = dist.read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable", False):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "editable owner installs are not admitted")
    actual, count = _payload_digest(root)
    if dist.version != "0.4.5" or actual != OWNER_PAYLOAD_SHA256 or count != OWNER_FILES:
        raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, "installed ANYgeometry source is not the pinned H1 build",
                             expected_commit=OWNER_COMMIT, actual_payload_sha256=actual)
    return dict(source_commit=OWNER_COMMIT, python_payload_sha256=actual,
                python_files=count, distribution_version=dist.version,
                backend="python_only", verification="installed_python_source_equivalence",
                certified_hydrostatics=False)


@dataclass(frozen=True)
class H1Query:
    plane: HalfSpace
    order: int = 24
    rtol: float = 1e-8

    def __post_init__(self):
        if not isinstance(self.plane, HalfSpace):
            invalid("H1 query requires a HalfSpace")
        integer(self.order, "quadrature order", 4, 48)
        value = real(self.rtol, "relative order-doubling acceptance", positive=True)
        if not 1e-12 <= value <= 1e-4:
            invalid("development rtol must lie in [1e-12, 1e-4]")
        object.__setattr__(self, "rtol", value)

    def to_dict(self):
        return dict(plane=self.plane.to_dict(), order=self.order, rtol=self.rtol)


def _number(value, name):
    # Public H1 results include NumPy scalar values. No optional import here.
    if isinstance(value, (bool, str, bytes)):
        invalid(f"invalid owner {name}")
    try:
        return real(float(value), name)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, f"invalid owner {name}") from exc


def _point(value, name):
    if value is None:
        return None
    try:
        row = tuple(value)
    except TypeError as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, f"invalid owner {name}") from exc
    if len(row) != 3:
        invalid(f"owner {name} must have three components")
    return tuple(_number(v, name) for v in row)


def map_owner_result(raw, query):
    """Transport the ACTUAL source fields; fabricate neither raw moments nor bounds."""
    required = {"volume", "waterplane_area", "estimate", "frame", "buoyancy_centre",
                "flotation_centre", "i_transverse", "i_longitudinal", "i_product"}
    if not isinstance(raw, dict) or set(raw) not in (required, required | {"bm_transverse", "bm_longitudinal"}):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "unexpected H1 result fields")
    frame = raw["frame"]
    origin = _point(frame.origin, "frame origin")
    axes = tuple(_point(row, "frame axis") for row in frame.axes)
    if origin is None or len(axes) != 3 or any(row is None for row in axes):
        invalid("invalid owner frame")
    for i in range(3):
        for j in range(3):
            if abs(math.fsum(a*b for a, b in zip(axes[i], axes[j])) - float(i == j)) > 1e-12:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, "nonorthonormal H1 result frame")
    if any(abs(a-b) > 1e-12 for a,b in zip(cross(axes[0], axes[1]), axes[2])):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "improper H1 result frame")
    normal_length = math.hypot(*query.plane.normal)
    n = tuple(v / normal_length for v in query.plane.normal)
    d = query.plane.offset_m / normal_length
    normal_difference = max(abs(a-b) for a,b in zip(n, axes[2]))
    plane_residual = math.fsum(a*b for a,b in zip(n, origin)) - d
    scale = max(1., abs(d), math.hypot(*origin))
    if not math.isfinite(plane_residual) or normal_difference > 1e-12 or abs(plane_residual) > 1e-12*scale:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "owner frame is inconsistent with the requested plane")
    volume = _number(raw["volume"], "volume")
    area = _number(raw["waterplane_area"], "waterplane area")
    indicator = _number(raw["estimate"], "order-doubling indicator")
    if volume < 0 or area < 0 or not 0 <= indicator <= query.rtol:
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "nonphysical or unsettled H1 quantities; no clamp")
    cb = _point(raw["buoyancy_centre"], "CB")
    cf = _point(raw["flotation_centre"], "CF")
    if (volume > 0) != (cb is not None) or (area > 0) != (cf is not None):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "H1 centroid availability disagrees with volume/area")
    moments = {name: _number(raw[name], name) for name in ("i_transverse", "i_longitudinal", "i_product")}
    # Roundoff-dominated nominally zero waterplanes must not create enormous fake centroids/BM.
    # The owner has no rigorous zero-classification bound; retain unresolved rather than clamp.
    if 0 < area < 1e-12:
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "near-zero waterplane has no owner area enclosure")
    if moments["i_transverse"] < 0 or moments["i_longitudinal"] < 0:
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "negative centroidal moment; no clamp")
    if cf is not None and abs(math.fsum(a*b for a,b in zip(n, cf))-d) > 1e-12*max(scale, math.hypot(*cf)):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "flotation centre is off the waterplane")
    product_limit = math.sqrt(moments["i_transverse"]) * math.sqrt(moments["i_longitudinal"])
    if abs(moments["i_product"]) > product_limit + 1e-12*max(1., product_limit):
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "indefinite centroidal area tensor")
    bm = None
    if not (area > 0 and volume > 0) and "bm_transverse" in raw:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "unexpected H1 metacentric radii without volume/area")
    if area > 0 and volume > 0:
        if "bm_transverse" not in raw:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "missing H1 metacentric radii")
        bm = {"about_xi_m": _number(raw["bm_transverse"], "BM_T"),
              "about_eta_m": _number(raw["bm_longitudinal"], "BM_L")}
        for name, moment in (("about_xi_m", moments["i_transverse"]), ("about_eta_m", moments["i_longitudinal"])):
            if not math.isclose(bm[name], moment/volume, rel_tol=1e-12, abs_tol=1e-12):
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, "H1 BM disagrees with I/V")
    return dict(volume_m3=volume, center_of_buoyancy_body_m=cb,
                waterplane_area_m2=area, center_of_flotation_body_m=cf,
                centroidal_waterplane_moments_m4=dict(about_xi=moments["i_transverse"],
                    about_eta=moments["i_longitudinal"], product_xi_eta=moments["i_product"]),
                geometric_BM=bm, frame=dict(origin_body_m=origin, axes_rows_body=axes),
                plane_mapping=dict(unit_normal_difference=normal_difference,
                    offset_residual_m=plane_residual, exact_mapping_certified=False),
                order_doubling_indicator=indicator, quantity_error_bounds=None,
                section_topology=None, immersion="not_certified_by_owner")


class H1DevelopmentProvider:
    """Prepared private geometry snapshot, explicit planes, no production protocol.

    Order and call-count limits bound dispatch, not the owner's internal work.
    CLI/process callers must additionally set their process wall-time limit.
    """
    def __init__(self, model, face_ids, *, allow_development=False, max_queries=256):
        self._owner = verify_installed_owner(allow_development=allow_development)
        integer(max_queries, "H1 call limit", 1, 1000)
        ids = sequence(face_ids, "displacement face IDs", 128)
        for face_id in ids:
            integer(face_id, "face ID", 1, 2**53-1)
        if not ids or len(set(ids)) != len(ids):
            invalid("face selection must be nonempty and unique")
        from anygeometry import GeometryModel, from_dict, to_dict
        from anygeometry.shell_volume import closed_shell
        if not isinstance(model, GeometryModel) or model.units != "m":
            invalid("H1 requires an ANYgeometry model in metres")
        if model.coordinate_transform is not None or any(float(v) != 0 for v in model.local_origin):
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "H1 development requires explicit BODY-local geometry; no implicit CRS transform")
        # Owner codec owns all reconstruction and section checks. Detach external mutations.
        self._snapshot = canonical_bytes(to_dict(model))
        if len(self._snapshot) > 2_000_000:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "development geometry exceeds snapshot limit")
        self._model = from_dict(decode_json(self._snapshot))
        self._faces = tuple(sorted(ids))
        if any(face_id not in self._model.faces for face_id in self._faces):
            invalid("foreign displacement face ID")
        problems = closed_shell(self._model, self._faces)
        if problems:
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "owner closed-shell check refused", owner_problems=problems)
        self._model_hash = content_hash(to_dict(self._model))
        self._calls, self._max_queries = 0, max_queries
        self._binding = dict(owner=self._owner, model_id=str(self._model.model_id),
            revision=self._model.revision, model_content_hash=self._model_hash,
            face_ids=list(self._faces), units="m", frame="BODY",
            topology_check="owner_closed_shell_consistent_connected",
            outward_normals_certified=False, closure_certificate=None)

    @classmethod
    def b1(cls, *, allow_development=False, max_queries=256):
        verify_installed_owner(allow_development=allow_development)
        from anygeometry.b1_example import build_b1_half_hull
        model, faces = build_b1_half_hull()
        return cls(model, tuple(faces.values()), allow_development=True, max_queries=max_queries)

    @classmethod
    def from_snapshot(cls, data, *, allow_development=False, max_queries=256):
        verify_installed_owner(allow_development=allow_development)
        payload = exact(decode_json(data), {"kind", "units", "coordinates", "face_ids", "model"}, "H1 geometry snapshot")
        if payload["kind"] != SNAPSHOT_KIND or payload["units"] != "m" or payload["coordinates"] != "BODY":
            invalid("unsupported H1 development geometry snapshot")
        from anygeometry import from_dict
        return cls(from_dict(payload["model"]), payload["face_ids"], allow_development=True, max_queries=max_queries)

    def snapshot_bytes(self):
        return canonical_bytes(dict(kind=SNAPSHOT_KIND, units="m", coordinates="BODY",
                                    face_ids=list(self._faces), model=decode_json(self._snapshot)))

    def _check_source(self):
        from anygeometry import to_dict
        if content_hash(to_dict(self._model)) != self._model_hash:
            raise StabilityError(ErrorCode.SOURCE_STALE, "prepared owner geometry changed")

    def evaluate(self, query: H1Query):
        if not isinstance(query, H1Query):
            invalid("H1 development expects a typed H1Query, not a certified IntegralRequest")
        self._check_source()
        if self._calls >= self._max_queries:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "H1 development query limit reached")
        # Use the source's explicit shift argument; NEVER point = n*d in rounded coordinates.
        import numpy as np
        from anygeometry.hydrostatics import hydrostatics
        from anygeometry.errors import GeometryError
        n = query.plane.normal
        shift = query.plane.offset_m / float(np.linalg.norm(n))
        self._calls += 1
        start = time.perf_counter()
        try:
            raw = hydrostatics(self._model, self._faces, (0., 0., 0.), normal=n,
                               longitudinal=(1., 0., 0.), order=query.order, rtol=query.rtol, shift=shift)
        except GeometryError as exc:
            self._check_source()
            code = (ErrorCode.ACCURACY_UNRESOLVED if "did not settle" in str(exc)
                    else ErrorCode.QUERY_DEGENERATE)
            raise StabilityError(code, "ANYgeometry H1 refused the requested plane",
                owner_exception=type(exc).__name__, owner_message=str(exc), query=query.to_dict()) from exc
        elapsed = time.perf_counter() - start
        self._check_source()
        values = map_owner_result(raw, query)
        return dict(kind=RESULT_KIND, status="computed_development_only",
                    binding=json.loads(canonical_bytes(self._binding)), query=query.to_dict(), values=values,
                    geometry_assurance="owner_quadrature_estimate", production_qualified=False,
                    owner_certificate_verified=False, equilibrium_solved=False, criteria="not_evaluated",
                    diagnostics=dict(owner_call_seconds=elapsed, owner_calls=self._calls,
                                     internal_work_units=None, plane_nudges=0, fallback_used=False))
