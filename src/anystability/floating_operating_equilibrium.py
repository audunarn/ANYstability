"""Operating mean equilibrium of a floating body under mean thrust, mooring and external mean loads (development).

The canonical hydrostatic mean pose is ANYstability's (``floating_equilibrium.mean_pose_from_result`` of an accepted
``solve_floating_equilibrium`` result); this module never re-implements hydrostatics, buoyancy or a CG.  Around that
owner pose it solves the full 6-DOF small-offset operating balance

    (K_r + K_m) q = w0_moor + w_ext + b T(V(q)),     V(q) = (U_b(theta) . n),  U_b = Q0^T U - theta x Q0^T U

with K_r the owner's linear restoring at the hydrostatic pose (caller supplied WITH its owner identity), the supplied
fairlead mooring (pretension w0 and consistent tangent K_m, attachment-recoverable), a mean external generalised force
and the mean thrust evaluated with the TRIAL rotor orientation (first-order body-frame wind pull-back, fixed rotor axis
n and hub offset r; b = [n; r x n]).  The thrust law is the supplied piecewise-linear ThrustCurve: the balance reduces
to one scalar equation in V that is solved segment by segment (exactly one root required; zero / several / an
interval of roots refuse).  Directions with zero restoring are a gauge ONLY when they carry no load; a loaded
unrestrained direction refuses.  The mean force/moment residual must be <= 1e-8 (separate force / moment scales) and
the offset rotation <= 5 degrees.

Limitations (explicit): this is a linear offset about the owner pose (no nonlinear owner re-solve with external loads -
the owner workflow has no external-wrench input); the hydrodynamic operators stay those of the hydrostatic pose and the
offset magnitude is reported for that reason.  Status is ``converged_development``; never a qualified equilibrium.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import numpy as np

ROTATION_LIMIT_RAD = math.radians(5.0)
RESIDUAL_TOLERANCE = 1e-8
NULL_TOLERANCE = 1e-10
STATUS = "converged_development"


class OperatingEquilibriumError(ValueError):
    """The operating balance is invalid, unloaded-gauge inconsistent, ambiguous or outside its envelope."""


def _arr(name, value, shape):
    raw = np.asarray(value)
    if raw.dtype.kind == "c":
        raise OperatingEquilibriumError(f"{name}: complex input refused")
    a = np.array(raw, dtype=np.float64)
    if a.shape != shape or not np.all(np.isfinite(a)):
        raise OperatingEquilibriumError(f"{name}: finite array of shape {shape} required")
    return a


def _rodrigues(theta):
    th = float(np.linalg.norm(theta))
    if th == 0.0:
        return np.eye(3)
    k = theta / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


@dataclass(frozen=True)
class OperatingEquilibrium:
    offset: tuple                    # q* (translation m, rotation rad) about the owner hydrostatic pose, mean-body axes
    mean_thrust: float
    rotor_axial_speed: float
    rotation_body_to_world: tuple    # Q0 @ exp(theta*) (reporting; operators are NOT rebound)
    cg_world: tuple
    residual: tuple                  # scaled force / moment residual components
    gauge_directions: tuple          # basis vectors of unloaded zero-restoring directions fixed to 0
    status: str
    identities: Mapping[str, Any]

    def to_dict(self) -> dict:
        return dict(offset=list(self.offset), mean_thrust=self.mean_thrust, rotor_axial_speed=self.rotor_axial_speed,
                    rotation_body_to_world=[list(r) for r in self.rotation_body_to_world], cg_world=list(self.cg_world),
                    residual=list(self.residual), gauge_directions=[list(g) for g in self.gauge_directions],
                    status=self.status, identities=dict(self.identities), qualification_status="unqualified",
                    limitations="linear offset about the owner hydrostatic pose; hydrodynamic operators not rebound")

    @property
    def identity(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


def solve_operating_equilibrium(*, hydrostatic_pose: Any, restoring: Any, restoring_identity: str,
                                mooring: Any = None, external_mean: Any = None, wind_mean_world: Any = None,
                                thrust_curve: Any = None, applicator: Any = None) -> OperatingEquilibrium:
    """``hydrostatic_pose``: owner MeanFloatingPose (or its ``to_dict``); ``restoring``: owner 6x6 linear restoring
    about that pose in mean-body axes about the CG; ``mooring``: anyloads AffineFairleadMooring with the same Q0;
    ``external_mean``: (6,) mean external generalised force; ``wind_mean_world`` + ``thrust_curve`` + ``applicator``:
    the mean thrust (all three together)."""
    pose = hydrostatic_pose.to_dict() if hasattr(hydrostatic_pose, "to_dict") else dict(hydrostatic_pose)
    Q0 = _arr("rotation_body_to_world", pose["rotation_body_to_world"], (3, 3))
    if np.max(np.abs(Q0.T @ Q0 - np.eye(3))) > 1e-10 or abs(np.linalg.det(Q0) - 1.0) > 1e-10:
        raise OperatingEquilibriumError("owner pose rotation is not proper")
    cg = _arr("cg_world_m", pose["cg_world_m"], (3,))
    if not isinstance(restoring_identity, str) or not restoring_identity:
        raise OperatingEquilibriumError("the owner restoring must carry its owner identity")
    K = _arr("restoring", restoring, (6, 6))
    w_ext = np.zeros(6) if external_mean is None else _arr("external_mean", external_mean, (6,))
    K_m, w0 = np.zeros((6, 6)), np.zeros(6)
    if mooring is not None:
        if np.max(np.abs(np.asarray(mooring.Q0) - Q0)) > 1e-12:
            raise OperatingEquilibriumError("the mooring model is not referenced to the owner pose rotation")
        K_m, w0 = np.asarray(mooring.stiffness_matrix()), np.asarray(mooring.pretension_wrench())
    turbine = (wind_mean_world, thrust_curve, applicator)
    if any(x is not None for x in turbine) and not all(x is not None for x in turbine):
        raise OperatingEquilibriumError("mean thrust needs wind_mean_world, thrust_curve and applicator together")
    A = K + K_m
    base = w0 + w_ext
    b = np.zeros(6); d = np.zeros(6); c0 = 0.0
    if applicator is not None:
        U0 = Q0.T @ _arr("wind_mean_world", wind_mean_world, (3,))
        n = np.asarray(applicator.rotor_axis_body, float)
        b = np.asarray(applicator.generalized_vector, float)
        d = np.r_[np.zeros(3), np.cross(U0, n)]
        c0 = float(U0 @ n)
    # ---- gauge: zero-restoring directions (SVD); loaded ones refuse
    U, s, Vt = np.linalg.svd(A)
    smax = float(s[0]) if s.size else 0.0
    null = s <= NULL_TOLERANCE * smax if smax > 0.0 else np.ones(6, bool)
    left_null, right_null = U[:, null], Vt[null].T
    s_inv = np.where(null, 0.0, 1.0 / np.where(null, 1.0, s))
    A_pinv = (Vt.T * s_inv) @ U.T

    def solve_for(T):
        rhs = base + b * T
        loaded = left_null.T @ rhs if left_null.size else np.zeros(0)
        scale = max(float(np.max(np.abs(base))), float(np.max(np.abs(b * T))), 0.0)
        if loaded.size and float(np.max(np.abs(loaded))) > RESIDUAL_TOLERANCE * max(scale, 0.0) and \
                float(np.max(np.abs(loaded))) > 0.0:
            raise OperatingEquilibriumError(
                "a direction without restoring carries a mean load (e.g. unmoored surge thrust): not a gauge; refused")
        return A_pinv @ rhs

    if applicator is None:
        q = solve_for(0.0)
        T_star, V_star = 0.0, float("nan")
    else:
        q0 = A_pinv @ base
        g = A_pinv @ b
        V_base, kappa = c0 - float(d @ q0), float(d @ g)
        sp, th = np.asarray(thrust_curve.speeds, float), np.asarray(thrust_curve.thrusts, float)
        gk = sp - V_base + kappa * th
        roots, interval = [], False
        for i in range(sp.size):
            if gk[i] == 0.0:
                roots.append(float(sp[i]))
        for i in range(sp.size - 1):
            if gk[i] == 0.0 and gk[i + 1] == 0.0:
                interval = True
            elif gk[i] != 0.0 and gk[i + 1] != 0.0 and (gk[i] < 0.0) != (gk[i + 1] < 0.0):
                roots.append(float(sp[i] + gk[i] / (gk[i] - gk[i + 1]) * (sp[i + 1] - sp[i])))
        if interval or len(roots) != 1:
            raise OperatingEquilibriumError(
                f"mean thrust balance has {'an interval of' if interval else len(roots)} roots in the curve domain; "
                "exactly one is required (no extrapolation, no branch choice)")
        V_star = roots[0]
        T_star = thrust_curve.thrust(V_star)
        q = solve_for(T_star)
    if right_null.size:
        q = q - right_null @ (right_null.T @ q)          # gauge: unloaded unrestrained directions fixed to 0
    # ---- verify the balance (separate force / moment scales) and the envelope
    terms = np.stack([A @ q, base, b * T_star])
    resid = terms[0] - terms[1] - terms[2]
    fs = float(np.max(np.linalg.norm(terms[:, :3], axis=1)))
    ms = float(np.max(np.linalg.norm(terms[:, 3:], axis=1)))
    scaled = []
    for comp, sc in ((resid[:3], fs), (resid[3:], ms)):
        for x in comp:
            scaled.append(0.0 if x == 0.0 else (abs(float(x)) / sc if sc > 0.0 else float("inf")))
    if max(scaled) > RESIDUAL_TOLERANCE:
        raise OperatingEquilibriumError(f"mean balance residual {max(scaled):.3e} exceeds {RESIDUAL_TOLERANCE:g}")
    if float(np.linalg.norm(q[3:])) > ROTATION_LIMIT_RAD:
        raise OperatingEquilibriumError("operating offset rotation exceeds the 5 degree linear envelope")
    if mooring is not None:
        mooring.check_validity(q)
    if applicator is not None:
        V_check = c0 - float(d @ q)
        if abs(V_check - V_star) > RESIDUAL_TOLERANCE * max(abs(V_star), abs(c0), 1e-300):
            raise OperatingEquilibriumError("rotor-axial speed of the solved pose is inconsistent with the root")
    Qop = Q0 @ _rodrigues(q[3:])
    cg_op = cg + Q0 @ q[:3]
    ids = dict(owner_pose=str(pose.get("result_identity", "")), owner_study=str(pose.get("study_identity", "")),
               owner_assurance=str(pose.get("assurance", "")), restoring=restoring_identity,
               mooring=None if mooring is None else list(mooring.identities),
               thrust_curve=None if thrust_curve is None else thrust_curve.content_hash(),
               applicator=None if applicator is None else applicator.content_hash(),
               operators_pose_offset_m_rad=[float(x) for x in q])
    return OperatingEquilibrium(tuple(float(x) for x in q), float(T_star), float(V_star),
                                tuple(tuple(float(x) for x in r) for r in Qop), tuple(float(x) for x in cg_op),
                                tuple(scaled), tuple(tuple(float(x) for x in col) for col in right_null.T),
                                STATUS, ids)


# ----------------------------------------------------------------------------- canonical full mean wrench
#
# The linear offset above is a development approximation only.  The canonical operating mean below evaluates the FULL
# mean wrench at every trial pose (world z up, still water at z = 0, pose world = Q x_body + t):
#
#   buoyancy   rho g V(Q, t) e_z at the owner buoyancy centre (geometry owner query, see ``owner_buoyancy``)
#   gravity    -m g e_z at the dry CG
#   thrust     T(U . Q n) Q n at the hub Q h + t (thrust at the CURRENT trial rotor orientation, no extrapolation)
#   mooring    caller callable (Q, t) -> world [F; M about the CG] (pretension included)
#   external   constant world [F; M about the CG]
#
# and solves the six balances by a bounded Newton iteration with a finite-difference Jacobian.  Directions without
# stiffness (e.g. yaw / x / y without mooring) are a neutral gauge ONLY when they carry no load: the step is the
# minimum-norm step and the converged residual must vanish in every direction, so a loaded unrestrained direction
# never converges and refuses.  ANYgeometry owns the geometry; this module never integrates a hull itself.

CANONICAL_STATUS = "converged_canonical_development"


def _parse_channels(record):
    """Neutral external-channel record (components 'FX'..'MZ', frames 'world'|'body', CG-relative body points,
    mean values) -> [(component, frame, point, mean)]; anything else refuses."""
    if record is None:
        return []
    comps, frames = list(record["components"]), list(record["frames"])
    pts, vals = np.asarray(record["points_body"], float), np.asarray(record["mean_values"], float)
    n = len(comps)
    if len(frames) != n or pts.shape != (n, 3) or vals.shape != (n,) or not np.all(np.isfinite(pts)) \
            or not np.all(np.isfinite(vals)):
        raise OperatingEquilibriumError("external channels: matching components / frames / (n,3) points / values")
    out = []
    for c, f, p, v in zip(comps, frames, pts, vals):
        if str(c) not in ("FX", "FY", "FZ", "MX", "MY", "MZ") or str(f) not in ("world", "body"):
            raise OperatingEquilibriumError(f"external channel {c!r} / frame {f!r} is not supported")
        out.append((str(c), str(f), p, float(v)))
    return out


def _skew(v):
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def owner_pose_parameters(Q, t):
    """Heel / trim / origin_z of the owner ``Pose`` whose waterplane equals that of (Q, t).

    The owner pose is R = Ry(-trim) Rx(heel); any proper Q = Rz(psi) R has the same third row (body coordinates of the
    world vertical), so the immersed half-space depends on (heel, trim, t_z) only and yaw / x / y are applied
    canonically to the owner's body-frame answer."""
    Q = np.asarray(Q, dtype=float)
    z = Q[2]
    trim = math.asin(max(-1.0, min(1.0, float(z[0]))))
    heel = math.atan2(float(z[1]), float(z[2]))
    return heel, trim, float(np.asarray(t, dtype=float)[2])


def owner_buoyancy(provider_query, name: str = "HULL"):
    """Adapter of the stability owner query (``workflow._OwnerProvider.query``-compatible callable
    ``(name, pose, offset, query_identity) -> {'volume_m3', 'cg_body_m', 'assurance', ...}``) to
    ``(Q, t) -> (volume, centre_body, assurance)``.  The owner answers in the body frame; nothing is recomputed here."""
    from .conventions import Pose

    def query(Q, t):
        heel, trim, z0 = owner_pose_parameters(Q, t)
        pose = Pose(heel, trim, z0)
        normal, offset = pose.waterplane(0.0)
        if np.max(np.abs(np.asarray(normal) - np.asarray(Q, float)[2])) > 1e-12:
            raise OperatingEquilibriumError("owner pose waterplane differs from the trial pose (convention mismatch)")
        ident = hashlib.sha256(json.dumps([name, heel, trim, z0]).encode()).hexdigest()
        answer = provider_query(name, pose, offset, ident)
        vol = float(answer["volume_m3"])
        c = answer.get("cg_body_m")
        centre = np.zeros(3) if c is None else np.asarray(c, dtype=float).reshape(3)
        return vol, centre, str(answer.get("assurance", ""))
    return query


@dataclass(frozen=True)
class CanonicalOperatingMean:
    rotation_body_to_world: tuple
    translation_world: tuple
    cg_world: tuple
    displaced_volume: float
    mean_thrust: float
    rotor_axial_speed: float
    components_world: Mapping[str, tuple]     # name -> world [F; M about the CG]
    residual_scaled: tuple
    gauge_directions: tuple
    iterations: int
    owner_queries: int
    status: str
    identities: Mapping[str, Any]
    pose_offset: tuple = ()                       # (dt_world (3), rotvec(Q Q_ref^T) (3)) from the hydrostatic reference
    mooring_mean_forces_world: Mapping[str, tuple] = None   # fairlead id -> evaluated world force at the operating pose

    def to_dict(self) -> dict:
        return dict(pose_offset=list(self.pose_offset),
                    mooring_mean_forces_world={k: list(v) for k, v in (self.mooring_mean_forces_world or {}).items()},
                    rotation_body_to_world=[list(r) for r in self.rotation_body_to_world],
                    translation_world=list(self.translation_world), cg_world=list(self.cg_world),
                    displaced_volume=self.displaced_volume, mean_thrust=self.mean_thrust,
                    rotor_axial_speed=self.rotor_axial_speed,
                    components_world={k: list(v) for k, v in self.components_world.items()},
                    residual_scaled=list(self.residual_scaled), gauge_directions=[list(g) for g in self.gauge_directions],
                    iterations=self.iterations, owner_queries=self.owner_queries, status=self.status,
                    identities=dict(self.identities), qualification_status="unqualified")

    @property
    def identity(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    def components_body(self) -> dict:
        """Component wrenches in body axes about the CG (the frame of the transient solver)."""
        Q = np.asarray(self.rotation_body_to_world)
        return {k: np.r_[Q.T @ np.asarray(v[:3]), Q.T @ np.asarray(v[3:])] for k, v in self.components_world.items()}

    def mean_equilibrium_record(self) -> dict:
        """The bound record ``FloatingTransientInput.mean_equilibrium`` requires (mean_thrust must equal it)."""
        ids = dict(self.identities)
        return {"identity": self.identity, "status": self.status, "mean_thrust": float(self.mean_thrust),
                "rotor_axial_speed": float(self.rotor_axial_speed),
                "rotation_body_to_world": [list(r) for r in self.rotation_body_to_world],
                "translation_world": list(self.translation_world), "cg_world": list(self.cg_world),
                "pose_offset": list(self.pose_offset), "kind": "canonical_full_mean_wrench",
                # every quantity a downstream input must reproduce exactly (bound, never re-derived downstream)
                "binding": {"mass": ids.get("mass"), "cg_body": ids.get("cg_body"), "rho": ids.get("rho"),
                            "gravity": ids.get("gravity"), "rotor_axis_body": ids.get("rotor_axis_body"),
                            "hub_body": ids.get("hub_body"), "thrust_curve": ids.get("thrust_curve_arrays"),
                            "wind_reference_mean_world": ids.get("wind_mean_world"),
                            "external_mean_world": ids.get("external_mean_world"),
                            "external_channels": ids.get("external_channels"),
                            "fairleads": ids.get("fairleads"),
                            "mooring_mean_forces_world": {k: list(v) for k, v in
                                                          (self.mooring_mean_forces_world or {}).items()},
                            "reference_pose": ids.get("reference_pose")}}


def _curve_eval(curve, V):
    sp, th = np.asarray(curve.speeds, float), np.asarray(curve.thrusts, float)
    if not sp[0] <= V <= sp[-1]:
        raise OperatingEquilibriumError(f"rotor-axial speed {V:.6g} outside the thrust curve domain (no extrapolation)")
    return float(curve.thrust(V)) if hasattr(curve, "thrust") else float(np.interp(V, sp, th))


def solve_operating_mean_canonical(*, buoyancy, mass: float, cg_body, rho: float, gravity: float,
                                   initial_rotation, initial_translation, length_scale: float,
                                   mooring=None, external_mean_world=None, wind_mean_world=None, thrust_curve=None,
                                   rotor_axis_body=None, hub_body=None, tolerance: float = RESIDUAL_TOLERANCE,
                                   max_iterations: int = 30, max_owner_queries: int = 400,
                                   poll=None, fairleads=None, external_channels=None,
                                   max_rotation_rad: float = ROTATION_LIMIT_RAD) -> CanonicalOperatingMean:
    """Canonical operating mean (see the section comment).  ``buoyancy`` is ``owner_buoyancy(...)`` (or a callable
    with the same contract); ``mooring(Q, t)`` returns the world [F; M about the CG] including pretension.

    ``fairleads``: affine attachment laws about the REFERENCE (initial = owner hydrostatic) pose, each
    ``{identity, point_body (ABSOLUTE body point), pretension_world (force at the reference pose), stiffness_world (3x3)}``:
    ``f_i(Q, t) = F0_i - K_i (x_i(Q, t) - x_i(Q_ref, t_ref))``.  They are EVALUATED at every trial pose (not reused
    unchanged); the evaluated forces at the operating pose are reported so a downstream perturbation model is
    relinearised about the operating pose (same affine law: same tangent, transported pretension).
    ``hub_body`` is an ABSOLUTE body point (the transient input uses hub - CG).  The total rotation from the reference
    pose must stay within ``max_rotation_rad`` (5 deg small-motion contract; may only tighten)."""
    if not 0.0 < float(max_rotation_rad) <= ROTATION_LIMIT_RAD:
        raise OperatingEquilibriumError("max_rotation_rad may only tighten the 5 degree small-motion contract")
    m = float(mass); L = float(length_scale)
    if not (m > 0 and rho > 0 and gravity > 0 and L > 0) or not all(map(math.isfinite, (m, rho, gravity, L))):
        raise OperatingEquilibriumError("mass, rho, gravity and length_scale must be positive and finite")
    cgb = _arr("cg_body", cg_body, (3,))
    Q = _arr("initial_rotation", initial_rotation, (3, 3)); t = _arr("initial_translation", initial_translation, (3,))
    if np.max(np.abs(Q.T @ Q - np.eye(3))) > 1e-10 or abs(np.linalg.det(Q) - 1.0) > 1e-10:
        raise OperatingEquilibriumError("initial rotation is not proper")
    w_ext = np.zeros(6) if external_mean_world is None else _arr("external_mean_world", external_mean_world, (6,))
    turbine = (wind_mean_world, thrust_curve, rotor_axis_body, hub_body)
    if any(x is not None for x in turbine) and not all(x is not None for x in turbine):
        raise OperatingEquilibriumError("mean thrust needs wind, curve, rotor axis and hub together")
    if thrust_curve is not None:
        U = _arr("wind_mean_world", wind_mean_world, (3,))
        n_b = _arr("rotor_axis_body", rotor_axis_body, (3,)); h_b = _arr("hub_body", hub_body, (3,))
        if abs(float(np.linalg.norm(n_b)) - 1.0) > 1e-12:
            raise OperatingEquilibriumError("rotor axis must be a unit vector")
    e_z = np.array([0.0, 0.0, 1.0])
    counter = {"q": 0}
    assurances = set()
    Q_ref, t_ref = Q.copy(), t.copy()
    channels = _parse_channels(external_channels)
    if channels and external_mean_world is not None and np.any(w_ext != 0.0):
        raise OperatingEquilibriumError("supply the external mean EITHER as attached channels OR as a standalone world "
                                        "wrench, not both (ambiguous double counting)")

    def channel_wrench(Qk):
        """Attached mean channels at the TRIAL pose: world-frame vectors stay world-fixed, body-frame vectors rotate
        with Qk; a force at the CG-relative body point p has the moment (Qk p) x F about the CG."""
        w = np.zeros(6)
        for comp, frame, p, m0 in channels:
            e = np.zeros(3); e["XYZ".index(comp[1])] = m0
            vec = e if frame == "world" else Qk @ e
            if comp[0] == "F":
                w += np.r_[vec, np.cross(Qk @ p, vec)]
            else:
                w[3:] += vec
        return w
    laws = []
    damping_world = {}
    seen = set()
    for f in (fairleads or ()):
        fid = str(f["identity"])
        if not fid or fid in seen:
            raise OperatingEquilibriumError("fairlead identities must be unique and non-empty")
        seen.add(fid)
        p = _arr(f"fairlead {fid} point_body", f["point_body"], (3,))
        laws.append((fid, p, _arr(f"fairlead {fid} pretension_world", f["pretension_world"], (3,)),
                     _arr(f"fairlead {fid} stiffness_world", f["stiffness_world"], (3, 3)), Q_ref @ p + t_ref))
        # damping does not enter the static mean but its declared WORLD frame is bound for the transient model
        damping_world[fid] = _arr(f"fairlead {fid} damping_world", f.get("damping_world", np.zeros((3, 3))), (3, 3))

    def fairlead_forces(Qk, tk):
        return {fid: F0 - K_i @ (Qk @ p + tk - x_ref) for fid, p, F0, K_i, x_ref in laws}

    def wrench(Qk, tk):
        if poll is not None:
            poll()
        counter["q"] += 1
        if counter["q"] > max_owner_queries:
            raise OperatingEquilibriumError(f"owner query budget {max_owner_queries} exhausted")
        cg_w = Qk @ cgb + tk
        vol, cb, assurance = buoyancy(Qk, tk)
        assurances.add(assurance)
        Fb = rho * gravity * vol * e_z
        comps = {"buoyancy": np.r_[Fb, np.cross(Qk @ cb + tk - cg_w, Fb)],
                 "gravity": np.r_[-m * gravity * e_z, np.zeros(3)],
                 "external": channel_wrench(Qk) if channels else w_ext.copy()}
        T = V = 0.0
        if thrust_curve is not None:
            a = Qk @ n_b
            V = float(U @ a)
            T = _curve_eval(thrust_curve, V)
            F = T * a
            comps["thrust"] = np.r_[F, np.cross(Qk @ (h_b - cgb), F)]      # hub_body is a body POINT
        if mooring is not None:
            comps["mooring"] = _arr("mooring wrench", mooring(Qk, tk), (6,))
        if laws:
            w = np.zeros(6)
            for (fid, p, _, _, _), f_i in zip(laws, fairlead_forces(Qk, tk).values()):
                w += np.r_[f_i, np.cross(Qk @ (p - cgb), f_i)]
            comps["mooring"] = comps.get("mooring", np.zeros(6)) + w
        return comps, T, V

    fs, ms = m * gravity, m * gravity * L

    def scaled(r):
        return np.r_[r[:3] / fs, r[3:] / ms]

    def apply(Qk, tk, dq):
        return _rodrigues(dq[3:]) @ Qk, tk + dq[:3] * L

    comps, T, V = wrench(Q, t)
    r = scaled(sum(comps.values()))
    it = 0
    h = 1e-6
    while float(np.max(np.abs(r))) > tolerance:
        if it >= max_iterations:
            raise OperatingEquilibriumError(f"canonical mean did not converge in {max_iterations} iterations "
                                            f"(scaled residual {float(np.max(np.abs(r))):.3e}); a loaded direction "
                                            "without restoring cannot balance")
        J = np.empty((6, 6))
        for j in range(6):
            dq = np.zeros(6); dq[j] = h
            Qj, tj = apply(Q, t, dq)
            J[:, j] = (scaled(sum(wrench(Qj, tj)[0].values())) - r) / h
        U_, s, Vt = np.linalg.svd(J)
        keep = s > 1e-10 * float(s[0]) if s[0] > 0 else np.zeros(6, bool)
        step = -(Vt[keep].T @ ((U_[:, keep].T @ r) / s[keep]))
        lam, best = 1.0, None
        for _ in range(8):
            Qn, tn = apply(Q, t, lam * step)
            cn, Tn, Vn = wrench(Qn, tn)
            rn = scaled(sum(cn.values()))
            if float(np.linalg.norm(rn)) < float(np.linalg.norm(r)):
                best = (Qn, tn, cn, Tn, Vn, rn)
                break
            lam *= 0.5
        if best is None:
            raise OperatingEquilibriumError("canonical mean line search failed (no residual decrease)")
        Q, t, comps, T, V, r = best
        it += 1
    rot_offset = _rotvec(Q @ Q_ref.T)
    if float(np.linalg.norm(rot_offset)) > float(max_rotation_rad):
        raise OperatingEquilibriumError(
            f"operating mean rotates {math.degrees(float(np.linalg.norm(rot_offset))):.3f} deg from the hydrostatic "
            f"reference pose; the retained small-motion contract allows {math.degrees(float(max_rotation_rad)):.3f} deg")
    # reported gauge: (near-)zero stiffness directions of the Jacobian AT the converged pose (reporting only; the
    # balance itself was verified in every direction above)
    J = np.empty((6, 6))
    for j in range(6):
        dq = np.zeros(6); dq[j] = h
        Qj, tj = apply(Q, t, dq)
        J[:, j] = (scaled(sum(wrench(Qj, tj)[0].values())) - r) / h
    _, s, Vt = np.linalg.svd(J)
    null = s <= 1e-6 * float(s[0]) if s[0] > 0 else np.ones(6, bool)
    gauge = tuple(tuple(float(x) for x in v) for v in Vt[null])
    ids = dict(owner_assurance=sorted(assurances), mass=m, cg_body=[float(x) for x in cgb], rho=float(rho),
               gravity=float(gravity), external_mean_world=[float(x) for x in w_ext],
               thrust_curve=None if thrust_curve is None or not hasattr(thrust_curve, "content_hash")
               else thrust_curve.content_hash(),
               wind_mean_world=None if wind_mean_world is None else [float(x) for x in U],
               mooring=None if mooring is None else str(getattr(mooring, "identity", "callable")))
    if thrust_curve is not None:
        ids.update(rotor_axis_body=[float(x) for x in n_b], hub_body=[float(x) for x in h_b],
                   thrust_curve_arrays=dict(speeds=[float(x) for x in np.asarray(thrust_curve.speeds, float)],
                                            thrusts=[float(x) for x in np.asarray(thrust_curve.thrusts, float)]))
    ids["external_channels"] = None if external_channels is None else json.loads(json.dumps(external_channels))
    ids["fairleads"] = [dict(identity=fid, point_body=p.tolist(), pretension_world=F0.tolist(),
                             stiffness_world=K_i.tolist(), damping_world=damping_world[fid].tolist(), frame="world")
                        for fid, p, F0, K_i, _ in laws]
    ids["reference_pose"] = dict(rotation_body_to_world=Q_ref.tolist(), translation_world=t_ref.tolist())
    forces = {fid: tuple(float(x) for x in f) for fid, f in fairlead_forces(Q, t).items()}
    vol = float(comps["buoyancy"][2] / (rho * gravity))
    return CanonicalOperatingMean(
        tuple(tuple(float(x) for x in row) for row in Q), tuple(float(x) for x in t),
        tuple(float(x) for x in (Q @ cgb + t)), vol, float(T), float(V),
        {k: tuple(float(x) for x in v) for k, v in comps.items()}, tuple(float(x) for x in r), gauge, it,
        counter["q"], CANONICAL_STATUS, ids,
        pose_offset=tuple(float(x) for x in np.r_[t - t_ref, rot_offset]), mooring_mean_forces_world=forces)


def _rotvec(R):
    c = max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0))
    th = math.acos(c)
    if th < 1e-12:
        return np.zeros(3)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2.0 * math.sin(th))
    return th * w


def affine_world_mooring(pretension_world, stiffness_world, reference_rotation, reference_translation, length_scale=1.0):
    """Development affine mooring about a reference pose: w = w0 - K [dt; rotvec(Q Q_ref^T)] (world, about the CG).
    Labelled development: a nonlinear line model belongs to the mooring owner."""
    w0 = _arr("pretension_world", pretension_world, (6,)); K = _arr("stiffness_world", stiffness_world, (6, 6))
    Qr = _arr("reference_rotation", reference_rotation, (3, 3)); tr = _arr("reference_translation", reference_translation, (3,))

    def mooring(Qk, tk):
        return w0 - K @ np.r_[np.asarray(tk) - tr, _rotvec(np.asarray(Qk) @ Qr.T)]
    mooring.identity = hashlib.sha256(json.dumps([w0.tolist(), K.tolist(), Qr.tolist(), tr.tolist()]).encode()).hexdigest()
    return mooring
