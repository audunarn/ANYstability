"""Owner-free engineering studies and globally bounded floating/GZ execution.

The geometry bridge is loaded only by execution. Historical source registration
is retained verbatim; a fresh runtime binding accompanies every new query.
"""
from dataclasses import dataclass
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import time

from .conventions import Pose, cross, generalized_rotation_forces
from .domain import LoadingCondition, MassItem
from .errors import ErrorCode, StabilityError
from .loading import aggregate_mass
from .validation import canonical_bytes, content_hash, integer, real, vector, invalid

SCHEMA = 'anystability-engineering-workflow-v1'
PIN = '4502e2292214a2217a666b4e67b4660eb89308676ba4ea06ece5664911d3e886'
_MAX_BYTES = 64 * 1024 * 1024


def _linked(path):
    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
        return True
    import stat
    try:
        return bool(getattr(path.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))
    except FileNotFoundError:
        return False


def decode_json(raw):
    if len(raw) > _MAX_BYTES:
        invalid('workflow JSON transport limit exceeded')
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value:
                invalid('duplicate workflow JSON key')
            value[key] = item
        return value
    def constant(value):
        invalid('nonfinite workflow JSON')
    try:
        result = json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
        canonical_bytes(result)
        return result
    except (UnicodeError,ValueError,RecursionError) as exc:
        raise StabilityError(ErrorCode.INPUT_INVALID,'invalid workflow JSON') from exc


def workflow_defaults(profile='preview'):
    if profile not in ('preview', 'full', 'equilibrium'):
        invalid('profile must be equilibrium, preview or full')
    full = profile == 'full'
    return dict(max_wall_seconds=600. if full else 90.,
        max_owner_queries=8192 if full else (512 if profile == 'equilibrium' else 1024),
        max_evaluations=512 if full else 48, max_points=241 if full else 5,
        max_iterations=6, max_backtracks=8, volume_tolerance_m3=1e-9,
        residual_tolerances=dict(force_N=1., heel_Nm=1., trim_Nm=1.),
        fd_steps=[.001, .0001, .0001], gz_tolerance_m=.001,
        area_tolerance_mrad=.001, angle_tolerance_rad=math.radians(.1),
        heels_rad=[math.radians(x) for x in (range(-60, 61, 5) if full else (-10, -5, 0, 5, 10))])


def _controls(profile, changes):
    c = workflow_defaults(profile)
    if changes:
        if not isinstance(changes, dict) or set(changes)-set(c):
            invalid('unknown workflow controls')
        c.update(changes)
    for key in ('max_owner_queries', 'max_evaluations', 'max_points', 'max_iterations', 'max_backtracks'):
        integer(c[key], key, 1, 100000)
    for key in ('max_wall_seconds', 'volume_tolerance_m3', 'gz_tolerance_m', 'area_tolerance_mrad', 'angle_tolerance_rad'):
        real(c[key], key, positive=True)
    if set(c['residual_tolerances']) != {'force_N', 'heel_Nm', 'trim_Nm'}:
        invalid('three dimensional residual tolerances required')
    for v in c['residual_tolerances'].values():
        real(v, 'residual tolerance', positive=True)
    if len(c['fd_steps']) != 3:
        invalid('three finite difference steps required')
    for v in c['fd_steps']:
        real(v, 'finite difference step', positive=True)
    return decode_json(canonical_bytes(c))


def _read(path):
    p = Path(path).absolute()
    if any(_linked(v) for v in (p, *p.parents)):
        invalid('symbolic-link study/source paths are refused')
    with p.open('rb') as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        invalid('workflow file exceeds bounded transport size')
    return raw


def _source(bundle):
    if isinstance(bundle, dict):
        return decode_json(canonical_bytes(bundle))
    root = Path(bundle)
    if root.is_file():
        return decode_json(_read(root))
    envelope = decode_json(_read(root / 'manifest.json'))
    manifest = envelope.get('manifest',envelope)
    if 'manifest' in envelope and envelope.get('integrity') != content_hash(manifest):
        raise StabilityError(ErrorCode.INTEGRITY_ERROR,'source manifest integrity mismatch')
    files = {}
    for name, digest in manifest['files'].items():
        if Path(name).name != name or '/' in name or '\\' in name:
            invalid('source member must be a simple filename')
        raw = _read(root / name)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'source file hash mismatch', member=name)
        if name.endswith('.json'):
            files[name] = decode_json(raw)
    return dict(manifest=manifest, files=files)


def _validate_study(d):
    if d.get('schema') != SCHEMA or d.get('kind') != 'engineering_study':
        invalid('unsupported engineering study schema')
    LoadingCondition.from_dict(d['base_condition'])
    p = d['initial_pose']; pose = Pose(p['heel_rad'], p['trim_rad'], p['origin_z_m'])
    bounds = d['pose_bounds']
    if len(bounds) != 3:
        invalid('pose bounds must be origin_z, heel, trim')
    for value, bound in zip((pose.origin_z_m, pose.heel_rad, pose.trim_rad), bounds):
        if len(bound) != 2 or not real(bound[0], 'lower bound') < real(bound[1], 'upper bound') or not bound[0] <= value <= bound[1]:
            invalid('initial pose outside ordered pose bounds')
    if not -math.pi/2 < bounds[2][0] < bounds[2][1] < math.pi/2:
        invalid('trim bounds must remain inside nonsingular chart')
    if d['geometry_mode'] not in ('engineering_estimate', 'certified_point'):
        invalid('geometry mode must be engineering_estimate or certified_point')
    if type(d['allow_development']) is not bool:
        invalid('allow_development must be bool')
    source = d['source']; manifest = source['manifest']; files = source['files']
    if not isinstance(source, dict) or len(files) > 128:
        invalid('bounded neutral source required')
    names = set(d['targets_m3'])
    if names != set(d['densities_kg_m3']) or not names <= {'WB'+str(i) for i in range(1, 9)}:
        invalid('liquid selection must be named WB1..WB8; pump and void are not liquids')
    definition = files['definition.json']
    for name, expected in manifest.get('files',{}).items():
        if name.endswith('.json') and name in files and content_hash(files[name]) != expected:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR,'neutral source identity mismatch',member=name)
    for name in {'HULL'} | names:
        full = manifest['capacity_comparisons'][name]
        real(full['volume_m3'], 'full volume', positive=True)
        vector(full['centroid_body_m'], 'full centroid')
        entry = definition['hull'] if name == 'HULL' else definition['spaces'][name]
        vertices = [p for face in entry['faces_body_m'] for p in face]
        if not 4 <= len(vertices) <= 100000:
            invalid('bounded source vertices required')
        for point in vertices:
            vector(point, 'source vertex')
        if name+'.geometry.json' not in files:
            invalid('neutral geometry snapshot required')
        if name != 'HULL':
            target = real(d['targets_m3'][name], 'contained volume', nonnegative=True)
            if target > full['volume_m3']:
                invalid('contained volume exceeds source capacity')
            real(d['densities_kg_m3'][name], 'liquid density', positive=True)
    base = LoadingCondition.from_dict(d['base_condition'])
    covers = {'tank:'+name+':liquid' for name in names}
    if any(covers.intersection(item.covers) for item in base.items):
        invalid('base condition already covers a selected tank liquid')
    seen = set()
    for opening in d['openings']:
        if set(opening) != {'name', 'point_body_m', 'closing_status', 'limits_intact'}:
            invalid('opening requires name, point_body_m, closing_status, limits_intact')
        if not isinstance(opening['name'], str) or not opening['name'] or opening['name'] in seen:
            invalid('opening names must be nonempty and unique')
        seen.add(opening['name']); vector(opening['point_body_m'], 'opening point')
        if opening['closing_status'] not in ('open', 'closed', 'unknown') or type(opening['limits_intact']) is not bool:
            invalid('opening closing_status must be open, closed or unknown')
    if not isinstance(d['owner_wheel'], str) or not d['owner_wheel']:
        invalid('explicit owner wheel path required')


@dataclass(frozen=True)
class EngineeringStudy:
    _bytes: bytes

    def __post_init__(self):
        try:
            d = decode_json(self._bytes); _validate_study(d)
            if canonical_bytes(d) != self._bytes:
                invalid('study must use immutable canonical bytes')
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise StabilityError(ErrorCode.INPUT_INVALID, 'invalid engineering study') from exc
        object.__setattr__(self,'_identity',hashlib.sha256(self._bytes).hexdigest())

    @property
    def identity(self):
        return self._identity

    def to_dict(self):
        return decode_json(self._bytes)

    @classmethod
    def from_dict(cls, data):
        return cls(canonical_bytes(data))


def create_stability_study(source_bundle, *, base_condition, targets_m3, densities_kg_m3,
        initial_pose, pose_bounds, owner_wheel, geometry_mode='engineering_estimate',
        openings=(), allow_development=False):
    if not isinstance(base_condition, LoadingCondition) or not isinstance(initial_pose, Pose):
        invalid('typed LoadingCondition and Pose required')
    d = dict(schema=SCHEMA, kind='engineering_study', source=_source(source_bundle),
        base_condition=base_condition.to_dict(), targets_m3=dict(targets_m3),
        densities_kg_m3=dict(densities_kg_m3), initial_pose=initial_pose.to_dict(),
        pose_bounds=[list(b) for b in pose_bounds], owner_wheel=str(owner_wheel),
        geometry_mode=geometry_mode, openings=list(openings), allow_development=allow_development)
    return EngineeringStudy(canonical_bytes(d))


@dataclass(frozen=True)
class EngineeringResult:
    _bytes: bytes

    def __post_init__(self):
        try:
            d = decode_json(self._bytes)
            if canonical_bytes(d) != self._bytes or d['schema'] != SCHEMA or d['status'] not in ('complete', 'partial', 'cancelled', 'unresolved', 'refused'):
                invalid('invalid engineering result')
            if d['identity'] != content_hash({k:v for k,v in d.items() if k != 'identity'}):
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'engineering result identity mismatch')
            if d['request_identity'] != content_hash(d['request']):
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'engineering request identity mismatch')
            if d['study_identity'] != d['request']['study_identity']:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'result study/request binding mismatch')
            work=d['work']; queries=work['queries']; evaluations=work['evaluations']
            if (work['attempted_owner_queries']!=len(queries) or
                    work['completed_owner_queries']!=sum(q['sample'] is not None for q in queries) or
                    work['evaluation_count']!=len(evaluations) or
                    work['accepted_point_count']!=len(d['points'])):
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'result work journal count mismatch')
            if work['limits']!=d['request']['controls']:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'result work limits mismatch')
            for q in queries:
                if q['identity']!=content_hash(q['query']):
                    raise StabilityError(ErrorCode.INTEGRITY_ERROR,'retained query identity mismatch')
            states={content_hash(e['state']) for e in evaluations if e['state'] is not None}
            if d['equilibrium'] is not None and content_hash(d['equilibrium']) not in states:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'equilibrium missing from evaluation journal')
            for point in d['points']:
                if point['identity'] != content_hash({k:v for k,v in point.items() if k != 'identity'}):
                    raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'accepted point identity mismatch')
                if content_hash({k:v for k,v in point.items() if k not in ('identity','branch')}) not in states:
                    raise StabilityError(ErrorCode.INTEGRITY_ERROR,'accepted point missing from evaluation journal')
            ids={p['identity'] for p in d['points']}
            if any(not set(b['point_identities'])<=ids for b in d['branches'].values()):
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'branch references an unavailable accepted point')
            if d['assurance']['production_qualified'] is not False:
                invalid('engineering result cannot confer production qualification')
        except (KeyError, TypeError, ValueError) as exc:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'invalid engineering result structure') from exc
        object.__setattr__(self,'_identity',d['identity'])

    @property
    def identity(self):
        return self._identity

    def to_dict(self):
        return decode_json(self._bytes)

    @classmethod
    def from_dict(cls, data):
        return cls(canonical_bytes(data))


def _result(d):
    d['identity'] = content_hash({k:v for k,v in d.items() if k != 'identity'})
    return EngineeringResult(canonical_bytes(d))


class _OwnerProvider:
    """One fresh authenticated execution; no source-version rebinding."""
    def __init__(self, spec, poll, deadline):
        self.spec = spec; self.poll = poll; self.models = {}; self.runtime = None; self.deadline = deadline

    def query(self, name, pose, offset, query_identity):
        from .providers.certified import authenticate_installed_owner
        self.poll()
        runtime = self.runtime or authenticate_installed_owner(self.spec['owner_wheel'])
        if runtime['wheel_sha256'] != PIN or runtime['version'] != '0.4.8':
            raise StabilityError(ErrorCode.SOURCE_STALE, 'workflow requires pinned ANYgeometry0.4.8')
        if self.runtime is not None and runtime != self.runtime:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, 'runtime owner changed during execution')
        self.runtime = runtime
        source = self.spec['source']; document = source['files'][name+'.geometry.json']
        normal = pose.rotation[2]; longitudinal = pose.rotation[0]
        if self.spec['geometry_mode'] == 'certified_point':
            from .providers.certified import certified_point
            from .providers.integrals import IntegralRequest, PlaneFrame
            from .providers.protocol import HalfSpace
            # Face selection comes from the neutral serialized model, not a kernel.
            from anygeometry.serialization import from_dict
            model = from_dict(document)
            frame = PlaneFrame(tuple(v*offset for v in normal), longitudinal, pose.rotation[1])
            record = certified_point(document, list(model.faces),
                IntegralRequest(query_identity, HalfSpace(normal, offset)), frame,
                wheel=self.spec['owner_wheel'], cancellation_check=lambda: (self.poll() or False), deadline=self.deadline)
            sample = record['payload']['sample']; volume = sample['volume_m3']['value']
            first = [q['value'] for q in sample['first_moments_m4']]
            section=sample['waterplane']; area=None; inertia=None
            if section:
                if section.get('convention')!='raw_u2_v2_uv':
                    raise StabilityError(ErrorCode.INTEGRITY_ERROR,'certified section moment ordering differs from consumer contract')
                area=section['area_m2']['value']
                if area>0:
                    inertia=section['second_m4'][1]['value']-section['first_m3'][1]['value']**2/area
            return dict(volume_m3=volume, cg_body_m=None if volume == 0 else [v/volume for v in first],
                assurance='owner_certified_point', owner_record=record, runtime=runtime,
                waterplane_area_m2=area,i_transverse_m4=inertia)
        from anygeometry.serialization import from_dict
        from anygeometry.hydrostatics import hydrostatics
        from anygeometry.errors import GeometryError
        try:
            if name not in self.models:
                self.models[name] = from_dict(document)
            model = self.models[name]
            answer = hydrostatics(model, list(model.faces), point=tuple(v*offset for v in normal),
                normal=normal, longitudinal=longitudinal, order=2, rtol=1e-8)
        except GeometryError as exc:
            raise StabilityError(ErrorCode.QUERY_DEGENERATE, 'geometry owner refused exact query',
                original_cause=dict(type=type(exc).__name__, message=str(exc))) from exc
        self.poll()
        try:
            volume = real(answer['volume'], 'owner displaced volume', nonnegative=True)
            cg = list(vector(list(answer['buoyancy_centre']), 'owner centroid')) if volume else None
            axes = [list(row) for row in answer['frame'].axes]
            if len(axes) != 3 or any(abs(a-b) > 1e-12 for row, expected in zip(axes, pose.rotation) for a,b in zip(row, expected)):
                invalid('owner returned a different frame')
            return dict(volume_m3=volume, cg_body_m=cg, assurance='owner_estimate_not_quantity_bound',
                estimate=real(answer['estimate'], 'owner estimate', nonnegative=True), runtime=runtime,
                waterplane_area_m2=real(answer['waterplane_area'], 'waterplane area', nonnegative=True),
                i_transverse_m4=real(answer['i_transverse'], 'waterplane inertia', nonnegative=True))
        except StabilityError as exc:
            if exc.code!=ErrorCode.INPUT_INVALID:
                raise
            raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED,'owner response failed plausibility/frame validation',original_cause=exc.to_dict()) from exc
        except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as exc:
            raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED,'owner response has invalid shape',original_cause=dict(type=type(exc).__name__,message=str(exc))) from exc

    def finish(self):
        if self.runtime is not None:
            from .providers.certified import authenticate_installed_owner
            if authenticate_installed_owner(self.spec['owner_wheel']) != self.runtime:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR,'runtime owner changed during workflow')


def _linear(matrix, rhs):
    """Pivoted, row-scaled elimination extracted from reference.coupled._linear."""
    size = len(rhs); rows = []
    for row, value in zip(matrix, rhs):
        scale = max(abs(v) for v in row)
        if not scale:
            raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, 'singular residual Jacobian')
        rows.append([v/scale for v in row]+[value/scale])
    for col in range(size):
        pivot = max(range(col, size), key=lambda r:abs(rows[r][col]))
        if abs(rows[pivot][col]) <= 64*math.ulp(1.):
            raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, 'numerically singular residual Jacobian')
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]; rows[col] = [v/divisor for v in rows[col]]
        for row in range(size):
            if row != col:
                factor = rows[row][col]
                rows[row] = [real(x-factor*y, 'Newton elimination') for x,y in zip(rows[row], rows[col])]
    return [row[-1] for row in rows]


class _Execution:
    def __init__(self, study, request, cancel, progress, start=None):
        self.start = time.monotonic() if start is None else start
        self.study = study; self.spec = study.to_dict(); self.c = request['controls']
        self.cancel = cancel; self.progress = progress
        self.cache = {}; self.queries = []; self.evaluations = []; self.pending = None
        self.source_identity=content_hash(self.spec['source'])
        self.finalization_reserve=min(2.,.1*self.c['max_wall_seconds'])
        self.provider = _OwnerProvider(self.spec, self.poll,self.start+self.c['max_wall_seconds']-self.finalization_reserve)
        self.snapshot = None

    def poll(self):
        if self.cancel is not None:
            value = self.cancel()
            if type(value) is not bool:
                invalid('cancellation_check must return bool')
            if value:
                raise StabilityError(ErrorCode.CANCELLED, 'engineering calculation cancelled')
        if time.monotonic()-self.start >= self.c['max_wall_seconds']-self.finalization_reserve:
            raise StabilityError(ErrorCode.DEADLINE_EXCEEDED, 'workflow computation deadline reached; remaining wall reserved for final authentication/publication')

    def notify(self, phase, heel=None, accepted=None):
        if self.progress:
            d = dict(phase=phase, heel_rad=heel, query_count=len(self.queries), evaluation_count=len(self.evaluations))
            if accepted is not None:
                d['accepted_state'] = accepted
                if self.snapshot is not None:
                    d['result'] = self.snapshot()
            try:
                self.progress(decode_json(canonical_bytes(d)))
            except Exception as exc:
                raise StabilityError(ErrorCode.IO_ERROR,'progress publication failed',original_cause=dict(type=type(exc).__name__,message=str(exc))) from exc

    def vertices(self, name):
        definition = self.spec['source']['files']['definition.json']
        entry = definition['hull'] if name == 'HULL' else definition['spaces'][name]
        return [p for face in entry['faces_body_m'] for p in face]

    def query(self, name, pose, offset):
        self.poll()
        query = dict(component=name, normal=list(pose.rotation[2]), offset_m=offset,
            longitudinal=list(pose.rotation[0]), source_identity=self.source_identity,
            geometry_mode=self.spec['geometry_mode'], accuracy=dict(order=2, rtol=1e-8))
        identity = content_hash(query); self.pending = dict(query=query, identity=identity)
        if len(self.queries) >= self.c['max_owner_queries']:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, 'global owner query cap exhausted')
        row = dict(query=query, identity=identity, sample=None, failure=None)
        self.queries.append(row)
        try:
            self.notify('geometry_query', pose.heel_rad)
            answer = self.provider.query(name, pose, offset, identity)
            self.poll()
        except StabilityError as exc:
            row['failure']=exc.to_dict(); raise
        try:
            v = real(answer['volume_m3'], 'sample volume', nonnegative=True)
            full = self.spec['source']['manifest']['capacity_comparisons'][name]['volume_m3']
            if v > full + max(64*math.ulp(max(1., full)),self.c['volume_tolerance_m3']):
                invalid('owner volume exceeds full source capacity')
            if v:
                cg = vector(answer['cg_body_m'], 'sample centroid')
                vertices = self.vertices(name)
                for axis in range(3):
                    lo = min(p[axis] for p in vertices); hi = max(p[axis] for p in vertices)
                    slack = 64*math.ulp(max(1., abs(lo), abs(hi)))
                    if not lo-slack <= cg[axis] <= hi+slack:
                        invalid('owner centroid outside source bounds')
                projection = sum(a*b for a,b in zip(pose.rotation[2], cg))
                if projection > offset + 64*math.ulp(max(1.,abs(offset),abs(projection))):
                    invalid('owner liquid centroid above exact liquid plane')
            row['sample'] = answer
        except StabilityError as exc:
            if exc.code==ErrorCode.INPUT_INVALID:
                original=exc
                exc=StabilityError(ErrorCode.ACCURACY_UNRESOLVED,'owner response failed plausibility validation',original_cause=original.to_dict())
                row['failure']=exc.to_dict()
                raise exc from original
            row['failure'] = exc.to_dict(); raise
        except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as original:
            exc=StabilityError(ErrorCode.ACCURACY_UNRESOLVED,'owner response has invalid shape',original_cause=dict(type=type(original).__name__,message=str(original)))
            row['failure']=exc.to_dict(); raise exc from original
        try:
            self.poll()
        except StabilityError as exc:
            row['failure']=exc.to_dict(); raise
        self.pending=None
        return answer

    def tank(self, name, pose):
        target = self.spec['targets_m3'][name]
        full = self.spec['source']['manifest']['capacity_comparisons'][name]
        if target == 0:
            return dict(target_volume_m3=0., achieved_volume_m3=0., residual_volume_m3=0.,
                cg_body_m=None, state='empty', assurance='empty_definition', query_identities=[])
        key = content_hash(dict(source=self.source_identity, name=name,
            normal=pose.rotation[2], target=target, tolerance=self.c['volume_tolerance_m3'],
            mode=self.spec['geometry_mode']))
        if key in self.cache:
            return decode_json(canonical_bytes(self.cache[key]))
        vertices = self.vertices(name)
        projections = [sum(a*b for a,b in zip(pose.rotation[2], p)) for p in vertices]
        lo, hi = min(projections), max(projections)
        # Full liquid is queried just beyond the authored projection bound; this
        # is an explicit full-solid query, never an event-repair nudge.
        if target == full['volume_m3']:
            answer = self.query(name, pose, hi + max(1., hi-lo))
            if abs(answer['volume_m3']-target) > self.c['volume_tolerance_m3']:
                raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, 'fresh full tank capacity differs from target')
            ids = [self.queries[-1]['identity']]
        else:
            vlo, vhi = 0., full['volume_m3']; ids = []
            next_offset = lo+(hi-lo)/2
            while True:
                offset = next_offset
                if offset in (lo, hi):
                    raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, 'liquid volume bracket collapsed')
                answer = self.query(name, pose, offset); ids.append(self.queries[-1]['identity'])
                v = answer['volume_m3']
                if not vlo < v < vhi:
                    raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, 'owner liquid volume violates monotone bracket')
                if abs(v-target) <= self.c['volume_tolerance_m3']:
                    break
                if v < target:
                    lo, vlo = offset, v
                else:
                    hi, vhi = offset, v
                # Safeguarded volume inversion uses the owner's exact requested
                # section derivative A=dV/dd; bisection remains the fallback.
                area=answer.get('waterplane_area_m2')
                proposal=offset+(target-v)/area if area is not None and area>0 else lo+(target-vlo)*(hi-lo)/(vhi-vlo)
                margin=1e-6*(hi-lo)
                next_offset=proposal if lo+margin<proposal<hi-margin else lo+(hi-lo)/2
        result = dict(target_volume_m3=target, achieved_volume_m3=answer['volume_m3'],
            residual_volume_m3=answer['volume_m3']-target, cg_body_m=answer['cg_body_m'],
            state='full' if target == full['volume_m3'] else 'partial',
            assurance=answer['assurance'], query_identities=ids)
        self.cache[key] = result
        return decode_json(canonical_bytes(result))

    def evaluate(self, q, purpose):
        self.poll()
        if len(self.evaluations) >= self.c['max_evaluations']:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, 'global pose evaluation cap exhausted')
        if any(not lo <= value <= hi for value,(lo,hi) in zip(q,self.spec['pose_bounds'])):
            raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, 'trial pose outside search box')
        pose = Pose(q[1], q[2], q[0]); row = dict(pose=pose.to_dict(), purpose=purpose, state=None)
        self.evaluations.append(row); self.notify(purpose, pose.heel_rad)
        base = LoadingCondition.from_dict(self.spec['base_condition']); items = list(base.items); tanks = {}
        for name in sorted(self.spec['targets_m3']):
            tank = self.tank(name, pose); tanks[name] = tank
            target = self.spec['targets_m3'][name]
            if target:
                items.append(MassItem('workflow-liquid-'+name, target*self.spec['densities_kg_m3'][name],
                    tuple(tank['cg_body_m']), 'actual_liquid_CG', ('tank:'+name+':liquid',)))
        condition = LoadingCondition(base.condition_id, base.name, tuple(items), base.water_density_kg_m3, base.gravity_m_s2)
        summary = aggregate_mass(condition)
        hull = self.query('HULL', pose, -pose.origin_z_m)
        if hull['volume_m3'] <= 0:
            raise StabilityError(ErrorCode.NO_ROOT_IN_SEARCH_DOMAIN, 'hull has no immersed volume')
        weight = summary.mass_kg*base.gravity_m_s2
        buoyancy = hull['volume_m3']*base.water_density_kg_m3*base.gravity_m_s2
        cb = hull['cg_body_m']; cg = summary.cg_body_m
        bm = cross(pose.rotate(cb), (0.,0.,buoyancy)); wm = cross(pose.rotate(cg), (0.,0.,-weight))
        torque = [a+b for a,b in zip(bm,wm)]; qheel,qtrim = generalized_rotation_forces(pose,torque)
        # Horizontal separation is independent of vertical residual; physical
        # total torque and generalized reaction are retained separately.
        gz = pose.rotate(cg)[1]-pose.rotate(cb)[1]
        hydro_gm=None
        if hull.get('i_transverse_m4') is not None:
            # This is the local frozen-liquid transverse hydrostatic formula,
            # separate from the effective moving-liquid GZ slope.
            hydro_gm=hull['i_transverse_m4']/hull['volume_m3']+pose.rotate(cb)[2]-pose.rotate(cg)[2]
        openings = []
        for opening in self.spec['openings']:
            height = pose.origin_z_m+pose.rotate(opening['point_body_m'])[2]
            openings.append(dict(**opening, height_above_water_m=height, immersed=height <= 0))
        state = dict(heel_rad=pose.heel_rad, trim_rad=pose.trim_rad, origin_z_m=pose.origin_z_m,
            mass_kg=summary.mass_kg, cg_body_m=list(cg), cb_body_m=cb, gz_m=gz,
            righting_moment_Nm=-torque[0], generalized_Qheel_Nm=qheel,
            vertical_residual_N=buoyancy-weight, trim_residual_Nm=qtrim,
            physical_torque_world_Nm=torque, tanks=tanks, openings=openings,
            free_surface_treatment='actual_CG_only_no_added_FSM',
            geometry_assurance=hull['assurance'], hull_query_identity=self.queries[-1]['identity'],
            hydrostatic_GM_m=hydro_gm, hydrostatic_GM_reason=None if hydro_gm is not None else 'owner section inertia unavailable',
            hydrostatic_GM_definition='local_world_transverse_frozen_liquid_CBz_plus_Ix_over_V_minus_CGz')
        row['state'] = state
        return state

    def solve(self, q, axes, purpose):
        residual_keys = ['vertical_residual_N', 'generalized_Qheel_Nm', 'trim_residual_Nm']
        tolerances = [self.c['residual_tolerances'][k] for k in ('force_N','heel_Nm','trim_Nm')]
        def norm(state):
            return max(abs(state[residual_keys[i]])/tolerances[i] for i in axes)
        state = self.evaluate(q, purpose)
        for iteration in range(self.c['max_iterations']+1):
            if norm(state) <= 1:
                state['convergence'] = dict(converged=True, iterations=iteration,
                    accepted_residuals={residual_keys[i]:state[residual_keys[i]] for i in axes},
                    residual_tolerances=self.c['residual_tolerances'])
                return state
            if iteration == self.c['max_iterations']:
                break
            columns = []
            for axis in axes:
                step = self.c['fd_steps'][axis]; trial = list(q)
                if trial[axis]+step > self.spec['pose_bounds'][axis][1]:
                    step = -step
                if not self.spec['pose_bounds'][axis][0]<=trial[axis]+step<=self.spec['pose_bounds'][axis][1]:
                    raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED,'finite-difference step fits neither side of pose bounds')
                trial[axis] += step
                probe = self.evaluate(trial, 'finite_difference')
                columns.append([(probe[residual_keys[i]]-state[residual_keys[i]])/step for i in axes])
            matrix = [[columns[col][row] for col in range(len(axes))] for row in range(len(axes))]
            delta = _linear(matrix, [-state[residual_keys[i]] for i in axes])
            accepted = False
            for backtrack in range(self.c['max_backtracks']):
                trial = list(q)
                for axis, step in zip(axes, delta):
                    trial[axis] += step*(.5**backtrack)
                if any(not lo <= value <= hi for value,(lo,hi) in zip(trial,self.spec['pose_bounds'])):
                    continue
                candidate = self.evaluate(trial, 'backtrack')
                if norm(candidate) < norm(state):
                    q, state, accepted = trial, candidate, True; break
            if not accepted:
                raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, 'bounded Newton search found no improving trial')
        raise StabilityError(ErrorCode.EQUILIBRIUM_UNRESOLVED, 'bounded Newton iteration cap exhausted')


def _point(state, branch):
    p = dict(state, branch=branch)
    p['identity'] = content_hash(p)
    return p


def _failure(exc, phase, branch=None, heel=None):
    d = dict(phase=phase, branch=branch, heel_rad=heel, error=exc.to_dict())
    if exc.__cause__ is not None:
        d['original_cause'] = dict(type=type(exc.__cause__).__name__, message=str(exc.__cause__))
    return d


def _run(study, *, curve, mode='free_trim', fixed_trim_rad=None, profile='equilibrium',
        heels_rad=None, controls=None, cancellation_check=None, progress=None, seed_result=None,
        execution_started_monotonic=None):
    started=time.monotonic()
    if execution_started_monotonic is not None:
        anchor=real(execution_started_monotonic,'execution_started_monotonic',nonnegative=True)
        if anchor>started:
            invalid('execution_started_monotonic must be in the past')
        started=anchor
    if not isinstance(study, EngineeringStudy):
        invalid('typed EngineeringStudy required')
    if mode not in ('free_trim', 'fixed_trim'):
        invalid('GZ mode must be free_trim or fixed_trim')
    c = _controls(profile, controls); spec = study.to_dict()
    schedule=c['heels_rad'] if heels_rad is None else heels_rad
    if curve and heels_rad is None and profile=='preview':
        schedule=[v for v in schedule if v!=0.]
    heels = sorted(set(real(v,'heel') for v in schedule)) if curve else []
    if curve and not heels:
        invalid('GZ requires a nonempty heel schedule')
    if any(not spec['pose_bounds'][1][0] <= v <= spec['pose_bounds'][1][1] for v in heels):
        invalid('requested heels outside study bounds')
    if fixed_trim_rad is not None:
        real(fixed_trim_rad, 'fixed trim')
        if not spec['pose_bounds'][2][0] <= fixed_trim_rad <= spec['pose_bounds'][2][1]:
            invalid('fixed trim outside study bounds')
    request = dict(study_identity=study.identity, calculation='gz_curve' if curve else 'floating_equilibrium',
        mode=mode, fixed_trim_rad=fixed_trim_rad, profile=profile, heels_rad=heels, controls=c)
    d = dict(schema=SCHEMA, kind=request['calculation'], status='unresolved', study_identity=study.identity,
        request_identity=content_hash(request), request=request,
        assurance=dict(geometry='unavailable', numerics='engineering_estimate', continuous_curve='not_certified',
            criteria='not_evaluated', approval='none', production_qualified=False),
        equilibrium=None, points=[], branches={}, metrics={}, work={}, failures=[], pending=None)
    ex = _Execution(study, request, cancellation_check, progress,started)
    global_error=None
    def snapshot():
        saved=dict(d,status='partial',work=dict(elapsed_wall_seconds=time.monotonic()-ex.start,
            attempted_owner_queries=len(ex.queries),completed_owner_queries=sum(q['sample'] is not None for q in ex.queries),
            evaluation_count=len(ex.evaluations),accepted_point_count=len(d['points']),limits=c,
            queries=ex.queries,evaluations=ex.evaluations,resumable=False,
            resume_reason='accepted_checkpoint_does_not_include_post_checkpoint_work'),pending=ex.pending)
        saved['metrics']=_metrics(saved)
        return _result(saved).to_dict()
    ex.snapshot=snapshot
    try:
        if not spec['allow_development']:
            raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED, 'engineering workflow requires explicit development opt-in')
        # Resume is deliberately bounded by retained work; changed requests may
        # use a previous accepted equilibrium only as a numerical initial guess.
        p = spec['initial_pose']; q = [p['origin_z_m'],p['heel_rad'],p['trim_rad']]
        resumed=False
        if seed_result is not None:
            if not isinstance(seed_result, EngineeringResult) or seed_result.to_dict()['study_identity'] != study.identity:
                invalid('seed result does not belong to immutable study')
            seed = seed_result.to_dict()
            if seed['work'].get('resumable') is not True:
                raise StabilityError(ErrorCode.CAPABILITY_UNSUPPORTED,'accepted progress checkpoints cannot resume after an unaccounted hard kill')
            if seed['request_identity'] == d['request_identity']:
                if seed['status'] == 'complete':
                    return seed_result
                oldwork=seed['work']; resumed=True
                ex.start-=oldwork['elapsed_wall_seconds']
                ex.provider.deadline=ex.start+c['max_wall_seconds']-ex.finalization_reserve
                ex.queries=list(oldwork['queries']); ex.evaluations=list(oldwork['evaluations'])
                d['equilibrium']=seed['equilibrium']; d['points']=list(seed['points'])
                d['failures']=list(seed['failures'])
                d['assurance']['resumed_from_result_identity']=seed_result.identity
            if seed['equilibrium']:
                eq = seed['equilibrium']; q = [eq['origin_z_m'],eq['heel_rad'],eq['trim_rad']]
        equilibrium = d['equilibrium'] if resumed and d['equilibrium'] else ex.solve(q, (0,1,2), 'initial_equilibrium')
        d['equilibrium'] = equilibrium; ex.notify('accepted_equilibrium', equilibrium['heel_rad'], equilibrium)
        if not curve:
            d['status'] = 'complete'
        else:
            eqheel = equilibrium['heel_rad']; eqtrim = equilibrium['trim_rad']
            fixed = eqtrim if fixed_trim_rad is None else fixed_trim_rad
            axes = (0,2) if mode == 'free_trim' else (0,)
            # Each branch starts afresh at the accepted equilibrium. No failed
            # branch may seed the other branch or bridge an unavailable interval.
            curve_origin=equilibrium
            if mode=='fixed_trim' and fixed!=eqtrim:
                curve_origin=ex.solve([equilibrium['origin_z_m'],eqheel,fixed],(0,),'fixed_trim_origin')
            origin = _point(curve_origin, 'equilibrium')
            if not any(p['identity']==origin['identity'] for p in d['points']):
                d['points'].append(origin)
            for name, sign in (('negative',-1),('positive',1)):
                targets = sorted([h for h in heels if (h-eqheel)*sign > 1e-12], key=lambda h:abs(h-eqheel))
                branch = dict(status='complete', point_identities=[origin['identity']], failure=None,
                    intervals=[], intact_limit=None, requested_heels_rad=targets)
                d['branches'][name] = branch; previous = curve_origin
                initial_immersed=[o for o in curve_origin['openings'] if o['limits_intact'] and o['closing_status']!='closed' and o['immersed']]
                if initial_immersed:
                    branch['status']='intact_limit'
                    branch['intact_limit']=dict(heel_rad=curve_origin['heel_rad'],
                        openings=[o['name'] for o in initial_immersed],
                        resolution='initially_immersed',angle_uncertainty_rad=0.)
                    continue
                for heel in targets:
                    try:
                        existing=next((p for p in d['points'] if p['branch']==name and p['heel_rad']==heel),None)
                        if existing is not None:
                            branch['point_identities'].append(existing['identity'])
                            branch['intervals'].append(dict(from_heel_rad=previous['heel_rad'],to_heel_rad=heel,
                                status='sampled_unresolved',gz_error_estimate_m=None,area_error_estimate_mrad=None))
                            previous=existing
                            continue
                        if len(d['points']) >= c['max_points']:
                            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, 'global accepted point cap exhausted')
                        q = [previous['origin_z_m'], heel, previous['trim_rad'] if mode == 'free_trim' else fixed]
                        state = ex.solve(q, axes, 'gz_'+name)
                        point = _point(state,name); d['points'].append(point); branch['point_identities'].append(point['identity'])
                        branch['intervals'].append(dict(from_heel_rad=previous['heel_rad'], to_heel_rad=heel,
                            status='sampled_unresolved', gz_error_estimate_m=None, area_error_estimate_mrad=None))
                        ex.notify('accepted_point',heel,point); previous = state
                        marked = [o for o in state['openings'] if o['limits_intact'] and o['closing_status'] != 'closed' and o['immersed']]
                        if marked:
                            branch['status'] = 'intact_limit'; branch['intact_limit'] = dict(heel_rad=heel, openings=[o['name'] for o in marked],
                                resolution='sample_bracket_only', angle_uncertainty_rad=abs(branch['intervals'][-1]['to_heel_rad']-branch['intervals'][-1]['from_heel_rad']))
                            break
                    except StabilityError as exc:
                        failure = _failure(exc,'gz_branch',name,heel); d['failures'].append(failure)
                        branch['status'] = 'partial'; branch['failure'] = failure
                        if exc.code in (ErrorCode.CANCELLED,ErrorCode.DEADLINE_EXCEEDED,ErrorCode.WORK_BUDGET_EXCEEDED,ErrorCode.INTEGRITY_ERROR,ErrorCode.SOURCE_STALE):
                            raise
                        break
            _refine(ex,d,mode,fixed,c)
            all_resolved=all((bool(b['intervals']) or b['status']=='intact_limit') and all(i['status']=='engineering_estimate_resolved' for i in b['intervals']) for b in d['branches'].values())
            d['status'] = 'complete' if all_resolved and all(b['status'] in ('complete','intact_limit') for b in d['branches'].values()) else 'partial'
            if d['branches'] and all(b['intact_limit'] and b['intact_limit']['resolution']=='initially_immersed' for b in d['branches'].values()):
                d['assurance']['completion_scope']='origin_intact_limit_only_no_intact_curve_interval'
    except StabilityError as exc:
        if exc.code==ErrorCode.INPUT_INVALID:
            raise
        if exc.code in (ErrorCode.INTEGRITY_ERROR,ErrorCode.SOURCE_STALE):
            global_error=exc
        if not d['failures'] or d['failures'][-1]['error'] != exc.to_dict():
            d['failures'].append(_failure(exc,'workflow'))
        d['status'] = 'cancelled' if exc.code == ErrorCode.CANCELLED else ('partial' if d['equilibrium'] else ('unresolved' if exc.code in (ErrorCode.EQUILIBRIUM_UNRESOLVED,ErrorCode.ACCURACY_UNRESOLVED,ErrorCode.WORK_BUDGET_EXCEEDED,ErrorCode.DEADLINE_EXCEEDED) else 'refused'))
    finally:
        if hasattr(ex.provider,'finish'):
            try:
                ex.provider.finish()
                d['assurance']['final_runtime_authentication']='completed'
            except StabilityError as exc:
                d['failures'].append(_failure(exc,'final_runtime_authentication'))
                d['assurance']['final_runtime_authentication']='failed'
                d['status']='partial' if d['equilibrium'] else 'refused'
                if global_error is None:
                    global_error=exc
        if time.monotonic()-ex.start>=c['max_wall_seconds']:
            deadline=StabilityError(ErrorCode.DEADLINE_EXCEEDED,'global wall limit exhausted including final runtime authentication')
            if not any(f['error']['code']==ErrorCode.DEADLINE_EXCEEDED.value for f in d['failures']):
                d['failures'].append(_failure(deadline,'finalization'))
            if d['status']!='cancelled':
                d['status']='partial' if d['equilibrium'] else 'unresolved'
        d['pending'] = ex.pending
        d['work'] = dict(elapsed_wall_seconds=time.monotonic()-ex.start,
            attempted_owner_queries=len(ex.queries), completed_owner_queries=sum(q['sample'] is not None for q in ex.queries),
            evaluation_count=len(ex.evaluations), accepted_point_count=len(d['points']),
            limits=c, queries=ex.queries, evaluations=ex.evaluations)
        d['work']['resumable']=global_error is None
        d['work']['finalization_reserve_seconds']=ex.finalization_reserve
    assurances = {q['sample']['assurance'] for q in ex.queries if q['sample'] is not None}
    d['assurance']['geometry'] = 'owner_certified_points' if assurances == {'owner_certified_point'} else ('engineering_estimate' if assurances else 'unavailable')
    d['assurance']['historical_source'] = 'preserved_not_reauthenticated'
    d['metrics'] = _metrics(d)
    result=_result(d)
    if global_error is not None:
        d['assurance']['quarantined']=True
        result=_result(d)
        global_error.evidence=result
        raise global_error
    return result


def _accepted_root(point, equilibrium):
    """Identify the retained full-equilibrium state, without rounding its GZ."""
    if not equilibrium:
        return False
    convergence = equilibrium.get('convergence', {})
    if convergence.get('converged') is not True or not {
            'vertical_residual_N', 'generalized_Qheel_Nm', 'trim_residual_Nm'
            } <= set(convergence.get('accepted_residuals', {})):
        return False
    return {k:v for k,v in point.items() if k not in ('identity','branch')} == equilibrium


def _distinct_zero_crossing(a, b, equilibrium):
    return (not _accepted_root(a, equilibrium) and not _accepted_root(b, equilibrium)
            and a['gz_m']*b['gz_m'] < 0)


def _refine(ex,d,mode,fixed,c):
    """Midpoint comparison supplies engineering error estimates, never bounds."""
    for name,branch in d['branches'].items():
        if branch['status'] == 'partial':
            continue
        points = {p['identity']:p for p in d['points']}
        ids = branch['point_identities']; initial = [points[i] for i in ids]
        queue = [(a,b) for a,b in zip(initial,initial[1:])]
        intervals = []
        while queue:
            a,b = queue.pop(0); width = abs(b['heel_rad']-a['heel_rad'])
            midpoint = (a['heel_rad']+b['heel_rad'])/2
            origin = next((p for p in (a,b) if _accepted_root(p,d['equilibrium'])),None)
            origin_probe = False
            if origin is not None:
                other=b if origin is a else a
                probe=origin['heel_rad']+math.copysign(c['angle_tolerance_rad'],other['heel_rad']-origin['heel_rad'])
                if min(a['heel_rad'],b['heel_rad']) < probe < max(a['heel_rad'],b['heel_rad']):
                    # Establish a separate, budgeted sample at the existing
                    # angular resolution. A distinct crossing before the old
                    # midpoint must not disappear with the baseline residual.
                    midpoint=probe;origin_probe=True
            existing=next((p for p in d['points'] if p['branch']==name and p['heel_rad']==midpoint),None)
            if len(d['points']) >= c['max_points'] and existing is None:
                intervals.append(dict(from_heel_rad=a['heel_rad'],to_heel_rad=b['heel_rad'],status='unresolved_point_budget',
                    gz_error_estimate_m=None,area_error_estimate_mrad=None)); continue
            try:
                state = existing or ex.solve([origin['origin_z_m'] if origin_probe else (a['origin_z_m']+b['origin_z_m'])/2,midpoint,
                    (origin['trim_rad'] if origin_probe else (a['trim_rad']+b['trim_rad'])/2) if mode == 'free_trim' else fixed],(0,2) if mode == 'free_trim' else (0,),'adaptive_'+name)
                point = existing or _point(state,name)
                if existing is None:
                    d['points'].append(point)
                if point['identity'] not in branch['point_identities']:
                    branch['point_identities'].append(point['identity'])
                marked=lambda p:any(o['limits_intact'] and o['closing_status']!='closed' and o['immersed'] for o in p['openings'])
                if origin_probe:
                    if marked(point) and not marked(origin):
                        # This is not a midpoint: use the actual origin/probe
                        # event bracket and let its midpoint be checked next.
                        distance=abs(point['heel_rad']-initial[0]['heel_rad'])
                        branch['status']='intact_limit'
                        branch['intact_limit']=dict(heel_rad=point['heel_rad'],
                            openings=[o['name'] for o in point['openings'] if o['limits_intact'] and o['closing_status']!='closed' and o['immersed']],
                            resolution='engineering_angle_bracket',angle_uncertainty_rad=abs(point['heel_rad']-origin['heel_rad']))
                        indexed={p['identity']:p for p in d['points']}
                        branch['point_identities']=[i for i in branch['point_identities'] if abs(indexed[i]['heel_rad']-initial[0]['heel_rad'])<=distance]
                        queue=[(x,y) for x,y in queue if max(abs(x['heel_rad']-initial[0]['heel_rad']),abs(y['heel_rad']-initial[0]['heel_rad']))<=distance]
                        intervals=[i for i in intervals if max(abs(i['from_heel_rad']-initial[0]['heel_rad']),abs(i['to_heel_rad']-initial[0]['heel_rad']))<=distance]
                        queue.insert(0,(origin,point))
                    else:
                        queue[0:0]=[(a,point),(point,b)]
                    ex.notify('accepted_origin_probe',midpoint,point)
                    continue
                error = abs(point['gz_m']-(a['gz_m']+b['gz_m'])/2)
                area = error*width/2
                immersion_change=marked(a)!=marked(b)
                if marked(point) and not marked(a):
                    # Drop the farther immersed part: geometry beyond first
                    # intact-opening immersion never contributes intact metrics.
                    branch['intact_limit']=dict(heel_rad=point['heel_rad'],openings=[o['name'] for o in point['openings'] if o['limits_intact'] and o['closing_status']!='closed' and o['immersed']],
                        resolution='engineering_angle_bracket',angle_uncertainty_rad=abs(point['heel_rad']-a['heel_rad']))
                    branch['status']='intact_limit'
                    branch['point_identities']=[i for i in branch['point_identities'] if abs(next(p for p in d['points'] if p['identity']==i)['heel_rad']-initial[0]['heel_rad'])<=abs(point['heel_rad']-initial[0]['heel_rad'])]
                    queue=[(x,y) for x,y in queue if abs(y['heel_rad']-initial[0]['heel_rad'])<=abs(point['heel_rad']-initial[0]['heel_rad'])]
                    limit_distance=abs(point['heel_rad']-initial[0]['heel_rad'])
                    intervals=[i for i in intervals if max(abs(i['from_heel_rad']-initial[0]['heel_rad']),abs(i['to_heel_rad']-initial[0]['heel_rad']))<=limit_distance]
                    if width/2>c['angle_tolerance_rad']:
                        queue.insert(0,(a,point)); continue
                    # The old far endpoint has been removed. Never fall through
                    # into midpoint splitting that would re-admit (point,b).
                    intervals.append(dict(from_heel_rad=a['heel_rad'],to_heel_rad=point['heel_rad'],
                        status='engineering_estimate_resolved' if error<=c['gz_tolerance_m'] and area<=c['area_tolerance_mrad'] else 'unresolved_value_estimate',
                        gz_error_estimate_m=error,area_error_estimate_mrad=area,estimate_source='parent_interval'))
                    continue
                elif immersion_change and not marked(point):
                    if width/2>c['angle_tolerance_rad']:
                        queue.insert(0,(point,b)); queue.insert(0,(a,point)); continue
                    if branch['intact_limit']:
                        branch['intact_limit']['angle_uncertainty_rad']=width/2
                        branch['intact_limit']['resolution']='engineering_angle_bracket'
                # Resolve both a zero crossing and a bracketed local extremum
                # in angle as well as GZ/area value estimates.
                peak=point['gz_m']>max(a['gz_m'],b['gz_m']) or point['gz_m']<min(a['gz_m'],b['gz_m'])
                ordered=sorted((p for p in d['points'] if p['identity'] in branch['point_identities']),key=lambda p:p['heel_rad'])
                extrema=set()
                for left,centre,right in zip(ordered,ordered[1:],ordered[2:]):
                    dl=centre['gz_m']-left['gz_m']; dr=right['gz_m']-centre['gz_m']
                    if dl*dr<0:
                        extrema.add(centre['identity'])
                endpoint_peak=a['identity'] in extrema or b['identity'] in extrema
                # The converged baseline is already the known root. Its tiny
                # signed residual must not trigger a second search for that root.
                # Still inspect both midpoint halves for a distinct crossing.
                crossing = any(_distinct_zero_crossing(x, y, d['equilibrium'])
                    for x,y in ((a,b),(a,point),(point,b)))
                angle_needed = ((crossing or peak or immersion_change) and width > c['angle_tolerance_rad']) or (endpoint_peak and width>c['angle_tolerance_rad']/2)
                resolved = error <= c['gz_tolerance_m'] and area <= c['area_tolerance_mrad'] and not angle_needed
                if resolved:
                    intervals.append(dict(from_heel_rad=a['heel_rad'],to_heel_rad=b['heel_rad'],status='engineering_estimate_resolved',
                        gz_error_estimate_m=error,area_error_estimate_mrad=area))
                else:
                    queue.extend(((a,point),(point,b)))
                ex.notify('accepted_refinement',midpoint,point)
            except StabilityError as exc:
                branch['status'] = 'partial'; failure = _failure(exc,'adaptive',name,midpoint)
                branch['failure'] = failure; d['failures'].append(failure)
                intervals.append(dict(from_heel_rad=a['heel_rad'],to_heel_rad=b['heel_rad'],status='unresolved_refusal',
                    gz_error_estimate_m=None,area_error_estimate_mrad=None))
                intervals.extend(dict(from_heel_rad=x['heel_rad'],to_heel_rad=y['heel_rad'],status='unresolved_pending',
                    gz_error_estimate_m=None,area_error_estimate_mrad=None) for x,y in queue)
                queue.clear()
                if exc.code in (ErrorCode.CANCELLED,ErrorCode.DEADLINE_EXCEEDED,ErrorCode.WORK_BUDGET_EXCEEDED,ErrorCode.INTEGRITY_ERROR,ErrorCode.SOURCE_STALE):
                    branch['intervals'] = intervals; raise
        branch['intervals'] = intervals


def solve_floating_equilibrium(study, *, controls=None, cancellation_check=None, progress=None,
        execution_started_monotonic=None):
    return _run(study,curve=False,controls=controls,cancellation_check=cancellation_check,progress=progress,
        execution_started_monotonic=execution_started_monotonic)


def calculate_gz_curve(study, *, mode='free_trim', fixed_trim_rad=None, profile='preview',
        heels_rad=None, controls=None, cancellation_check=None, progress=None, seed_result=None,
        execution_started_monotonic=None):
    return _run(study,curve=True,mode=mode,fixed_trim_rad=fixed_trim_rad,profile=profile,
        heels_rad=heels_rad,controls=controls,cancellation_check=cancellation_check,progress=progress,seed_result=seed_result,
        execution_started_monotonic=execution_started_monotonic)


def _metrics(d):
    result = dict(assurance='engineering_estimates_not_certified_bounds', criteria='not_evaluated',
        hydrostatic_GM_m=None, hydrostatic_GM_reason='frozen-liquid hydrostatic derivative not evaluated', branches={})
    indexed = {p['identity']:p for p in d['points']}
    for name,branch in d['branches'].items():
        points = sorted((indexed[i] for i in branch['point_identities']),key=lambda p:p['heel_rad'])
        # Polyline descriptors are always named sampled, never continuous metrics.
        area = math.fsum((b['heel_rad']-a['heel_rad'])*(a['gz_m']+b['gz_m'])/2 for a,b in zip(points,points[1:])) if len(points)>1 and branch['status']!='partial' else None
        resolved = bool(branch['intervals']) and all(i['status'] == 'engineering_estimate_resolved' for i in branch['intervals']) and branch['status'] in ('complete','intact_limit')
        direction=-1 if name=='negative' else 1
        maximum = max((direction*p['gz_m'] for p in points),default=None)
        zeros=[]; plateau=False
        for a,b in zip(points,points[1:]):
            if _distinct_zero_crossing(a,b,d['equilibrium']) and abs(b['heel_rad']-a['heel_rad'])<=d['request']['controls']['angle_tolerance_rad']:
                zeros.append(a['heel_rad']-a['gz_m']*(b['heel_rad']-a['heel_rad'])/(b['gz_m']-a['gz_m']))
        eqheel=d['equilibrium']['heel_rad'] if d['equilibrium'] else 0.
        for index,p in enumerate(points):
            if p['gz_m']==0 and not _accepted_root(p,d['equilibrium']) and abs(p['heel_rad']-eqheel)>d['request']['controls']['angle_tolerance_rad']:
                neighbours=[points[i] for i in (index-1,index+1) if 0<=i<len(points)]
                if any(n['gz_m']==0 for n in neighbours):
                    plateau=True
                else:
                    zeros.append(p['heel_rad'])
        roots=sorted((v for v in zeros if abs(v-eqheel)>d['request']['controls']['angle_tolerance_rad']),key=lambda v:abs(v-eqheel))
        max_angles=[p['heel_rad'] for p in points if direction*p['gz_m']==maximum]
        peak_brackets=[]
        for index,p in enumerate(points):
            if direction*p['gz_m']==maximum and 0<index<len(points)-1:
                peak_brackets.append(points[index+1]['heel_rad']-points[index-1]['heel_rad'])
        peak_resolved=resolved and all(width<=d['request']['controls']['angle_tolerance_rad'] for width in peak_brackets)
        result['branches'][name] = dict(sampled_signed_area_mrad=area, sampled_maximum_gz_m=maximum,
            restoring_direction=direction,maximum_definition='max(direction_times_signed_raw_gz)',
            sampled_maximum_signed_raw_gz_m=None if maximum is None else direction*maximum,
            sampled_maximum_angles_rad=max_angles,
            signed_area_estimate_mrad=area if resolved else None,
            maximum_gz_estimate_m=maximum if resolved else None,
            maximum_gz_angles_estimate_rad=max_angles if peak_resolved else None,
            maximum_angle_reason=None if peak_resolved else 'unresolved_extremum_angle_bracket',
            continuous_metrics_reason=None if resolved else 'unresolved_intervals_or_branch_limit',
            vanishing_angle_estimate_rad=roots[0] if resolved and roots and not plateau else None,
            vanishing_angle_reason=None if resolved and roots and not plateau else ('nonisolated_zero_plateau' if plateau else 'no_resolved_zero_crossing_in_intact_requested_range'),
            downflooding=branch['intact_limit'])
    eq = d['equilibrium']
    if eq:
        result['hydrostatic_GM_m']=eq['hydrostatic_GM_m']
        result['hydrostatic_GM_reason']=eq['hydrostatic_GM_reason']
    if eq and len(d['points']) >= 3:
        left = [p for p in d['points'] if p['heel_rad'] < eq['heel_rad']]
        right = [p for p in d['points'] if p['heel_rad'] > eq['heel_rad']]
        if left and right:
            a=max(left,key=lambda p:p['heel_rad']); b=min(right,key=lambda p:p['heel_rad'])
            result['effective_moving_liquid_gz_slope_m']=(b['gz_m']-a['gz_m'])/(b['heel_rad']-a['heel_rad'])
            result['effective_slope_angular_span_rad']=b['heel_rad']-a['heel_rad']
    result.setdefault('effective_moving_liquid_gz_slope_m',None)
    resolutions=sorted({b['intact_limit']['resolution'] for b in d['branches'].values() if b['intact_limit']})
    result['downflooding_reason']='no_opening_inventory_closed_envelope_diagnostic' if not eq or not eq['openings'] else (';'.join(resolutions) if resolutions else 'no_marked_opening_immersion_in_retained_range')
    return result


def stability_metrics(result):
    if not isinstance(result, EngineeringResult):
        invalid('typed EngineeringResult required')
    return _metrics(result.to_dict())


def save_stability_study(study, path, *, result=None):
    from .persistence import atomic_write
    if not isinstance(study, EngineeringStudy):
        invalid('typed EngineeringStudy required')
    if result is not None and (not isinstance(result, EngineeringResult) or result.to_dict()['study_identity'] != study.identity):
        invalid('result does not belong to study')
    payload = dict(schema=SCHEMA, study=study.to_dict(),study_identity=study.identity,
        result=None if result is None else result.to_dict())
    payload['identity'] = content_hash(payload)
    raw = canonical_bytes(payload)
    # Existing atomic writer is intentionally bounded at2MB; avoid weakening it.
    # Workflow snapshots use their own larger bounded atomic writer below.
    _atomic(path,raw)
    return payload['identity']


def _atomic(path, raw):
    import os
    import tempfile
    p=Path(path).absolute()
    if len(raw)>_MAX_BYTES or any(_linked(v) for v in (p,*p.parents)):
        invalid('workflow persistence size/path refused')
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.stability-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,p)
    finally:
        Path(name).unlink(missing_ok=True)


def load_stability_study(path):
    try:
        d=decode_json(_read(path))
        if d['schema']!=SCHEMA or d['identity']!=content_hash({k:v for k,v in d.items() if k!='identity'}):
            raise StabilityError(ErrorCode.INTEGRITY_ERROR,'saved workflow integrity mismatch')
        study=EngineeringStudy(canonical_bytes(d['study']))
        if study.identity!=d['study_identity']:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR,'saved study identity mismatch')
        result=None if d['result'] is None else EngineeringResult(canonical_bytes(d['result']))
        if result and result.to_dict()['study_identity']!=study.identity:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR,'saved result belongs to another study')
        return study,result
    except (KeyError,TypeError,ValueError) as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR,'invalid saved workflow') from exc


def export_stability_report(study,result,destination):
    if not isinstance(study,EngineeringStudy) or not isinstance(result,EngineeringResult) or result.to_dict()['study_identity']!=study.identity:
        invalid('matching study/result required')
    root=Path(destination).absolute()
    if any(_linked(v) for v in (root,*root.parents)):
        invalid('symbolic-link report destination refused')
    root.mkdir(parents=True,exist_ok=False)
    d=result.to_dict(); metrics=stability_metrics(result)
    rows=sorted(d['points'],key=lambda p:p['heel_rad'])
    out=io.StringIO(newline=''); writer=csv.writer(out)
    columns=['branch','heel_rad','trim_rad','origin_z_m','mass_kg','gz_m','righting_moment_Nm','generalized_Qheel_Nm','vertical_residual_N','trim_residual_Nm']
    writer.writerow(columns)
    for p in rows:
        writer.writerow([p.get(k) for k in columns])
    files={'points.csv':out.getvalue().encode(),'result.json':canonical_bytes(d),'metrics.json':canonical_bytes(metrics)}
    title='ANYstability engineering stability report'
    text=f'# {title}\n\nStatus: {d["status"]}\n\nStudy: {study.identity}\n\nResult: {result.identity}\n\nEngineering estimates; no continuous certification, regulatory PASS or external approval.\n\n'
    text+='Geometry: '+d['assurance']['geometry']+'\n\n'
    text+='Effective moving-liquid GZ slope: '+str(metrics['effective_moving_liquid_gz_slope_m'])+' m/rad\n\n'
    text+='Hydrostatic frozen-liquid GM: '+str(metrics['hydrostatic_GM_m'])+' m; '+str(metrics['hydrostatic_GM_reason'])+'\n\n'
    text+='Downflooding: '+metrics['downflooding_reason']+'\n\n'
    text+='Failures: '+str(len(d['failures']))+'; unresolved intervals remain unavailable.\n'
    if d['equilibrium']:
        eq=d['equilibrium']
        text+='\nEquilibrium mass: '+str(eq['mass_kg'])+' kg; CG body: '+str(eq['cg_body_m'])+' m.\n\n'
        text+='| Tank | Target m3 | Achieved m3 | Volume residual m3 | Liquid CG body m |\n|---|---:|---:|---:|---|\n'
        for name,tank in eq['tanks'].items():
            text+='| '+name+' | '+str(tank['target_volume_m3'])+' | '+str(tank['achieved_volume_m3'])+' | '+str(tank['residual_volume_m3'])+' | '+str(tank['cg_body_m'])+' |\n'
    text+='\nMaximum restoring GZ uses direction times signed raw GZ: direction -1 on the negative branch, +1 on the positive branch. Areas retain their ascending-angle signed convention.\n'
    text+='\n| Branch | Signed area estimate m rad | Maximum branch restoring GZ estimate m | Maximum angles rad | Vanishing angle rad |\n|---|---:|---:|---|---:|\n'
    for name,m in metrics['branches'].items():
        text+='| '+name+' | '+str(m['signed_area_estimate_mrad'])+' | '+str(m['maximum_gz_estimate_m'])+' | '+str(m['maximum_gz_angles_estimate_rad'])+' | '+str(m['vanishing_angle_estimate_rad'])+' |\n'
    files['report.md']=text.encode()
    files['report.html']=('<!doctype html><html><meta charset="utf-8"><title>'+title+'</title><body><h1>'+title+'</h1><pre>'+html.escape(text)+'</pre><img src="gz.svg" alt="Retained GZ samples"><p><a href="points.csv">CSV</a> <a href="result.json">Full retained evidence</a></p></body></html>').encode()
    paths=[]
    for name,branch in d['branches'].items():
        indexed={p['identity']:p for p in rows}
        selected=sorted((indexed[i] for i in branch['point_identities']),key=lambda p:p['heel_rad'])
        color='#1266aa' if name=='positive' else '#aa4412'
        # Mark all retained branch points, but draw lines only on resolved
        # intervals. A refused refinement cannot be bridged in a report figure.
        for p in selected:
            paths.append(f'<circle cx="{400+p["heel_rad"]*300}" cy="{250-p["gz_m"]*100}" r="2" fill="{color}"/>')
        byheel={p['heel_rad']:p for p in selected}
        for interval in branch['intervals']:
            if interval['status']!='engineering_estimate_resolved':
                continue
            a=byheel.get(interval['from_heel_rad']); b=byheel.get(interval['to_heel_rad'])
            if a is not None and b is not None:
                paths.append(f'<path fill="none" stroke="{color}" d="M{400+a["heel_rad"]*300} {250-a["gz_m"]*100} L{400+b["heel_rad"]*300} {250-b["gz_m"]*100}"/>')
    files['gz.svg']=('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="0 0 800 500"><title>Retained engineering GZ samples; radians and metres</title><path d="M0 250H800M400 0V500" stroke="gray"/>'+''.join(paths)+'</svg>').encode()
    manifest=dict(schema=SCHEMA,study_identity=study.identity,result_identity=result.identity,
        assurance=d['assurance'],files={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()})
    for name,raw in files.items():
        _atomic(root/name,raw)
    _atomic(root/'manifest.json',canonical_bytes(manifest))
    return dict(destination=str(root),manifest=manifest)
