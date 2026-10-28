"""Isolated neutral-JSON OPERATING mean worker (runs under the runtime that holds the PINNED installed ANYgeometry).

``python -c "...; main(argv)" <input.json> <output.json>``.  Input: everything ``floating_equilibrium_worker`` takes
(envelope, mass_kg, cg_body_m, rho, gravity, datum_xy_m, owner_wheel, controls, allow_development) plus

  operating: { length_scale,
               wind_mean_world?, thrust_curve? {speeds, thrusts}, rotor_axis_body?, hub_body?   (all four together)
               external_mean_world? (6,),
               external_channels? (neutral channel description, bound verbatim),
               fairleads? [{identity, point_body (absolute body point), pretension_world, stiffness_world (3x3)}]
                          affine attachment laws about the hydrostatic pose, evaluated at the operating pose }

The worker first solves the owner HYDROSTATIC mean through the public workflow (unchanged worker path), then the
canonical full mean wrench (``floating_operating_equilibrium.solve_operating_mean_canonical``) with buoyancy from the
SAME authenticated owner provider (``workflow._OwnerProvider.query``; yaw / x / y applied canonically).  Output:
``{status: 'ok', hydrostatic_pose, operating, mean_equilibrium, components_body}`` or a structured refusal.
"""
import hashlib
import json
import sys

from .floating_equilibrium_worker import _atomic, _build_model


def _curve(data):
    import numpy as np
    from types import SimpleNamespace
    sp = np.asarray(data['speeds'], dtype=float); th = np.asarray(data['thrusts'], dtype=float)
    if sp.ndim != 1 or sp.shape != th.shape or sp.size < 2 or not np.all(np.diff(sp) > 0) or not np.all(np.isfinite(th)):
        raise ValueError('thrust curve needs >= 2 strictly increasing finite speeds with matching thrusts')
    digest = hashlib.sha256(json.dumps([sp.tolist(), th.tolist()]).encode()).hexdigest()
    return SimpleNamespace(speeds=sp, thrusts=th, thrust=lambda v: float(np.interp(v, sp, th)),
                           content_hash=lambda: digest)


def run(spec, poll=None):
    import numpy as np
    from anygeometry.serialization import to_dict
    from anygeometry.hydrostatics import hydrostatics
    from .floating_equilibrium_run import neutral_hull_bundle, solve_mean_equilibrium
    from .floating_operating_equilibrium import owner_buoyancy, solve_operating_mean_canonical
    from .workflow import _OwnerProvider, _source

    envelope = spec['envelope']
    model = _build_model(envelope)
    polygons = [[envelope['vertices'][i] for i in loop] for loop in envelope['faces']]
    pts = [p for f in polygons for p in f]
    zmin = min(p[2] for p in pts); zmax = max(p[2] for p in pts)
    full = hydrostatics(model, list(model.faces), point=(0.0, 0.0, zmax + 1.0), normal=(0.0, 0.0, 1.0), order=2, rtol=1e-8)
    volume = float(full['volume'])
    fraction = spec['mass_kg'] / (spec['rho'] * volume)
    if not 0.0 < fraction < 1.0:
        raise ValueError(f'dry mass is {fraction:.3g} of the full displacement envelope: the body cannot float')
    height = zmax - zmin
    bundle = neutral_hull_bundle(to_dict(model), polygons, volume, tuple(full['buoyancy_centre']))
    hydro = solve_mean_equilibrium(bundle, mass_kg=spec['mass_kg'], cg_body_m=spec['cg_body_m'],
                                   owner_wheel=spec['owner_wheel'], rho=spec['rho'], gravity=spec['gravity'],
                                   datum_xy_m=tuple(spec.get('datum_xy_m', (0.0, 0.0))),
                                   initial_origin_z_m=-(zmin + fraction * height),
                                   origin_z_bounds_m=(-zmax - 0.25 * height, -zmin + 0.25 * height),
                                   controls=spec.get('controls'), allow_development=bool(spec.get('allow_development')))
    pose = hydro.to_dict()
    Q0 = np.asarray(pose['rotation_body_to_world'], dtype=float)
    cg_body = np.asarray(spec['cg_body_m'], dtype=float)
    t0 = np.asarray(pose['cg_world_m'], dtype=float) - Q0 @ cg_body
    op = dict(spec['operating'])
    import time
    budget = float(spec.get('owner_deadline_s', 600.0))
    if not (budget > 0.0 and budget <= 3600.0):
        raise ValueError('owner_deadline_s must lie in (0, 3600] s (finite owner-query bound)')
    deadline = time.monotonic() + budget

    def bounded_poll():
        if poll is not None:
            poll()
        if time.monotonic() > deadline:
            raise TimeoutError(f'operating-mean owner queries exceeded {budget} s')
    provider = _OwnerProvider(dict(owner_wheel=spec['owner_wheel'], source=_source(bundle),
                                   geometry_mode='engineering_estimate'), bounded_poll, deadline)
    turbine = {}
    if op.get('thrust_curve') is not None:
        turbine = dict(wind_mean_world=op['wind_mean_world'], thrust_curve=_curve(op['thrust_curve']),
                       rotor_axis_body=op['rotor_axis_body'], hub_body=op['hub_body'])
    if op.get('mooring') is not None:
        raise ValueError('a lumped mooring wrench cannot be bound to structural attachments; supply per-fairlead '
                         'laws in operating.fairleads')
    try:
        eq = _solve(provider, spec, op, cg_body, Q0, t0, bounded_poll, turbine)
    finally:
        provider.finish()                                # runtime-owner integrity check on EVERY exit path
    return dict(hydrostatic_pose=pose, operating=eq.to_dict(), mean_equilibrium=eq.mean_equilibrium_record(),
                components_body={k: [float(x) for x in v] for k, v in eq.components_body().items()})


def _solve(provider, spec, op, cg_body, Q0, t0, bounded_poll, turbine):
    from .floating_operating_equilibrium import owner_buoyancy, solve_operating_mean_canonical
    return solve_operating_mean_canonical(buoyancy=owner_buoyancy(provider.query), mass=spec['mass_kg'], cg_body=cg_body,
                                        rho=spec['rho'], gravity=spec['gravity'], initial_rotation=Q0,
                                        initial_translation=t0, length_scale=float(op['length_scale']),
                                        poll=bounded_poll,
                                        external_mean_world=op.get('external_mean_world'),
                                        external_channels=op.get('external_channels'),
                                        fairleads=op.get('fairleads'), **turbine)


def main(argv):
    source, target = argv[0], argv[1]
    try:
        with open(source, 'r', encoding='utf-8') as stream:
            spec = json.load(stream)
        _atomic(target, dict(status='ok', **run(spec)))
        return 0
    except BaseException as error:        # structured refusal, never a partial pose
        code = getattr(error, 'code', None)
        _atomic(target, dict(status='error', type=type(error).__name__, code=str(code) if code else None, message=str(error)))
        return 1


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:3]))
