"""One headless service layer. Reference selection must be explicit."""
from dataclasses import dataclass
from . import __version__
from .conventions import Pose
from .domain import (AnalysisSettings, GeometrySource, LoadingCondition, MassItem,
                     Project, VesselDefinition)
from .equilibrium import load_state, prescribed_pose, solve_vertical
from .errors import ErrorCode, StabilityError
from .loading import aggregate_mass
from .validation import canonical_bytes, content_hash, decode_json, exact, integer, invalid, real
from .providers.protocol import HalfSpace, HydrostaticSample, ProviderBinding, Quantity

ENGINE = {"package": "ANYstability", "version": __version__, "algorithm": "s1-reference/1"}
ASSURANCE = {"geometry": "analytical_reference", "numerics": "engineering_development",
             "continuous_curve": "not_evaluated", "criteria": "not_evaluated",
             "approval": "none", "production_qualified": False}


def capabilities():
    return dict(package="ANYstability", version=__version__, stage="S1_foundation",
                production_geometry=dict(available=False, code="PROVIDER_UNAVAILABLE",
                                         reason="No installed B1/H1 adapter has been admitted in this build"),
                reference_box=dict(explicit_opt_in_required=True, planes="horizontal +z only",
                                   calculations=["prescribed_pose", "fixed_attitude_vertical"],
                                   geometry_assurance="analytical_reference"),
                unavailable=["free_floating", "GZ", "tanks", "criteria", "GUI", "marine_numerical_exchange"])


def provider_for(project: Project, *, allow_reference: bool = False):
    if type(allow_reference) is not bool:
        invalid("allow_reference must be a boolean")
    source = project.vessel.geometry
    if source.provider_id == "anygeometry_h1":
        raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE,
                             "ANYgeometry H1 adapter and artifact admission are not implemented in this build",
                             required=["public half-space quantities and bounds", "installed B1 boundary verifier",
                                       "provider/source binding and supported-domain evidence"])
    if source.provider_id != "reference_box_v1":
        raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "unregistered geometry provider",
                             provider_id=source.provider_id)
    if not allow_reference:
        raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED,
                             "reference data requires explicit --allow-reference; no production fallback")
    from .reference.box import AnalyticBoxProvider
    provider = AnalyticBoxProvider.from_source(source)
    if provider.binding.source_hash != source.identity:
        raise StabilityError(ErrorCode.SOURCE_STALE, "provider definition does not match the saved geometry source")
    return provider


def example_project():
    # These are explicit reference inputs, not B1 dimensions or ship data.
    source = GeometrySource.from_dict(dict(provider_id="reference_box_v1",
                             definition=dict(length_m=20.0, breadth_m=10.0, height_m=4.0)))
    condition = LoadingCondition("reference-loaded", "Analytical reference condition", (
        MassItem("lightship", 205000.0, (0.0, 0.0, 1.5), "declared_reference", ("structure",)),
        MassItem("cargo", 205000.0, (0.0, 0.0, 2.5), "declared_reference", ("cargo",)),
    ))
    return Project(VesselDefinition("reference-box", "Analytical box (not B1)", source), condition)


@dataclass(frozen=True)
class AnalysisRecord:
    """Immutable transport snapshot. A hash is integrity, not independent proof."""
    payload_json: str

    def __post_init__(self):
        if not isinstance(self.payload_json, str):
            invalid("analysis payload must be JSON text")
        data = decode_json(self.payload_json.encode("utf-8"))
        d = exact(data, {"schema_version", "engine", "assurance", "input_hash", "inputs", "output"}, "analysis record")
        integer(d["schema_version"], "result schema", 1, 1)
        if d["engine"] != ENGINE:
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "result requires another engine/algorithm version")
        if canonical_bytes(d["assurance"]) != canonical_bytes(ASSURANCE):
            invalid("reference result cannot acquire production, criteria or certified assurance")
        project = Project.from_dict(d["inputs"])
        if d["input_hash"] != project.identity:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "result input identity mismatch")
        # Constructor/identity checks only: loading does NOT execute a solve.
        provider = provider_for(project, allow_reference=True)
        out = d["output"]
        if not isinstance(out, dict) or out.get("mode") not in {"prescribed_pose", "fixed_attitude_vertical"}:
            invalid("unimplemented result mode")
        mode = out["mode"]
        expected = {"mode", "status", "query_count", "state"}
        if mode == "fixed_attitude_vertical":
            expected |= {"rotational_equilibrium", "draft_m", "force_limit_N", "search_bracket_m", "draft_uncertainty"}
        exact(out, expected, "analysis output")
        expected_status = "evaluated_not_equilibrated" if mode == "prescribed_pose" else "engineering_converged"
        if out["status"] != expected_status:
            invalid("result mode/status mismatch")
        if mode == "fixed_attitude_vertical" and (out["rotational_equilibrium"] != "not_solved" or
                out["draft_uncertainty"] != "search_bracket_not_certified_root_bound"):
            invalid("S1 result cannot claim rotational or certified-root qualification")
        integer(out["query_count"], "query_count", 1, project.settings.max_queries)
        try:
            sample_data = out["state"]["hydrostatics"]
            if canonical_bytes(sample_data["binding"]) != canonical_bytes(provider.binding.to_dict()):
                raise StabilityError(ErrorCode.SOURCE_STALE, "stored provider binding differs from input source")
            qkeys = ("volume_m3", "waterplane_area_m2", "waterplane_raw_xx_m4",
                     "waterplane_raw_yy_m4", "waterplane_raw_xy_m4")
            quantities = {key: Quantity(**exact(sample_data[key], {"value", "error", "assurance"}, key))
                          for key in qkeys}
            moments = tuple(Quantity(**exact(v, {"value", "error", "assurance"}, "first moment"))
                            for v in sample_data["first_moments_m4"])
            plane = HalfSpace(**exact(sample_data["plane"], {"normal", "offset_m"}, "sample plane"))
            sample = HydrostaticSample(provider.binding, plane, first_moments_m4=moments, **quantities)
            if canonical_bytes(sample_data) != canonical_bytes(sample.to_dict()):
                invalid("stored hydrostatic quantities are inconsistent or have unknown fields")
            pose_data = exact(out["state"]["pose"],
                              {"heel_rad", "trim_rad", "origin_z_m", "rotation_body_to_world"}, "stored pose")
            pose = Pose(pose_data["heel_rad"], pose_data["trim_rad"], pose_data["origin_z_m"])
            if plane != HalfSpace(*pose.waterplane()) or plane.normal != (0.0, 0.0, 1.0):
                invalid("stored plane differs from producing pose or reference provider scope")
            expected_state = load_state(project.condition, pose, sample)
            if canonical_bytes(out["state"]) != canonical_bytes(expected_state):
                invalid("stored state does not match its mass, pose and hydrostatic quantities")
            if mode == "fixed_attitude_vertical":
                draft = real(out["draft_m"], "stored draft", positive=True)
                bracket = out["search_bracket_m"]
                if not isinstance(bracket, list) or len(bracket) != 2:
                    invalid("stored search bracket must have two values")
                lo, hi = (real(v, "stored bracket") for v in bracket)
                limit = real(out["force_limit_N"], "stored force limit", positive=True)
                expected_limit = (aggregate_mass(project.condition).mass_kg * project.condition.gravity_m_s2
                                  * project.settings.force_relative_tolerance)
                if limit != expected_limit or not lo <= draft <= hi or not 0 < hi-lo <= project.settings.draft_tolerance_m:
                    invalid("stored search evidence differs from declared tolerances")
                if pose != Pose(origin_z_m=-draft) or not 0 < draft < provider.height_m:
                    invalid("stored draft differs from fixed-attitude condition")
                if abs(expected_state["vertical_residual_N"]) + expected_state["vertical_residual_error_estimate_N"] > limit:
                    invalid("stored vertical result fails its residual test")
        except (KeyError, TypeError) as exc:
            raise StabilityError(ErrorCode.INPUT_INVALID, "malformed stored result state") from exc
        object.__setattr__(self, "payload_json", canonical_bytes(d).decode())

    def to_dict(self):
        return decode_json(self.payload_json.encode())

    @property
    def identity(self):
        return content_hash(self.to_dict())

    @property
    def project(self):
        return Project.from_dict(self.to_dict()["inputs"])

    def is_stale(self, project):
        return self.to_dict()["input_hash"] != project.identity


def analyze(project, *, calculation="equilibrium", pose=None, allow_reference=False):
    provider = provider_for(project, allow_reference=allow_reference)
    if calculation == "equilibrium":
        if pose is not None:
            invalid("S1 vertical equilibrium has fixed zero heel/trim; pose is not an input")
        output = solve_vertical(provider, project.condition, project.settings)
    elif calculation == "hydrostatics":
        if not isinstance(pose, Pose):
            invalid("prescribed hydrostatics requires an explicit Pose")
        output = prescribed_pose(provider, project.condition, pose)
    else:
        raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, "calculation not implemented", calculation=calculation)
    payload = dict(schema_version=1, engine=dict(ENGINE), assurance=dict(ASSURANCE), input_hash=project.identity,
                   inputs=project.to_dict(), output=output)
    return AnalysisRecord(canonical_bytes(payload).decode())


def reproduce(record):
    """Explicit replay of stored reference inputs; never run implicitly on load."""
    out = record.to_dict()["output"]
    if out["mode"] == "fixed_attitude_vertical":
        fresh = analyze(record.project, allow_reference=True)
    else:
        p = out["state"]["pose"]
        fresh = analyze(record.project, calculation="hydrostatics", allow_reference=True,
                        pose=Pose(p["heel_rad"], p["trim_rad"], p["origin_z_m"]))
    if canonical_bytes(fresh.to_dict()) != canonical_bytes(record.to_dict()):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "stored result does not reproduce with its declared engine")
    return fresh
