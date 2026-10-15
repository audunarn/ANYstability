"""Body x forward, y port, z up; R = Ry(-trim) Rx(heel); angles in radians."""
from dataclasses import dataclass
import math
from .validation import real, vector


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


@dataclass(frozen=True)
class Pose:
    heel_rad: float = 0.0
    trim_rad: float = 0.0
    origin_z_m: float = 0.0

    def __post_init__(self):
        for name in ("heel_rad", "trim_rad", "origin_z_m"):
            object.__setattr__(self, name, real(getattr(self, name), name))

    @property
    def rotation(self):
        cp, sp = math.cos(self.heel_rad), math.sin(self.heel_rad)
        ct, st = math.cos(self.trim_rad), math.sin(self.trim_rad)
        return ((ct, -st*sp, -st*cp), (0.0, cp, -sp), (st, ct*sp, ct*cp))

    def rotate(self, point):
        p = vector(point, "body point")
        return vector(tuple(math.fsum(a*b for a, b in zip(row, p)) for row in self.rotation), "world vector")

    def waterplane(self, elevation_m=0.0):
        # Normal is already unit length by construction; no silent normalization.
        return self.rotation[2], real(elevation_m, "water elevation") - self.origin_z_m

    def to_dict(self):
        return dict(heel_rad=self.heel_rad, trim_rad=self.trim_rad, origin_z_m=self.origin_z_m,
                    rotation_body_to_world=[list(row) for row in self.rotation])


def generalized_rotation_forces(pose: Pose, torque_world):
    tx, ty, tz = vector(torque_world, "world torque")
    return (math.cos(pose.trim_rad)*tx + math.sin(pose.trim_rad)*tz, -ty)
