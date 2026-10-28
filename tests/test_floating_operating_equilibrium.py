"""Operating mean equilibrium about the owner hydrostatic pose: analytic thrust/mooring balances and refusals."""
import math

import numpy as np
import pytest

from anyloads.external_history import AffineFairleadMooring, FairleadSpec
from anyloads.wind_turbine import ThrustCurve, TurbineLoadApplicator
from anystability.floating_operating_equilibrium import OperatingEquilibriumError, solve_operating_equilibrium

POSE = dict(rotation_body_to_world=np.eye(3).tolist(), cg_world_m=[0.0, 0.0, -1.0], result_identity="owner-r",
            study_identity="owner-s", assurance="engineering")
KZ, KR, KP = 4.0e5, 3.0e7, 3.0e7
K = np.diag([0.0, 0.0, KZ, KR, KP, 0.0])
KX = KY = 2.0e4


def mooring():
    return AffineFairleadMooring((FairleadSpec("spread", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], np.diag([KX, KY, 0.0])),),
                                 np.eye(3), validity_half_range=np.array([5.0, 5.0, 5.0, 0.1, 0.1, 0.1]))


def curve(T0=1000.0, s=100.0):
    v = np.array([0.0, 20.0])
    return ThrustCurve(v, T0 + s * (v - 10.0))


def test_horizontal_rotor_balance_matches_closed_form_and_gauges_unloaded_yaw():
    app = TurbineLoadApplicator([0.0, 0.0, 10.0], [1.0, 0.0, 0.0])
    eq = solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K", mooring=mooring(),
                                     wind_mean_world=[10.0, 0.0, 0.0], thrust_curve=curve(), applicator=app)
    T = 1000.0
    assert eq.mean_thrust == pytest.approx(T) and eq.rotor_axial_speed == pytest.approx(10.0)
    assert np.allclose(eq.offset, [T / KX, 0.0, 0.0, 0.0, 10.0 * T / KP, 0.0], rtol=1e-12, atol=1e-15)
    assert max(eq.residual) <= 1e-8 and eq.status == "converged_development"
    assert len(eq.gauge_directions) == 1 and abs(abs(eq.gauge_directions[0][5]) - 1.0) < 1e-12     # yaw gauge
    assert eq.identities["restoring"] == "owner-K" and eq.identities["owner_pose"] == "owner-r"


def test_tilted_rotor_uses_the_trial_orientation_in_the_wind_projection():
    tilt = math.radians(6.0)
    app = TurbineLoadApplicator.from_yaw_tilt([0.0, 0.0, 10.0], tilt=tilt)
    T0, s = 1000.0, 100.0
    eq = solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K", mooring=mooring(),
                                     wind_mean_world=[10.0, 0.0, 0.0], thrust_curve=curve(T0, s), applicator=app)
    c, sn = math.cos(tilt), math.sin(tilt)
    # theta_y = 10 c T / KP ; V = 10 c + 10 sn theta_y ; T = T0 + s (V - 10)
    T = (T0 + s * (10.0 * c - 10.0)) / (1.0 - 100.0 * s * sn * c / KP)
    assert eq.mean_thrust == pytest.approx(T, rel=1e-12)
    assert eq.offset[4] == pytest.approx(10.0 * c * T / KP, rel=1e-12)
    assert eq.offset[0] == pytest.approx(c * T / KX, rel=1e-12) and eq.offset[2] == pytest.approx(sn * T / KZ, rel=1e-12)


def test_refusals():
    app = TurbineLoadApplicator([0.0, 0.0, 10.0], [1.0, 0.0, 0.0])
    with pytest.raises(OperatingEquilibriumError, match="without restoring"):        # unmoored surge carries thrust
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K",
                                    wind_mean_world=[10.0, 0.0, 0.0], thrust_curve=curve(), applicator=app)
    with pytest.raises(OperatingEquilibriumError, match="roots"):                    # outside the curve domain
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K", mooring=mooring(),
                                    wind_mean_world=[50.0, 0.0, 0.0], thrust_curve=curve(), applicator=app)
    soft = np.diag([0.0, 0.0, KZ, KR, 1.0e5, 0.0])
    with pytest.raises(OperatingEquilibriumError, match="5 degree"):
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=soft, restoring_identity="owner-K",
                                    mooring=mooring(), wind_mean_world=[10.0, 0.0, 0.0], thrust_curve=curve(),
                                    applicator=app)
    with pytest.raises(OperatingEquilibriumError, match="owner identity"):
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="", mooring=mooring())
    with pytest.raises(OperatingEquilibriumError, match="together"):
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K", mooring=mooring(),
                                    applicator=app)
    with pytest.raises(OperatingEquilibriumError, match="complex"):
        solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K * (1 + 0j), restoring_identity="owner-K")


def test_no_load_no_turbine_gives_zero_offset_with_gauges():
    eq = solve_operating_equilibrium(hydrostatic_pose=POSE, restoring=K, restoring_identity="owner-K")
    assert np.allclose(eq.offset, 0.0) and len(eq.gauge_directions) == 3 and eq.mean_thrust == 0.0


# ----------------------------------------------------------------------------- canonical full mean wrench
# Manufactured owner: an exact wall-sided box x in [-A, A], y in [-B, B], bottom at z = -H (body), answering the owner
# query contract (name, Pose, offset, identity) for the half-space n.x <= offset (n = Pose.rotation[2]).

from anystability.conventions import Pose  # noqa: E402
from anystability.floating_operating_equilibrium import (  # noqa: E402
    affine_world_mooring,
    owner_buoyancy,
    owner_pose_parameters,
    solve_operating_mean_canonical,
)

A_, B_, H_ = 5.0, 5.0, 10.0
RHO, GRAV = 1025.0, 9.81
MASS = RHO * 800.0
CG_B = np.array([0.0, 0.0, -6.0])


def box_owner(calls=None):
    def query(name, pose, offset, ident):
        if calls is not None:
            calls.append((name, pose, offset))
        n = np.asarray(pose.rotation[2])
        c, p, q = offset / n[2], n[0] / n[2], n[1] / n[2]
        area = 4 * A_ * B_
        ix, iy = 4 * A_ ** 3 * B_ / 3, 4 * A_ * B_ ** 3 / 3
        vol = area * (c + H_)
        x = -p * ix / vol
        y = -q * iy / vol
        z = (area * c * c + p * p * ix + q * q * iy - area * H_ * H_) / 2.0 / vol
        return dict(volume_m3=vol, cg_body_m=[x, y, z], assurance="manufactured_box")
    return query


def _rz(psi):
    c, s = math.cos(psi), math.sin(psi)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def test_owner_pose_parameters_remove_yaw_canonically():
    R = np.asarray(Pose(0.03, -0.02, 1.7).rotation)
    heel, trim, z = owner_pose_parameters(_rz(0.7) @ R, [3.0, -2.0, 1.7])
    assert heel == pytest.approx(0.03, abs=1e-14) and trim == pytest.approx(-0.02, abs=1e-14) and z == 1.7
    calls = []
    vol, c, _ = owner_buoyancy(box_owner(calls))(_rz(0.7) @ R, [3.0, -2.0, 1.7])
    vol0, c0, _ = owner_buoyancy(box_owner())(R, [0.0, 0.0, 1.7])
    assert vol == vol0 and np.array_equal(c, c0) and calls[0][0] == "HULL"


def test_canonical_mean_without_loads_balances_buoyancy_and_gauges_x_y_yaw():
    R0 = np.asarray(Pose(0.02, 0.01, 0.0).rotation)
    eq = solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=CG_B, rho=RHO,
                                        gravity=GRAV, initial_rotation=R0, initial_translation=[0.0, 0.0, 1.5],
                                        length_scale=10.0)
    assert eq.displaced_volume == pytest.approx(800.0, rel=1e-8)
    assert max(abs(x) for x in eq.residual_scaled) <= 1e-8 and eq.status == "converged_canonical_development"
    assert np.allclose(np.asarray(eq.rotation_body_to_world)[2], [0.0, 0.0, 1.0], atol=1e-7)
    assert eq.translation_world[2] == pytest.approx(2.0, rel=1e-7)
    assert len(eq.gauge_directions) == 3


def test_canonical_mean_with_thrust_uses_the_trial_orientation_and_mooring():
    k = np.diag([1.0e4, 1.0e4, 0.0, 0.0, 0.0, 1.0e6])
    moor = affine_world_mooring(np.zeros(6), k, np.eye(3), [0.0, 0.0, 2.0])
    eq = solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=CG_B, rho=RHO,
                                        gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                        length_scale=10.0, mooring=moor, wind_mean_world=[10.0, 0.0, 0.0],
                                        thrust_curve=curve(), rotor_axis_body=[1.0, 0.0, 0.0],
                                        hub_body=[0.0, 0.0, 20.0])
    Q = np.asarray(eq.rotation_body_to_world)
    assert eq.rotor_axial_speed == pytest.approx(10.0 * Q[0, 0], rel=1e-12)          # U . (Q n) at the solved pose
    assert eq.mean_thrust == pytest.approx(1000.0 + 100.0 * (eq.rotor_axial_speed - 10.0), rel=1e-12)
    total = sum(np.asarray(v) for v in eq.components_world.values())
    assert np.max(np.abs(total[:3])) <= 1e-8 * MASS * GRAV * 1.0001
    # x balance: mooring -k x + T (Q n)_x; residual gate 1e-8 m g ~ 0.08 N against ~1e3 N
    assert eq.translation_world[0] == pytest.approx(eq.mean_thrust * Q[0, 0] / 1.0e4, rel=1e-4)
    rec = eq.mean_equilibrium_record()
    assert rec["mean_thrust"] == eq.mean_thrust and rec["identity"] == eq.identity


def test_fairleads_are_evaluated_at_the_operating_pose_and_bound_with_absolute_hub():
    k = 1.0e4
    laws = [dict(identity=name, point_body=p, pretension_world=[0.0, 0.0, 0.0],
                 stiffness_world=np.diag([k, k, 0.0]).tolist())
            for name, p in (("fore", [5.0, 0.0, -2.0]), ("aft", [-5.0, 0.0, -2.0]))]
    cg = np.array([0.03, 0.0, -6.0])                                 # nonzero horizontal CG offset (~1.6 deg trim)
    eq = solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=cg, rho=RHO,
                                        gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                        length_scale=10.0, fairleads=laws, wind_mean_world=[10.0, 0.0, 0.0],
                                        thrust_curve=curve(), rotor_axis_body=[1.0, 0.0, 0.0],
                                        hub_body=[0.0, 0.0, 20.0], max_iterations=40)
    Q, t = np.asarray(eq.rotation_body_to_world), np.asarray(eq.translation_world)
    for law in laws:
        p = np.asarray(law["point_body"])
        dx = Q @ p + t - (p + np.array([0.0, 0.0, 2.0]))
        expect = -np.diag([k, k, 0.0]) @ dx                         # transported, NOT the reference pretension
        np.testing.assert_allclose(eq.mooring_mean_forces_world[law["identity"]], expect, atol=1e-9)
        assert np.linalg.norm(expect) > 1.0
    b = eq.mean_equilibrium_record()["binding"]
    assert b["hub_body"] == [0.0, 0.0, 20.0] and b["cg_body"] == cg.tolist()       # ABSOLUTE hub; CG separate
    assert b["wind_reference_mean_world"] == [10.0, 0.0, 0.0] and b["thrust_curve"]["speeds"] == [0.0, 20.0]
    assert set(b["mooring_mean_forces_world"]) == {"fore", "aft"} and len(eq.pose_offset) == 6


@pytest.mark.parametrize("frame", ["world", "body"])
def test_attached_external_mean_channels_are_evaluated_at_the_trial_pose(frame):
    k = 1.0e4
    laws = [dict(identity=name, point_body=p, pretension_world=[0.0, 0.0, 0.0],
                 stiffness_world=np.diag([k, k, 0.0]).tolist())
            for name, p in (("fore", [5.0, 0.0, -2.0]), ("aft", [-5.0, 0.0, -2.0]))]
    cg = np.array([0.02, 0.0, -6.0])
    p_att = [0.0, 0.0, 16.0]                                          # CG-relative attachment high above the CG
    ch = dict(components=["FX"], frames=[frame], points_body=[p_att], node_ids=[1], mean_values=[2.0e4])
    eq = solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=cg, rho=RHO,
                                        gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                        length_scale=10.0, fairleads=laws, external_channels=ch, max_iterations=40)
    Q = np.asarray(eq.rotation_body_to_world)
    assert abs(_pitch(Q)) > 1e-4                                       # a genuinely pitched trial/operating pose
    F = np.array([2.0e4, 0.0, 0.0]) if frame == "world" else Q @ np.array([2.0e4, 0.0, 0.0])
    expect = np.r_[F, np.cross(Q @ np.asarray(p_att), F)]              # lever Q p at the OPERATING pose
    np.testing.assert_allclose(eq.components_world["external"], expect, rtol=1e-12, atol=1e-9)
    assert eq.mean_equilibrium_record()["binding"]["external_channels"]["frames"] == [frame]
    with pytest.raises(OperatingEquilibriumError, match="EITHER"):
        solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=cg, rho=RHO,
                                       gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                       length_scale=10.0, fairleads=laws, external_channels=ch,
                                       external_mean_world=[1.0, 0, 0, 0, 0, 0])


def _pitch(Q):
    return float(np.arcsin(-Q[2, 0]))


def test_mean_rotation_beyond_the_5_degree_contract_is_refused():
    # large external heeling moment: converged heel above 5 degrees
    with pytest.raises(OperatingEquilibriumError, match="small-motion contract"):
        solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=CG_B, rho=RHO,
                                       gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                       length_scale=10.0, external_mean_world=[0.0, 0.0, 0.0, 1.5e6, 0.0, 0.0])
    with pytest.raises(OperatingEquilibriumError, match="only tighten"):
        solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=CG_B, rho=RHO,
                                       gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                       length_scale=10.0, max_rotation_rad=0.2)


def test_canonical_mean_refuses_a_loaded_unrestrained_direction():
    with pytest.raises(OperatingEquilibriumError):
        solve_operating_mean_canonical(buoyancy=owner_buoyancy(box_owner()), mass=MASS, cg_body=CG_B, rho=RHO,
                                       gravity=GRAV, initial_rotation=np.eye(3), initial_translation=[0.0, 0.0, 2.0],
                                       length_scale=10.0, wind_mean_world=[10.0, 0.0, 0.0], thrust_curve=curve(),
                                       rotor_axis_body=[1.0, 0.0, 0.0], hub_body=[0.0, 0.0, 20.0],
                                       max_iterations=8)
