"""Explicit installed-owner certified point integration; no production admission.

No owner import happens until the pinned wheel and installed package are checked.
Saved records are evidence for inspection only and cannot authorize execution.
"""
from fractions import Fraction
import hashlib
import importlib
from importlib import metadata, util
import json
import math
import io
import marshal
from pathlib import Path
import sys
import time
import types
import zipfile
from collections import namedtuple
from types import MappingProxyType

from ..errors import ErrorCode, StabilityError
from ..validation import canonical_bytes, content_hash, exact, integer, invalid, sequence
from .integrals import (IntegralRequest, IntegralSample, PlaneFrame, PreparedBinding,
                        WaterplaneMoments)
from .protocol import ProviderBinding, Quantity

OwnerArtifact = namedtuple("OwnerArtifact", "version source_commit")
OWNER_ARTIFACTS = MappingProxyType({
    "b2954944a71ed5f5d6e1c36391346a08d4a60a821184772a062c48245ff6a7cd":
        OwnerArtifact("0.4.7", "9bc80c0005b8822cfb35bc8cd17db9d84d2dbdbc"),
    "4502e2292214a2217a666b4e67b4660eb89308676ba4ea06ece5664911d3e886":
        OwnerArtifact("0.4.8", "a960e57dfbcc1c4cf2c5b0244508b3959c04d46b"),
})
OWNER_VERSION = "0.4.8"
WHEEL_SHA256 = "4502e2292214a2217a666b4e67b4660eb89308676ba4ea06ece5664911d3e886"
KIND = "anystability-certified-point-v1"
MAX_RECORD_BYTES = 128 * 1024 * 1024
NAMES = ("V", "Jx", "Jy", "Jz", "A", "Mu", "Mv", "Iuu", "Ivv", "Iuv")


def _fail(code, message, **details):
    raise StabilityError(code, message, **details)


def _plain(value):
    """Detach mutable JSON input without importing or executing owner code."""
    def safe(v):
        if type(v) is int and v.bit_length() > 4096:
            # Preserve large proof integers without changing Python's global
            # integer-conversion security limit. This tagging is transport only.
            chunks, n = [], abs(v)
            while n:
                n, r = divmod(n, 10**9)
                chunks.append(r)
            digits = str(chunks.pop()) + "".join(f"{c:09d}" for c in reversed(chunks))
            return {"integer_decimal": ("-" if v < 0 else "") + digits}
        if isinstance(v, dict):
            return {k: safe(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [safe(x) for x in v]
        return v
    return json.loads(canonical_bytes(safe(value)))


def _parse_proof(proof):
    def bounded_integer(s):
        if len(s) <= 1234:
            return int(s)
        return {"integer_decimal": s}
    try:
        return _plain(json.loads(proof, parse_int=bounded_integer))
    except (ValueError, RecursionError) as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "saved certificate is not readable JSON") from exc


def _path(path):
    p = Path(path).absolute()
    if any(q.is_symlink() for q in (p, *p.parents)):
        _fail(ErrorCode.INTEGRITY_ERROR, "symbolic-link evidence path refused")
    return p


def authenticate_installed_owner(wheel):
    """Authenticate package files and origins, without process-memory attestation."""
    try:
        return _authenticate_installed_owner(wheel)
    except StabilityError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, "pinned owner wheel/installation is unreadable or invalid",
                             cause_type=type(exc).__name__, cause=str(exc)) from exc


def _authenticate_installed_owner(wheel):
    """Check exact wheel bytes, every installed package member and import origins.

    Only explicitly pinned deliveries are supported; a matching distribution
    version alone is insufficient. No optional imports here.
    """
    wheel = _path(wheel)
    if wheel.stat().st_size > 64 * 1024 * 1024:
        invalid("owner wheel exceeds artifact limit")
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    identity = OWNER_ARTIFACTS.get(wheel_sha256)
    if identity is None:
        _fail(ErrorCode.INTEGRITY_ERROR, "owner wheel differs from pinned delivery")
    try:
        dist = metadata.distribution("ANYgeometry")
    except metadata.PackageNotFoundError as exc:
        raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, "install the pinned ANYgeometry wheel in an isolated environment") from exc
    if dist.version != identity.version:
        _fail(ErrorCode.PROVIDER_UNAVAILABLE, "wrong installed owner version", expected=identity.version, actual=dist.version)
    root = _path(dist.locate_file("anygeometry"))
    if not root.is_dir():
        _fail(ErrorCode.INTEGRITY_ERROR, "installed owner package missing")
    members = {}
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if not entry.filename.startswith("anygeometry/") or entry.is_dir():
                continue
            relative = entry.filename.removeprefix("anygeometry/")
            p = _path(root / relative)
            if not p.is_relative_to(root) or not p.is_file():
                _fail(ErrorCode.INTEGRITY_ERROR, "installed owner member missing", member=relative)
            expected = hashlib.sha256(archive.read(entry)).hexdigest()
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                _fail(ErrorCode.INTEGRITY_ERROR, "installed owner member changed", member=relative)
            members[relative] = expected
    for p in root.rglob("*.py"):
        if p.relative_to(root).as_posix() not in members:
            _fail(ErrorCode.INTEGRITY_ERROR, "extra executable owner module", path=str(p))
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".pyd", ".dll", ".so", ".dylib", ".pyw"}:
            if p.relative_to(root).as_posix() not in members:
                _fail(ErrorCode.INTEGRITY_ERROR, "extra native/executable owner member", path=str(p))
    for cached in root.rglob("*.pyc"):
        try:
            cached = _path(cached)
            source = _path(util.source_from_cache(str(cached)))
            rel = source.relative_to(root).as_posix()
            if rel not in members or cached.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("unmatched cached bytecode")
            data = cached.read_bytes()
            if len(data) < 16 or data[:4] != util.MAGIC_NUMBER or int.from_bytes(data[4:8], "little") not in (0, 1, 3):
                raise ValueError("invalid cached bytecode header")
            stream = io.BytesIO(data[16:])
            code = marshal.load(stream)
            if stream.read() or not isinstance(code, types.CodeType):
                raise ValueError("invalid cached bytecode payload")
            name = cached.name
            optimize = 1 if ".opt-1." in name else 2 if ".opt-2." in name else 0
            if ".opt-" in name and optimize == 0:
                raise ValueError("unsupported bytecode optimization")
            expected_code = compile(source.read_bytes(), str(source), "exec", dont_inherit=True, optimize=optimize)
            def same(actual, expected):
                return (actual == expected and Path(actual.co_filename).resolve() == source.resolve()
                    and all(same(a, b) for a, b in zip(actual.co_consts, expected.co_consts)
                            if isinstance(a, types.CodeType)))
            if not same(code, expected_code):
                raise ValueError("cached bytecode differs from authenticated source")
        except (OSError, ValueError, TypeError, EOFError, SyntaxError) as exc:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "untrusted installed owner cached bytecode",
                                 path=str(cached), cause_type=type(exc).__name__) from exc
    spec = util.find_spec("anygeometry")
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != (root / "__init__.py").resolve():
        _fail(ErrorCode.INTEGRITY_ERROR, "owner import resolves outside authenticated installation")
    for name, module in tuple(sys.modules.items()):
        if name == "anygeometry" or name.startswith("anygeometry."):
            origin = getattr(module, "__file__", None)
            if origin is None or not Path(origin).resolve().is_relative_to(root.resolve()):
                _fail(ErrorCode.INTEGRITY_ERROR, "loaded owner module has foreign origin", module=name)
            rel = Path(origin).resolve().relative_to(root.resolve()).as_posix()
            if rel not in members:
                _fail(ErrorCode.INTEGRITY_ERROR, "loaded owner module is not a wheel member", module=name)
    return dict(version=identity.version, wheel_sha256=wheel_sha256, source_commit=identity.source_commit,
                package_files_sha256=content_hash(members), package_root=str(root))


def _quantity(item, limit):
    """Enclose the verified binary64 endpoints even after midpoint conversion."""
    if item.binary64 is None or item.accuracy_met is not True:
        _fail(ErrorCode.INTEGRITY_ERROR, "verified quantity lacks requested binary64 bound", quantity=item.name)
    lo, hi = item.binary64
    if not all(type(x) is float and math.isfinite(x) for x in (lo, hi)) or lo > hi:
        _fail(ErrorCode.INTEGRITY_ERROR, "invalid verified binary64 endpoints", quantity=item.name)
    a, b = Fraction(lo), Fraction(hi)
    if b-a > Fraction(limit):
        _fail(ErrorCode.ACCURACY_UNRESOLVED, "verified interval exceeds requested width", quantity=item.name)
    value = float((a+b)/2)
    radius = max(Fraction(value)-a, b-Fraction(value))
    error = float(radius)
    if Fraction(error) < radius:
        error = math.nextafter(error, math.inf)
    if error > limit:
        _fail(ErrorCode.ACCURACY_UNRESOLVED, "consumer conversion exceeds requested error", quantity=item.name)
    return Quantity(value, error, "owner_certified_bound")


def _limits(request):
    a = request.accuracy
    values = (a.volume_m3, *([a.first_moments_m4]*3), a.waterplane_area_m2,
              *([a.waterplane_first_m3]*2), *([a.waterplane_second_m4]*3))
    if any(v <= 0 for v in values):
        invalid("certified point accuracy widths must be positive")
    return dict(zip(NAMES, values))


def _query_document(request, frame):
    def pair(value):
        q = Fraction(value)
        return [q.numerator, q.denominator]
    return dict(normal=[pair(v) for v in request.plane.normal], offset=pair(request.plane.offset_m),
        waterplane_origin=[pair(v) for v in frame.origin_body_m],
        waterplane_axes=[[pair(v) for v in row] for row in (frame.u_body, frame.v_body)],
        absolute_accuracy={k: pair(v) for k, v in _limits(request).items()}, forms=["binary64"])


def _owner_refusal(exc, request, frame):
    category = exc.category.value
    code = {
        "ACCURACY_UNACHIEVABLE": ErrorCode.ACCURACY_UNRESOLVED,
        "RESULT_OUT_OF_RANGE": ErrorCode.ACCURACY_UNRESOLVED,
        "BUDGET_EXHAUSTED": ErrorCode.WORK_BUDGET_EXCEEDED,
        "BIT_LENGTH_EXCEEDED": ErrorCode.WORK_BUDGET_EXCEEDED,
        "CONCURRENT_MUTATION": ErrorCode.SOURCE_STALE,
        "STALE_PREPARATION": ErrorCode.SOURCE_STALE,
        "SYMBOLIC_DEGENERACY": ErrorCode.QUERY_DEGENERATE,
        "CURVED_SECTION_DEGENERACY": ErrorCode.QUERY_DEGENERATE,
        "VERIFICATION_FAILED": ErrorCode.INTEGRITY_ERROR,
        "MALFORMED_PROOF": ErrorCode.INTEGRITY_ERROR,
        "CANCELLED": ErrorCode.CANCELLED,
        "DEADLINE_EXCEEDED": ErrorCode.DEADLINE_EXCEEDED,
    }.get(category, ErrorCode.CAPABILITY_UNSUPPORTED)
    cause = exc.__cause__
    return StabilityError(code, "owner certified point refused", request=request.to_dict(),
        frame=frame.to_dict(), owner=dict(category=category, phase=exc.phase,
        sub_reason=exc.sub_reason, request=_plain(exc.request), identity=_plain(exc.identity),
        work=_plain(exc.work), detail=exc.detail,
        cause=None if cause is None else dict(type=type(cause).__name__, message=str(cause))))


def _map_sample(checked, binding, request, frame, operations):
    limits = _limits(request)
    if not checked.generic:
        _fail(ErrorCode.QUERY_DEGENERATE, "point adapter requires a generic owner query", request=request.to_dict())
    values = (checked.volume, *checked.moments)
    if tuple(q.name for q in values) != NAMES[:4]:
        _fail(ErrorCode.INTEGRITY_ERROR, "owner volume moment order differs")
    qs = [_quantity(q, limits[q.name]) for q in values]
    if len(checked.sections) != 1 or checked.sections[0].side != "plane":
        _fail(ErrorCode.INTEGRITY_ERROR, "owner section sides differ")
    section = checked.sections[0]
    if section.section == "ABSENT":
        if checked.occupancy not in {"EMPTY", "FULL"} or section.quantities is not None or section.topology is not None:
            _fail(ErrorCode.INTEGRITY_ERROR, "invalid absent section")
        waterplane = None
    elif section.section == "PRESENT" and section.quantities is not None and section.topology is not None:
        if tuple(q.name for q in section.quantities) != NAMES[4:]:
            _fail(ErrorCode.INTEGRITY_ERROR, "owner waterplane moment order differs")
        w = [_quantity(q, limits[q.name]) for q in section.quantities]
        waterplane = WaterplaneMoments(frame, w[0], tuple(w[1:3]), tuple(w[3:6]),
                                      section.topology.outer_count, section.topology.hole_count)
    else:
        _fail(ErrorCode.INTEGRITY_ERROR, "unrecognized section state")
    return IntegralSample(binding, request, qs[0], tuple(qs[1:]), waterplane,
        checked.occupancy.lower(), operations, "sha256:"+checked.proof_sha256)


def certified_point(model_document, boundary_ids, request, frame, *, wheel,
                    cancellation_check=None, deadline=None, require_hard_preemption=False,
                    convention_version="2"):
    """Prepare, query and independently verify one explicitly requested point.

    max_work_units maps to ONE shared owner WorkBudget.max_operations across
    preparation/query/verification. Policy max_bits is 65536. Counts are owner
    primitive operations, not elapsed time. Cancellation and an absolute
    time.monotonic deadline are cooperative: owner qualification has unmetered,
    nonpreemptible spans. Hard limits require a supervised disposable process.
    """
    if not isinstance(request, IntegralRequest) or not isinstance(frame, PlaneFrame):
        invalid("certified point requires IntegralRequest and PlaneFrame")
    if type(convention_version) is not str or convention_version not in {"1", "2"}:
        invalid("explicit owner convention_version must be '1' or '2'")
    if type(require_hard_preemption) is not bool:
        invalid("require_hard_preemption must be boolean")
    if require_hard_preemption:
        _fail(ErrorCode.CAPABILITY_UNSUPPORTED, "certified synchronous point cannot guarantee hard preemption")
    if cancellation_check is not None and not callable(cancellation_check):
        invalid("cancellation_check must be callable")
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        invalid("deadline must be a finite absolute monotonic time")
    def cancelled():
        value = False if cancellation_check is None else cancellation_check()
        if type(value) is not bool:
            invalid("cancellation_check must return bool")
        return value
    def poll():
        if cancelled():
            _fail(ErrorCode.CANCELLED, "certified point cooperatively cancelled", request=request.to_dict(), frame=frame.to_dict())
        if deadline is not None and time.monotonic() >= deadline:
            _fail(ErrorCode.DEADLINE_EXCEEDED, "certified point cooperative deadline expired", request=request.to_dict(), frame=frame.to_dict())
    poll()
    frame.validate_plane(request.plane)
    limits = _limits(request)
    faces = sequence(boundary_ids, "owner boundary IDs", 100000)
    if not faces or len(set(faces)) != len(faces):
        invalid("owner boundary IDs must be nonempty and unique")
    for face in faces:
        integer(face, "owner face identity", 0, 2**63-1)
    # The owner producer preserves caller order, while its independent verifier
    # compares the selected face set in numeric order. Canonicalize the set once
    # before every owner call; identities themselves are never changed.
    faces = tuple(sorted(faces))
    document = _plain(model_document)
    runtime = authenticate_installed_owner(wheel)
    api = importlib.import_module("anygeometry.certified_hydrostatics")
    serialization = importlib.import_module("anygeometry.serialization")
    owner_errors = importlib.import_module("anygeometry.errors")
    if authenticate_installed_owner(wheel) != runtime:
        _fail(ErrorCode.INTEGRITY_ERROR, "owner runtime identity changed during import")
    policy = api.CertifiedHydrostaticsPolicy(convention_version=convention_version)
    budget = api.WorkBudget(request.max_work_units, policy.max_bits, deadline)
    query = api.HalfSpaceQuery(request.plane.normal, request.plane.offset_m,
        frame.origin_body_m, (frame.u_body, frame.v_body),
        {name: Fraction(value) for name, value in limits.items()}, ("binary64",))
    try:
        poll()
        model = serialization.from_dict(document)
        poll()
        prepared = api.prepare_certified_hydrostatics(model, faces, policy=policy, budget=budget, cancellation_check=cancelled)
        if prepared.policy.as_dict() != policy.as_dict():
            _fail(ErrorCode.CAPABILITY_UNSUPPORTED, "owner preparation changed explicitly requested convention/policy",
                  requested_policy=policy.as_dict(), prepared_policy=prepared.policy.as_dict(), request=request.to_dict())
        poll()
        response = api.query_certified_hydrostatics(prepared, query, budget=budget, cancellation_check=cancelled)
        poll()
        expected = dict(artifact=prepared.implementation, convention_version=convention_version, units="m", policy=policy)
        # Full caller response and its proof, never a receipt or proof-only shortcut.
        checked = api.verify_certified_hydrostatics(model, faces, query, response, expected, budget=budget, cancellation_check=cancelled)
        poll()
    except api.CertifiedHydrostaticsRefusal as exc:
        raise _owner_refusal(exc, request, frame) from exc
    except owner_errors.GeometryError as exc:
        raise StabilityError(ErrorCode.INPUT_INVALID, "owner rejected serialized geometry input",
                             request=request.to_dict(), frame=frame.to_dict(),
                             owner_cause=dict(type=type(exc).__name__, message=str(exc))) from exc
    if authenticate_installed_owner(wheel) != runtime:
        _fail(ErrorCode.INTEGRITY_ERROR, "owner runtime identity changed during query/verification")
    binding = PreparedBinding(ProviderBinding("anygeometry_certified_point_v1",
        content_hash(dict(model=document, boundary_ids=sorted(faces))),
        "ANYgeometry/"+runtime["version"], "owner_certified"), str(prepared.model_id),
        str(prepared.revision), tuple(str(v) for v in faces),
        "anygeometry.certified_hydrostatics/convention-"+convention_version, "certified_owner",
        "per-artifact per-query verified point; no production qualification",
        runtime["wheel_sha256"], "verify_certified_hydrostatics/convention-"+convention_version)
    work = budget.counts()
    if work["operations"] > request.max_work_units:
        _fail(ErrorCode.WORK_BUDGET_EXCEEDED, "owner exceeded declared operation cap", work=work, request=request.to_dict())
    sample = _map_sample(checked, binding, request, frame, work["operations"])
    proof = response.proof.decode("utf-8")
    payload = dict(kind=KIND, production_qualified=False, admission="geometry_owner_certified",
        runtime=runtime, model_document=document, boundary_ids=list(faces),
        prepared_model_identity=prepared.model_identity(), artifact=prepared.artifact_identity(),
        policy=policy.as_dict(), owner_query=query.as_dict(), frame=frame.to_dict(),
        owner_response=response.claim(), certificate=proof,
        certificate_sha256=hashlib.sha256(response.proof).hexdigest(),
        verified=dict(proof_sha256=checked.proof_sha256,
                      artifact_files_sha256=checked.artifact_files_sha256),
        sample=sample.to_dict(), work=work,
        controls=dict(max_owner_operations=request.max_work_units, max_owner_bits=policy.max_bits,
                      cancellation="cooperative" if cancellation_check is not None else "not_requested",
                      deadline_monotonic=deadline, hard_preemption=False,
                      nonpreemptible_spans="owner qualification, bulk serialization, Python imports and evidence publication"))
    record = _record(payload)
    inspect_certified_point(record)
    poll()
    return record


def _record(payload):
    payload = _plain(payload)
    return dict(payload=payload, sha256=content_hash(payload))


def inspect_certified_point(record, *, expected_source_hash=None, expected_request=None):
    """Owner-free retained integrity inspection; cannot admit execution."""
    try:
        return _inspect_certified_point(record, expected_source_hash=expected_source_hash,
                                        expected_request=expected_request)
    except StabilityError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "malformed retained certified point evidence",
                             cause_type=type(exc).__name__) from exc


def _inspect_certified_point(record, *, expected_source_hash=None, expected_request=None):
    """Owner-free integrity/transport inspection; never re-admits a saved proof."""
    d = exact(record, {"payload", "sha256"}, "certified point envelope")
    payload = _plain(d["payload"])
    if content_hash(payload) != d["sha256"]:
        _fail(ErrorCode.INTEGRITY_ERROR, "certified point record hash differs")
    fields = {"kind", "production_qualified", "admission", "runtime", "model_document", "boundary_ids",
              "prepared_model_identity", "artifact", "policy", "owner_query", "frame", "owner_response",
              "certificate", "certificate_sha256", "verified", "sample", "work", "controls"}
    exact(payload, fields, "certified point payload")
    if payload["kind"] != KIND or payload["production_qualified"] is not False or payload["admission"] != "geometry_owner_certified":
        invalid("unsupported certified point record")
    sample = IntegralSample.from_dict(payload["sample"])
    wheel_sha256 = payload["runtime"]["wheel_sha256"]
    identity = OWNER_ARTIFACTS.get(wheel_sha256)
    if identity is None:
        _fail(ErrorCode.INTEGRITY_ERROR, "saved owner artifact is not a pinned delivery")
    # Original 0.4.7 records lack source_commit. Preserve them without rewriting
    # their identity; version was already mandatory in the original runtime.
    runtime = payload["runtime"]
    if (identity.version != "0.4.7" and "source_commit" not in runtime
        or runtime.get("version") != identity.version
        or runtime.get("source_commit", identity.source_commit) != identity.source_commit
        or payload["artifact"].get("distribution_version") != identity.version
        or sample.binding.source.implementation != "ANYgeometry/"+identity.version):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved owner version/source binding differs")
    source_hash = content_hash(dict(model=payload["model_document"], boundary_ids=sorted(payload["boundary_ids"])))
    if sample.binding.source.source_hash != source_hash or sample.binding.artifact_sha256 != wheel_sha256:
        _fail(ErrorCode.INTEGRITY_ERROR, "saved certified point source/artifact differs")
    proof_hash = hashlib.sha256(payload["certificate"].encode("utf-8")).hexdigest()
    if proof_hash != payload["certificate_sha256"] or proof_hash != payload["verified"]["proof_sha256"] or sample.certificate_ref != "sha256:"+proof_hash:
        _fail(ErrorCode.INTEGRITY_ERROR, "saved certificate binding differs")
    proof = _parse_proof(payload["certificate"])
    frame = PlaneFrame(**exact(payload["frame"], set(PlaneFrame.__dataclass_fields__), "saved point frame"))
    frame.validate_plane(sample.request.plane)
    query = _query_document(sample.request, frame)
    comparisons = ((proof.get("query"), query), (payload["owner_query"], query),
        (proof.get("model"), payload["prepared_model_identity"]),
        (proof.get("artifact"), payload["artifact"]),
        (proof.get("preparation_policy"), payload["policy"]),
        (proof.get("result"), payload["owner_response"]))
    if any(canonical_bytes(a) != canonical_bytes(b) for a, b in comparisons):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved owner model/query/policy/response binding differs")
    model = payload["prepared_model_identity"]
    if (str(model["model_id"]) != sample.binding.model_id or str(model["revision"]) != sample.binding.revision
        or sorted(model["face_ids"]) != sorted(payload["boundary_ids"])
        or tuple(sorted(str(v) for v in payload["boundary_ids"])) != sample.binding.boundary_ids
        or proof.get("convention", {}).get("convention_version") not in {"1", "2"}
        or proof.get("convention", {}).get("units") != "m"):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved prepared identity/convention differs")
    convention = proof["convention"]["convention_version"]
    if (payload["policy"].get("convention_version") != convention
        or sample.binding.owner_api != "anygeometry.certified_hydrostatics/convention-"+convention
        or sample.binding.verifier_id != "verify_certified_hydrostatics/convention-"+convention):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved convention/policy/verifier binding differs")
    document = payload["model_document"]
    model_bytes = json.dumps({k: v for k, v in document.items() if k != "checksum"},
        ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    checksum = dict(algorithm="sha256", value=hashlib.sha256(model_bytes).hexdigest())
    if document.get("checksum") != checksum:
        _fail(ErrorCode.INTEGRITY_ERROR, "saved serialized model content checksum differs")
    if (document.get("model_id") != model["model_id"] or document.get("revision") != model["revision"]
        or document.get("checksum", {}).get("value") != model["document_checksum"]):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved model document identity differs from proof")
    _check_retained_quantities(payload["owner_response"], sample, frame)
    if (sample.work_units != payload["work"]["operations"] or sample.work_units > sample.request.max_work_units
        or payload["controls"]["max_owner_operations"] != sample.request.max_work_units):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved owner work binding differs")
    if expected_source_hash is not None and source_hash != expected_source_hash:
        _fail(ErrorCode.SOURCE_STALE, "saved source differs from expected source")
    if expected_request is not None and sample.request != expected_request:
        _fail(ErrorCode.SOURCE_STALE, "saved query/accuracy differs from expected request")
    return dict(identity=d["sha256"], status="retained_evidence_inspected",
                execution_admitted=False, production_qualified=False,
                sample=sample.to_dict(), certificate_sha256=proof_hash,
                source_hash=source_hash, work=payload["work"])


def _check_retained_quantities(claim, sample, frame):
    """Check retained transport against literal proof; not mathematical verification."""
    from types import SimpleNamespace
    limits = _limits(sample.request)
    def quantity(name, d):
        q = _quantity(SimpleNamespace(name=name, binary64=(float.fromhex(d["binary64"]["lo"]),
                      float.fromhex(d["binary64"]["hi"])), accuracy_met=d["accuracy_met"]), limits[name])
        return q
    v = quantity("V", claim["volume"])
    j = tuple(quantity(name, claim["moments"][name]) for name in NAMES[1:4])
    if (sample.volume_m3 != v or sample.first_moments_m4 != j or sample.immersion != claim["occupancy"].lower()
        or claim["generic"] is not True):
        _fail(ErrorCode.INTEGRITY_ERROR, "saved volume/occupancy transport differs")
    section = claim["sections"]["plane"]
    if sample.waterplane is None:
        if section["section"] != "ABSENT" or section["quantities"] is not None or section["topology"] is not None:
            _fail(ErrorCode.INTEGRITY_ERROR, "saved absence transport differs")
    else:
        if section["section"] != "PRESENT" or sample.waterplane.frame != frame:
            _fail(ErrorCode.INTEGRITY_ERROR, "saved waterplane frame/state differs")
        q = tuple(quantity(name, section["quantities"][name]) for name in NAMES[4:])
        topology = section["topology"]
        components = len(topology["components"])
        holes = sum(len(c["holes"]) for c in topology["components"])
        if sample.waterplane != WaterplaneMoments(frame, q[0], q[1:3], q[3:6], components, holes):
            _fail(ErrorCode.INTEGRITY_ERROR, "saved waterplane quantities/topology transport differs")


def save_certified_point(record, path, *, cancellation_check=None, deadline=None):
    """Exclusive atomic publication of bounded complete evidence."""
    import os
    import tempfile
    def poll():
        if cancellation_check is not None:
            if not callable(cancellation_check):
                invalid("cancellation_check must be callable")
            value = cancellation_check()
            if type(value) is not bool:
                invalid("cancellation_check must return bool")
            if value:
                _fail(ErrorCode.CANCELLED, "cancelled before certified evidence publication")
        if deadline is not None:
            if type(deadline) not in (int, float) or not math.isfinite(deadline):
                invalid("deadline must be finite monotonic time")
            if time.monotonic() >= deadline:
                _fail(ErrorCode.DEADLINE_EXCEEDED, "deadline expired before certified evidence publication")
    poll()
    inspect_certified_point(record)
    data = canonical_bytes(record)
    if len(data) > MAX_RECORD_BYTES:
        invalid("certified point evidence exceeds record limit")
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".certified-point-", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        poll()
        os.link(temporary, p)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_certified_point(path, **expected):
    p = _path(path)
    with p.open("rb") as stream:
        raw = stream.read(MAX_RECORD_BYTES+1)
    if len(raw) > MAX_RECORD_BYTES:
        invalid("certified point evidence exceeds record limit")
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                invalid("duplicate evidence JSON key")
            d[k] = v
        return d
    try:
        record = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: invalid("nonfinite evidence JSON"))
    except (ValueError, RecursionError) as exc:
        raise StabilityError(ErrorCode.INPUT_INVALID, "invalid certified point evidence JSON") from exc
    inspect_certified_point(record, **expected)
    return record
