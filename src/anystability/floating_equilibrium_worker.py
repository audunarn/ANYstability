"""Isolated neutral-JSON equilibrium worker (runs under the runtime that holds the PINNED installed ANYgeometry).

``python -c "...; main(argv)" <input.json> <output.json>``.  Input (all neutral):
  polygons_body_m   closed displacement envelope, list of faces (each a list of 3D vertices, outward-oriented loops)
  mass_kg, cg_body_m, rho, gravity, datum_xy_m, owner_wheel, controls (optional), allow_development
The worker builds the geometry model with the installed owner, derives the full capacity with the owner's hydrostatics,
runs the PUBLIC ``create_stability_study`` / ``solve_floating_equilibrium`` and writes the accepted mean pose (or a
structured refusal) atomically.  Nothing is bypassed: the pinned-wheel authentication inside the workflow still applies.
"""
import json
import math
import os
import sys
import tempfile


def _plane_for(points):
    """Explicit planar support (origin, u, v) whose u x v follows the loop (outward) normal; no repair of the loop."""
    import numpy as np
    from anygeometry.surfaces import Plane
    p = np.asarray(points, dtype=float)
    normal = 0.5 * np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
    u = p[1] - p[0]
    for k in range(2, len(p)):
        v = p[k] - p[0]
        c = np.cross(u, v)
        if np.linalg.norm(c) > 1e-12 * max(1.0, float(np.abs(p).max())) ** 2:
            return Plane(p[0], u, v) if c @ normal > 0 else Plane(p[0], v, u)
    raise ValueError('envelope face has no independent plane vectors')


def _build_model(envelope):
    """Assemble the geometry-owner-validated INDEXED envelope (vertex identity given; no welding, rounding or reorientation)."""
    from anygeometry import GeometryModel, OrientedEdge
    g = GeometryModel()
    vid = [g.add_point(*[float(x) for x in xyz]) for xyz in envelope['vertices']]
    edge_lookup = {}
    for loop in envelope['faces']:
        ring = []
        for a, b in zip(loop, list(loop[1:]) + [loop[0]]):
            key = tuple(sorted((a, b)))
            eid = edge_lookup.get(key)
            if eid is None:
                eid = g.add_line(vid[a], vid[b])
                edge_lookup[key] = eid
            ring.append(OrientedEdge(eid, g.edges[eid].start == vid[a]))
        g.add_face_from_loop(tuple(ring), surface=_plane_for([envelope['vertices'][i] for i in loop]))
    return g


def run(spec):
    from anygeometry.serialization import to_dict
    from anygeometry.hydrostatics import hydrostatics
    from .floating_equilibrium_run import neutral_hull_bundle, solve_mean_equilibrium
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
    pose = solve_mean_equilibrium(bundle, mass_kg=spec['mass_kg'], cg_body_m=spec['cg_body_m'], owner_wheel=spec['owner_wheel'],
                                  rho=spec['rho'], gravity=spec['gravity'], datum_xy_m=tuple(spec.get('datum_xy_m', (0.0, 0.0))),
                                  initial_origin_z_m=-(zmin + fraction * height),
                                  origin_z_bounds_m=(-zmax - 0.25 * height, -zmin + 0.25 * height),
                                  controls=spec.get('controls'), allow_development=bool(spec.get('allow_development')))
    return pose.to_dict()


def _atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, allow_nan=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv):
    source, target = argv[0], argv[1]
    try:
        with open(source, 'r', encoding='utf-8') as stream:
            spec = json.load(stream)
        _atomic(target, dict(status='ok', pose=run(spec)))
        return 0
    except BaseException as error:        # structured refusal, never a partial pose
        code = getattr(error, 'code', None)
        _atomic(target, dict(status='error', type=type(error).__name__, code=str(code) if code else None, message=str(error)))
        return 1
