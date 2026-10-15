"""Bounded JSON, atomic manifests and content-addressed immutable sidecars.

Portable project directories are not a defence against a concurrent hostile
local process replacing files while they are being checked. Symlinks/traversal
are refused in the normal trusted-workspace threat model. No pickle or code.
"""
import hashlib
import os
from pathlib import Path
import tempfile
from .domain import Project
from .errors import ErrorCode, StabilityError
from .services import AnalysisRecord
from .validation import (MAX_JSON_BYTES, canonical_bytes, decode_json, digest,
                         exact, integer, invalid)


def read_bytes(path):
    p = Path(path).absolute()
    if any(v.is_symlink() for v in (p, *p.parents)):
        raise StabilityError(ErrorCode.IO_ERROR, "symbolic-link input is refused", path=str(p))
    with p.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        invalid("file exceeds the two-megabyte foundation limit")
    return data


def atomic_write(path, data, *, overwrite=False):
    p = Path(path).absolute()
    if not isinstance(data, bytes) or len(data) > MAX_JSON_BYTES:
        invalid("output must be bounded bytes")
    if any(v.is_symlink() for v in (p, *p.parents)):
        raise StabilityError(ErrorCode.IO_ERROR, "symbolic-link output is refused")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".anystability-", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, p)
        else:
            # Atomic exclusive publication: do not overwrite a racing creator.
            os.link(temporary, p)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _root(path, *, create=False):
    p = Path(path).absolute()
    if any(v.is_symlink() for v in (p, *p.parents)):
        raise StabilityError(ErrorCode.IO_ERROR, "project path contains a symbolic link")
    if create:
        p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise StabilityError(ErrorCode.IO_ERROR, "project directory does not exist", path=str(p))
    objects = p / "objects"
    if objects.is_symlink():
        raise StabilityError(ErrorCode.IO_ERROR, "object directory is a symbolic link")
    return p


def _put(root, payload):
    data = canonical_bytes(payload)
    identity = hashlib.sha256(data).hexdigest()
    p = root / "objects" / (identity + ".json")
    if p.exists():
        if read_bytes(p) != data:
            raise StabilityError(ErrorCode.INTEGRITY_ERROR, "existing content-addressed object is corrupt")
    else:
        try:
            atomic_write(p, data)
        except FileExistsError:
            if read_bytes(p) != data:
                raise StabilityError(ErrorCode.INTEGRITY_ERROR, "concurrent object content mismatch")
    return identity


def _get(root, identity):
    digest(identity, "sidecar hash")  # Construct the path ourselves; no input path traversal.
    data = read_bytes(root / "objects" / (identity + ".json"))
    if hashlib.sha256(data).hexdigest() != identity:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "sidecar content hash mismatch")
    return decode_json(data)


def save_project(project, path, *, overwrite=False):
    root = _root(path, create=True)
    identity = _put(root, project.to_dict())
    atomic_write(root / "project.json", canonical_bytes(dict(schema_version=1, kind="anystability_project",
                                                           input_hash=identity)), overwrite=overwrite)
    return identity


def load_project(path):
    root = _root(path)
    m = exact(decode_json(read_bytes(root / "project.json")), {"schema_version", "kind", "input_hash"}, "project manifest")
    integer(m["schema_version"], "manifest version", 1, 1)
    if m["kind"] != "anystability_project":
        invalid("not an ANYstability project manifest")
    project = Project.from_dict(_get(root, m["input_hash"]))
    if project.identity != m["input_hash"]:
        raise StabilityError(ErrorCode.INTEGRITY_ERROR, "project is not in canonical normalized form")
    return project


def save_result(record, path):
    root = _root(path)
    # The result includes its producing inputs even if current project has changed.
    return _put(root, dict(kind="anystability_result", payload=record.to_dict()))


def load_result(path, object_hash):
    root = _root(path)
    data = exact(_get(root, object_hash), {"kind", "payload"}, "result sidecar")
    if data["kind"] != "anystability_result":
        invalid("not an ANYstability result")
    return AnalysisRecord(canonical_bytes(data["payload"]).decode())
