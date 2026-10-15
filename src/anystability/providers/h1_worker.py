"""Bounded, installed-package subprocess entry point for H1 development jobs."""
import subprocess
import sys
from ..errors import ErrorCode, StabilityError
from ..validation import canonical_bytes, decode_json, exact, invalid, real
from .anygeometry_h1 import H1DevelopmentProvider, H1Query, _opt_in
from .protocol import HalfSpace


def execute_job(data):
    d = exact(data, {"action", "allow_development", "query", "snapshot"}, "H1 development job")
    _opt_in(d["allow_development"])
    if d["action"] not in {"export_b1", "query_b1", "query_snapshot"}:
        invalid("unknown H1 job")
    if (d["action"] == "query_snapshot") != (d["snapshot"] is not None):
        invalid("only query_snapshot accepts snapshot data")
    if d["action"] == "export_b1" and d["query"] is not None:
        invalid("export_b1 does not accept a waterplane query")
    query = None
    if d["action"] != "export_b1":
        q = exact(d["query"], {"plane", "order", "rtol"}, "H1 query")
        q["plane"] = HalfSpace(**exact(q["plane"], {"normal", "offset_m"}, "halfspace"))
        query = H1Query(**q)
    provider = (H1DevelopmentProvider.from_snapshot(canonical_bytes(d["snapshot"]), allow_development=True)
                if d["action"] == "query_snapshot" else H1DevelopmentProvider.b1(allow_development=True))
    if query is None:
        return dict(status="exported_development_geometry", snapshot=decode_json(provider.snapshot_bytes()),
                    production_qualified=False)
    return provider.evaluate(query)


def run_job(data, *, wall_seconds=120.):
    timeout = real(wall_seconds, "H1 process wall limit", positive=True)
    if timeout > 300:
        invalid("H1 process wall limit cannot exceed 300 seconds")
    _opt_in(data.get("allow_development"))
    try:
        completed = subprocess.run([sys.executable, "-I", "-m", __name__],
            input=canonical_bytes(data), capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise StabilityError(ErrorCode.WORK_BUDGET_EXCEEDED, "H1 process wall limit exceeded; no result admitted",
                             wall_seconds=timeout) from exc
    if completed.returncode:
        try:
            error = decode_json(completed.stderr)
            code = ErrorCode(error["code"])
        except (StabilityError, ValueError, KeyError, TypeError):
            raise StabilityError(ErrorCode.PROVIDER_UNAVAILABLE, "H1 worker failed before returning a typed result",
                                 exit_code=completed.returncode, stderr=completed.stderr[-1000:].decode(errors="replace"))
        raise StabilityError(code, error["message"], **error.get("details", {}))
    return decode_json(completed.stdout)


def main():
    try:
        data = decode_json(sys.stdin.buffer.read(2_000_001))
        result = execute_job(data)
        encoded = canonical_bytes(result)
        if len(encoded) > 2_000_000:
            invalid("H1 worker result exceeds the transport limit")
        sys.stdout.buffer.write(encoded + b"\n")
        return 0
    except StabilityError as exc:
        sys.stderr.buffer.write(canonical_bytes(exc.to_dict()) + b"\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
