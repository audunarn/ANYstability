"""Neutral adapter: an accepted ANYstability engineering equilibrium -> mean pose for the floating response milestone.

This module never solves or invents an equilibrium; the caller runs ``create_stability_study`` +
``solve_floating_equilibrium`` (explicit opt-in, owner-pinned artifacts, B1/H1 gate) and passes the immutable result.
Only a COMPLETE result with an accepted equilibrium is admitted; the engineering/source-only assurance label is
carried through unchanged so downstream records never present it as qualified.  Horizontal position and yaw are the
caller's fixed datum (x0, y0, yaw0).
"""
from dataclasses import dataclass
import math
from .conventions import Pose
from .errors import ErrorCode, StabilityError


@dataclass(frozen=True)
class MeanFloatingPose:
    heel_rad: float
    trim_rad: float
    origin_z_m: float
    datum_xy_m: tuple
    rotation_body_to_world: tuple     # Q0 rows, body axes -> world (ANYstability Pose convention R=Ry(-trim)Rx(heel))
    cg_world_m: tuple
    study_identity: str
    result_identity: str
    assurance: str
    hydrostatic_GM_m: object = None

    def to_dict(self):
        return dict(heel_rad=self.heel_rad, trim_rad=self.trim_rad, origin_z_m=self.origin_z_m,
                    datum_xy_m=list(self.datum_xy_m), rotation_body_to_world=[list(r) for r in self.rotation_body_to_world],
                    cg_world_m=list(self.cg_world_m), study_identity=self.study_identity,
                    result_identity=self.result_identity, assurance=self.assurance, hydrostatic_GM_m=self.hydrostatic_GM_m)


def mean_pose_from_result(result, *, cg_body_m, datum_xy_m=(0.0, 0.0)) -> MeanFloatingPose:
    """Admit only a complete accepted equilibrium; ``cg_body_m`` is the authoritative dry-FE CG in body axes."""
    d = result.to_dict() if hasattr(result, 'to_dict') else dict(result)
    if d.get('status') != 'complete' or not d.get('equilibrium'):
        raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED,
                             f"floating response requires a complete accepted equilibrium (status={d.get('status')!r})")
    eq = d['equilibrium']
    pose = Pose(float(eq['heel_rad']), float(eq['trim_rad']), float(eq['origin_z_m']))
    cg = tuple(float(x) for x in cg_body_m)
    xy = tuple(float(x) for x in datum_xy_m)
    if len(cg) != 3 or len(xy) != 2 or not all(math.isfinite(x) for x in (*cg, *xy)):
        raise StabilityError(ErrorCode.INVALID_INPUT if hasattr(ErrorCode, 'INVALID_INPUT') else ErrorCode.EQUILIBRIUM_UNRESOLVED,
                             'finite body CG and datum required')
    rc = pose.rotate(cg)
    cg_world = (xy[0] + rc[0], xy[1] + rc[1], pose.origin_z_m + rc[2])
    return MeanFloatingPose(pose.heel_rad, pose.trim_rad, pose.origin_z_m, xy, pose.rotation, cg_world,
                            str(d.get('study_identity', '')), str(d.get('identity', '')), str(d.get('assurance', '')),
                            eq.get('hydrostatic_GM_m'))
