"""Installed CLI; structured refusals and nonzero status on numerical/I/O failure."""
import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .conventions import Pose
from .domain import Project
from .errors import ErrorCode, StabilityError
from .persistence import (atomic_write, load_project, load_result, read_bytes,
                          save_project, save_result)
from .reporting import html_report, markdown_report
from .services import analyze, analyze_integrals, capabilities, example_project, provider_for, reproduce
from .validation import decode_json, canonical_bytes


def parser():
    p = argparse.ArgumentParser(prog="anystability", description="Ship stability foundations; S2 owner integration; explicit development modes only")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    sub.add_parser("provider-check", help="read-only H1 admission status; exits 2 while blocked")
    handoff = sub.add_parser("inspect-handoff", help="check delivery bytes, never execute/admit owner code")
    handoff.add_argument("manifest")
    export = sub.add_parser("h1-export-b1", help="export the real owner B1 half-hull development fixture")
    export.add_argument("output")
    export.add_argument("--allow-development", action="store_true")
    export.add_argument("--wall-seconds", type=float, default=120.)
    h1 = sub.add_parser("h1-query", help="real H1 quadrature; estimates, not certified geometry")
    source = h1.add_mutually_exclusive_group(required=True)
    source.add_argument("--b1", action="store_true")
    source.add_argument("--snapshot")
    h1.add_argument("--allow-development", action="store_true")
    h1.add_argument("--draft-m", type=float, required=True, help="body-origin plane offset, not a draught-marker reading")
    h1.add_argument("--heel-rad", type=float, default=0.)
    h1.add_argument("--trim-rad", type=float, default=0.)
    h1.add_argument("--order", type=int, default=24)
    h1.add_argument("--rtol", type=float, default=1e-8)
    h1.add_argument("--wall-seconds", type=float, default=120.)
    h1.add_argument("--output")
    example = sub.add_parser("example", help="save the explicitly analytical reference box")
    example.add_argument("project")
    create = sub.add_parser("import-json", help="validate input JSON and save a new project")
    create.add_argument("input")
    create.add_argument("project")
    for command in ("validate", "equilibrium", "hydrostatics", "integrals"):
        s = sub.add_parser(command)
        s.add_argument("project")
        s.add_argument("--allow-reference", action="store_true")
        if command in {"hydrostatics", "integrals"}:
            s.add_argument("--draft-m", type=float, required=True)
            s.add_argument("--heel-rad", type=float, default=0.0)
            s.add_argument("--trim-rad", type=float, default=0.0)
        if command == "integrals":
            s.add_argument("--accuracy-json", help="explicit absolute errors for all five quantity groups")
    for command in ("verify", "report", "export-json"):
        s = sub.add_parser(command)
        s.add_argument("project")
        s.add_argument("result_hash")
        if command in ("report", "export-json"):
            s.add_argument("output")
        if command == "report":
            s.add_argument("--format", choices=("markdown", "html"), default="markdown")
            s.add_argument("--verify", action="store_true")
    return p


def execute(args):
    if args.command in {"h1-export-b1", "h1-query"}:
        from .providers.anygeometry_h1 import H1Query, _opt_in
        from .providers.protocol import HalfSpace
        from .providers.h1_worker import run_job
        _opt_in(args.allow_development)
        job = dict(action="export_b1", allow_development=True, query=None, snapshot=None)
        if args.command == "h1-query":
            n, d = Pose(args.heel_rad, args.trim_rad, -args.draft_m).waterplane()
            job.update(action="query_b1" if args.b1 else "query_snapshot",
                       query=H1Query(HalfSpace(n, d), args.order, args.rtol).to_dict(),
                       snapshot=None if args.b1 else decode_json(read_bytes(args.snapshot)))
        result = run_job(job, wall_seconds=args.wall_seconds)
        if args.command == "h1-export-b1":
            atomic_write(args.output, canonical_bytes(result["snapshot"]) + b"\n")
            return dict(status=result["status"], output=args.output, production_qualified=False)
        if args.output:
            atomic_write(args.output, canonical_bytes(result) + b"\n")
        return result
    if args.command == "provider-check":
        from .providers.handoff import provider_status
        return provider_status()
    if args.command == "inspect-handoff":
        from .providers.handoff import inspect_handoff
        return inspect_handoff(args.manifest)
    if args.command == "capabilities":
        return capabilities()
    if args.command in {"example", "import-json"}:
        project = example_project() if args.command == "example" else Project.from_dict(decode_json(read_bytes(args.input)))
        identity = save_project(project, args.project)
        return dict(status="saved", input_hash=identity, project=str(Path(args.project)),
                    production_qualified=False)
    project = load_project(args.project)
    if args.command == "integrals":
        from .providers.integrals import Accuracy
        accuracy = (None if args.accuracy_json is None else
                    Accuracy.from_dict(decode_json(read_bytes(args.accuracy_json))))
        return analyze_integrals(project, pose=Pose(args.heel_rad, args.trim_rad, -args.draft_m),
                                 allow_reference=args.allow_reference, accuracy=accuracy)
    if args.command == "validate":
        provider = provider_for(project, allow_reference=args.allow_reference)
        return dict(status="reference_inputs_valid", input_hash=project.identity,
                    provider=provider.binding.to_dict(), production_qualified=False)
    if args.command in {"hydrostatics", "equilibrium"}:
        kwargs = {}
        if args.command == "hydrostatics":
            kwargs["pose"] = Pose(args.heel_rad, args.trim_rad, -args.draft_m)
        result = analyze(project, calculation=args.command, allow_reference=args.allow_reference, **kwargs)
        identity = save_result(result, args.project)
        return dict(status="completed_reference", result_object_hash=identity,
                    result=result.to_dict())
    record = load_result(args.project, args.result_hash)
    if args.command == "verify":
        reproduced = reproduce(record)
        return dict(status="reference_reproduced", result_hash=reproduced.identity,
                    stale=record.is_stale(project), production_qualified=False)
    if args.command == "export-json":
        data = canonical_bytes(record.to_dict()) + b"\n"
    else:
        renderer = markdown_report if args.format == "markdown" else html_report
        data = renderer(record, verify=args.verify, current_project=project).encode("utf-8")
    atomic_write(args.output, data)  # Exclusive; never silently replace a user's file.
    return dict(status="written", output=str(Path(args.output)), stale=record.is_stale(project))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(canonical_bytes(result).decode())
        return 2 if args.command in {"provider-check", "inspect-handoff"} else 0
    except StabilityError as exc:
        print(canonical_bytes(exc.to_dict()).decode(), file=sys.stderr)
        return 2
    except OSError as exc:
        error = StabilityError(ErrorCode.IO_ERROR, str(exc))
        print(canonical_bytes(error.to_dict()).decode(), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
