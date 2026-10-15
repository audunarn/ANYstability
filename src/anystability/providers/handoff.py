"""Read-only S2 handoff inspection; never imports or executes owner/user code.

A receipt proves neither a correct integral nor a trusted producer. Inspection
reports byte integrity only. Production admission additionally needs a reviewed
owner adapter, the actual installed owner verifier, and real B1/Q08 evidence.
"""
from email.parser import BytesParser
import hashlib
from importlib import metadata
from pathlib import Path, PurePosixPath
import stat
import zipfile
from ..errors import ErrorCode, StabilityError
from ..validation import decode_json, digest, exact, integer, invalid, sequence, text

KIND = "anystability-geometry-handoff-v1"
REQUIRED_ROLES = frozenset({"wheel", "b1_fixture", "api_document", "bound_semantics",
                            "supported_domain", "verification_evidence"})
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
BLOCKING_GATES = ("REVIEWED_OWNER_API_MAPPING", "INSTALLED_OWNER_CERTIFICATE_VERIFICATION",
                  "REAL_B1_Q08", "PANEL_REFINEMENT_COMPARISON", "P0_P1_MEASUREMENTS")


def provider_status() -> dict:
    """Metadata discovery alone cannot enable a provider. No optional imports."""
    try:
        installed_version = metadata.version("ANYgeometry")
    except metadata.PackageNotFoundError:
        installed_version = None
    return dict(provider_id="anygeometry_h1", available=False,
                code=ErrorCode.PROVIDER_UNAVAILABLE.value, stage="S2_consumer_preparation",
                installed_distribution_version=installed_version,
                installed_owner_verifier="not_executed", reviewed_adapter="not_implemented",
                Q08="blocked_not_executed", blocking_gates=list(BLOCKING_GATES),
                reason="B1/H1 public API and installed owner evidence are not admitted in this build")


def require_production_provider():
    status = provider_status()
    raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, status["reason"], provider_status=status)


def _relative(value):
    text(value, "artifact path")
    p = PurePosixPath(value)
    if (p.is_absolute() or "\\" in value or ":" in value or
            any(part in {"", ".", ".."} for part in value.split("/"))):
        invalid("artifact paths must be normalized relative POSIX paths")
    return p


def _no_links(path: Path):
    # Check the lexical path before resolve(), including directory ancestors.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise StabilityError(ErrorCode.IO_ERROR, "symlink paths are refused", path=str(part))


def _read_artifact(base: Path, relative: str, maximum: int) -> bytes:
    p = base.joinpath(*_relative(relative).parts)
    _no_links(p)
    try:
        if not p.is_file() or p.stat().st_size > maximum:
            raise StabilityError(ErrorCode.IO_ERROR, "missing/non-file/oversized artifact", path=relative)
        # No extraction, importing, build/install or execution. Bounded read.
        with p.open("rb") as f:
            data = f.read(maximum+1)
        if len(data) > maximum:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "artifact read limit exceeded")
        return data
    except OSError as exc:
        raise StabilityError(ErrorCode.IO_ERROR, "cannot read artifact", path=relative) from exc


def _wheel_metadata(data: bytes, version: str) -> dict:
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_BUNDLE_BYTES:
                raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "wheel inventory exceeds inspection bounds")
            names = []
            for i in infos:
                # Directory entries are allowed, but not unsafe names or links.
                _relative(i.filename.rstrip("/"))
                if stat.S_ISLNK(i.external_attr >> 16):
                    invalid("wheel symlink member refused")
                names.append(i.filename)
            if len(set(names)) != len(names):
                invalid("duplicate wheel member names")
            members = [i for i in infos if i.filename.endswith(".dist-info/METADATA")]
            if len(members) != 1 or members[0].file_size > 1000000:
                invalid("wheel requires one bounded distribution METADATA file")
            with z.open(members[0]) as f:
                raw = f.read(1000001)
            if len(raw) > 1000000:
                invalid("wheel METADATA exceeds limit")
            msg = BytesParser().parsebytes(raw)
            if len(msg.get_all("Name", [])) != 1 or len(msg.get_all("Version", [])) != 1:
                invalid("wheel metadata must contain one Name and Version")
            if msg["Name"].lower().replace("-", "_") != "anygeometry" or msg["Version"] != version:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, "wheel distribution/version differs from declaration")
            return dict(name=msg["Name"], version=msg["Version"], members=len(infos),
                        inspection="metadata_only_not_installability_or_authenticity")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError) as exc:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "wheel archive cannot be inspected") from exc


def inspect_handoff(manifest_path) -> dict:
    """Check a bounded local delivery bundle; success NEVER means admission.

    Missing required roles are reported without executing anything. Changed bytes,
    unknown fields, executable verifier instructions and unsafe paths are refused.
    The manifest is a proposed consumer handoff format, not an ANYgeometry codec.
    """
    path = Path(manifest_path).absolute()
    _no_links(path)
    base = path.parent
    raw = _read_artifact(base, path.name, 2000000)
    d = exact(decode_json(raw), {"kind", "provider_id", "source_commit", "distribution_version",
                                "owner_api_version", "artifacts"}, "geometry handoff")
    if d["kind"] != KIND or d["provider_id"] != "anygeometry_h1":
        invalid("unsupported handoff kind/provider")
    sha = d["source_commit"]
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        invalid("source commit must be a lowercase 40-character Git SHA")
    for name in ("distribution_version", "owner_api_version"):
        text(d[name], name)
    artifacts, roles, paths = [], set(), set()
    for value in sequence(d["artifacts"], "handoff artifacts", 16):
        item = exact(value, {"role", "path", "sha256"}, "artifact")
        role = item["role"]
        if not isinstance(role, str) or role not in REQUIRED_ROLES or role in roles:
            invalid("unknown/duplicate artifact role")
        _relative(item["path"])
        if item["path"] in paths:
            invalid("artifact paths must be unique")
        digest(item["sha256"], "artifact sha256")
        roles.add(role); paths.add(item["path"]); artifacts.append(item)
    inventory, wheel, total = [], None, 0
    for item in artifacts:
        data = _read_artifact(base, item["path"], MAX_ARTIFACT_BYTES)
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "handoff exceeds byte budget")
        actual = hashlib.sha256(data).hexdigest()
        if actual != item["sha256"]:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "handoff artifact checksum mismatch",
                                 role=item["role"], expected=item["sha256"], actual=actual)
        if item["role"] == "wheel":
            wheel = _wheel_metadata(data, d["distribution_version"])
        inventory.append(dict(**item, bytes=len(data), status="bytes_match_declaration"))
    return dict(kind=KIND, status="blocked_not_admitted", manifest_sha256=hashlib.sha256(raw).hexdigest(),
                declared_source_commit=sha, declared_owner_api_version=d["owner_api_version"],
                artifacts=inventory, wheel_metadata=wheel, missing_roles=sorted(REQUIRED_ROLES-roles),
                owner_code_executed=False, source_authenticity="not_verified",
                installed_artifact_equivalence="not_verified", Q08="not_executed",
                production_qualified=False, blocking_gates=list(BLOCKING_GATES),
                provider_status=provider_status())
