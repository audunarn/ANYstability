"""Run the PUBLIC coupled engineering workflow for a floating mean equilibrium from a neutral hull + dry-mass record.

No equilibrium root is implemented here: this builds the neutral source bundle and study, calls
``create_stability_study`` / ``solve_floating_equilibrium`` (explicit ``allow_development`` opt-in, pinned installed
ANYgeometry owner wheel, engineering-estimate geometry mode) and admits only a COMPLETE accepted result through
``mean_pose_from_result``.  The owner wheel is a required explicit input; its absence is refused, never bypassed, and
no analytic/reference box is ever substituted.
"""
import math
from .conventions import Pose
from .domain import LoadingCondition, MassItem
from .errors import ErrorCode, StabilityError
from .validation import content_hash
from .workflow import create_stability_study, solve_floating_equilibrium
from .floating_equilibrium import mean_pose_from_result


def neutral_hull_bundle(geometry_document, hull_faces_body_m, full_volume_m3, full_centroid_body_m):
    """Neutral source bundle: ``geometry_document`` is ``anygeometry.serialization.to_dict`` of the CLOSED displacement envelope."""
    definition = dict(hull=dict(faces_body_m=[[list(map(float, p)) for p in face] for face in hull_faces_body_m]), spaces={})
    files = {'definition.json': definition, 'HULL.geometry.json': geometry_document}
    manifest = dict(owner=dict(version='anyfem-floating-neutral-v1'),
                    files={name: content_hash(doc) for name, doc in files.items()},
                    capacity_comparisons=dict(HULL=dict(volume_m3=float(full_volume_m3),
                                                        centroid_body_m=[float(x) for x in full_centroid_body_m])))
    return dict(manifest=manifest, files=files)


def solve_mean_equilibrium(bundle, *, mass_kg, cg_body_m, owner_wheel, rho=1025.0, gravity=9.80665, datum_xy_m=(0.0, 0.0),
                           initial_origin_z_m, origin_z_bounds_m, heel_bound_rad=math.radians(25.0),
                           trim_bound_rad=math.radians(25.0), controls=None, cancel=None, allow_development=False):
    if not owner_wheel:
        raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED if hasattr(ErrorCode, 'CAPABILITY_UNSUPPORTED') else ErrorCode.INPUT_INVALID,
                             'floating equilibrium requires the pinned installed ANYgeometry owner wheel path (owner_wheel); none supplied')
    if allow_development is not True:
        raise StabilityError(ErrorCode.INPUT_INVALID,
                             'engineering/development equilibrium requires explicit allow_development=True opt-in')
    condition = LoadingCondition('floating-dry-fe', 'dry FE assembly',
                                 (MassItem('fe-dry-assembly', float(mass_kg), tuple(float(x) for x in cg_body_m),
                                           'anyfem_assembled_fe_mass', ('structure',)),),
                                 float(rho), float(gravity))
    study = create_stability_study(bundle, base_condition=condition, targets_m3={}, densities_kg_m3={},
                                   initial_pose=Pose(0.0, 0.0, float(initial_origin_z_m)),
                                   pose_bounds=[tuple(float(x) for x in origin_z_bounds_m),
                                                (-float(heel_bound_rad), float(heel_bound_rad)),
                                                (-float(trim_bound_rad), float(trim_bound_rad))],
                                   owner_wheel=str(owner_wheel), geometry_mode='engineering_estimate',
                                   allow_development=True)
    result = solve_floating_equilibrium(study, controls=controls, cancellation_check=cancel)
    return mean_pose_from_result(result, cg_body_m=cg_body_m, datum_xy_m=datum_xy_m)
