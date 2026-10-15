"""Bounded-work fixed-attitude vertical search; not the S3 free-floating solver."""
import math
from .conventions import Pose, cross, generalized_rotation_forces
from .domain import AnalysisSettings, LoadingCondition
from .errors import ErrorCode, StabilityError
from .loading import aggregate_mass
from .providers.protocol import HalfSpace, HydrostaticSample, HydrostaticsProvider
from .validation import real, vector


def evaluate(provider: HydrostaticsProvider, plane: HalfSpace) -> HydrostaticSample:
    """Do not accept a provider returning a nearby plane or a foreign source."""
    binding = provider.binding
    sample = provider.evaluate_halfspace(plane)
    if not isinstance(sample, HydrostaticSample):
        raise StabilityError(ErrorCode.INPUT_INVALID, "provider returned an untyped sample")
    if sample.binding != binding or provider.binding != binding:
        raise StabilityError(ErrorCode.SOURCE_STALE, "geometry binding changed during evaluation")
    if sample.plane != plane:
        raise StabilityError(ErrorCode.SOURCE_STALE, "provider substituted a different physical query",
                             requested=plane.to_dict(), received=sample.plane.to_dict())
    return sample


def load_state(condition, pose, sample):
    """Physical wrench about the current body origin; no large WORLD offsets."""
    mass = aggregate_mass(condition)
    rho_g = real(condition.water_density_kg_m3 * condition.gravity_m_s2, "rho g", positive=True)
    weight = real(mass.mass_kg * condition.gravity_m_s2, "weight", positive=True)
    buoyancy = real(rho_g * sample.volume_m3.value, "buoyancy", nonnegative=True)
    rotated_j = pose.rotate(tuple(q.value for q in sample.first_moments_m4))
    rotated_g = pose.rotate(mass.cg_body_m)
    b_moment = vector(cross(rotated_j, (0.0, 0.0, rho_g)), "buoyancy moment")
    w_moment = vector(cross(rotated_g, (0.0, 0.0, -weight)), "weight moment")
    torque = vector(tuple(math.fsum(pair) for pair in zip(b_moment, w_moment)), "total moment")
    # In S1 this is expressly an estimate, not a formal total wrench enclosure.
    err = real(rho_g*sample.volume_m3.error + 32*math.ulp(max(weight, buoyancy)),
               "vertical residual error", nonnegative=True)
    return dict(mass=mass.to_dict(), pose=pose.to_dict(), hydrostatics=sample.to_dict(),
                buoyancy_force_N=[0.0, 0.0, buoyancy], weight_force_N=[0.0, 0.0, -weight],
                buoyancy_moment_Nm=list(b_moment), weight_moment_Nm=list(w_moment),
                net_moment_Nm=list(torque), generalized_heel_trim_Nm=list(generalized_rotation_forces(pose, torque)),
                vertical_residual_N=buoyancy-weight, vertical_residual_error_estimate_N=err,
                moment_reference="current_body_origin_WORLD_axes")


def prescribed_pose(provider, condition, pose):
    plane = HalfSpace(*pose.waterplane())
    return dict(mode="prescribed_pose", status="evaluated_not_equilibrated", query_count=1,
                state=load_state(condition, pose, evaluate(provider, plane)))


def solve_vertical(provider: HydrostaticsProvider, condition: LoadingCondition,
                   settings: AnalysisSettings) -> dict:
    """Find draft at heel=trim=0. Remaining rotations are constrained, not solved.

    The bracket is a SEARCH bracket using floating-point reference values.
    It is not published as a certified enclosure of a physical root.
    """
    mass = aggregate_mass(condition)
    target = real(mass.mass_kg / condition.water_density_kg_m3, "target displacement", positive=True)
    weight = real(mass.mass_kg * condition.gravity_m_s2, "weight", positive=True)
    force_limit = real(settings.force_relative_tolerance*weight, "force limit", positive=True)
    lo, hi = (real(v, "vertical search bound") for v in provider.vertical_search_domain())
    if not lo < hi or not math.isfinite(hi-lo):
        raise StabilityError(ErrorCode.INPUT_INVALID, "invalid vertical search domain")
    binding = provider.binding
    queries = 0

    def query(draft):
        nonlocal queries
        if queries >= settings.max_queries:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "vertical query budget exhausted",
                                 query_count=queries, limit=settings.max_queries,
                                 search_bracket_m=[lo, hi])
        queries += 1
        if provider.binding != binding:
            raise StabilityError(ErrorCode.SOURCE_STALE, "provider changed during search")
        plane = HalfSpace((0.0, 0.0, 1.0), draft)
        try:
            return evaluate(provider, plane)
        except StabilityError as exc:
            raise StabilityError(exc.code, str(exc), query_count=queries,
                                 requested=plane.to_dict(), provider_cause=exc.to_dict()) from exc

    lower, upper = query(lo), query(hi)
    if lower.volume_m3.value > upper.volume_m3.value:
        raise StabilityError(ErrorCode.INPUT_INVALID, "nonmonotone provider search endpoints")
    # The reference endpoint capacities are closed-form values. Their engineering
    # roundoff allowances are retained; this is not arbitrary Newton failure.
    if target < lower.volume_m3.value-lower.volume_m3.error or target > upper.volume_m3.value+upper.volume_m3.error:
        raise StabilityError(ErrorCode.NO_ROOT_IN_SEARCH_DOMAIN,
                             "mass displacement lies outside the declared monotone volume range",
                             target_volume_m3=target,
                             volume_range_m3=[lower.volume_m3.value, upper.volume_m3.value],
                             query_count=queries, proof_scope="analytical_reference_range_with_roundoff_estimate")
    if target <= lower.volume_m3.value+lower.volume_m3.error or target >= upper.volume_m3.value-upper.volume_m3.error:
        raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED,
                             "endpoint or zero-waterplane equilibrium does not determine a unique draft",
                             target_volume_m3=target, query_count=queries)
    while True:
        draft = lo + (hi-lo)/2
        if draft == lo or draft == hi:
            raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED,
                                 "floating-point resolution exhausted before requested convergence",
                                 query_count=queries, search_bracket_m=[lo, hi])
        sample = query(draft)
        state = load_state(condition, Pose(origin_z_m=-draft), sample)
        residual = abs(state["vertical_residual_N"]) + state["vertical_residual_error_estimate_N"]
        if residual <= force_limit and hi-lo <= settings.draft_tolerance_m:
            # Verify the final original query again; a warm start/cache is not a proof.
            final = load_state(condition, Pose(origin_z_m=-draft), query(draft))
            if abs(final["vertical_residual_N"]) + final["vertical_residual_error_estimate_N"] > force_limit:
                raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, "final residual verification failed")
            return dict(mode="fixed_attitude_vertical", status="engineering_converged",
                        rotational_equilibrium="not_solved", draft_m=draft, query_count=queries,
                        force_limit_N=force_limit, search_bracket_m=[lo, hi],
                        draft_uncertainty="search_bracket_not_certified_root_bound", state=final)
        if sample.volume_m3.value < target:
            lo = draft
        else:
            hi = draft
