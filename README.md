# ANYstability

Standalone ship-stability development for the ANY ecosystem. Version 0.1.0.dev2.

**S1/S2 foundation plus real, explicitly opted-in ANYgeometry H1 queries.**
The H1 source returns quadrature estimates, not certified quantity bounds.
Certified production admission is still blocked. No mesh or analytical fallback
substitutes for the owner geometry.

## Implemented scope

The dependency-free foundation includes immutable SI loading records, physical
mass inclusion checks, explicit pose/wrench conventions, a reference box,
fixed-attitude vertical equilibrium, portable JSON projects, immutable result
snapshots, reproduction and Markdown/HTML reports. General integral transport
and interval postprocessing retain their separate assurance requirements.

The new optional `H1DevelopmentProvider` computes volume, CB, waterplane area/CF,
centroidal second moments, product moment and geometric BM using the pinned
owner API. Its result format is distinct from the certified integral contract.
It uses owner serialization and closure checks, preserves source identity and
refusals, and runs CLI jobs in an installed child with a wall limit. Base imports
and reference commands do not import geometry, marine, BEM or GUI dependencies.

The B1 fixture is a **closed half-hull bow segment**, not a complete barge.
Free-floating heel/trim, tanks, GZ, rules, GUI and marine numerical coupling remain
later phases. No result from this version has production or statutory approval.

## Reference foundation

Python 3.11 or newer; no runtime dependencies for this route:

```bash
python -m pip install .
python -m anystability capabilities
python -m anystability example reference-project
python -m anystability equilibrium reference-project --allow-reference
```

Use the printed `result_object_hash` in:

```bash
python -m anystability verify reference-project RESULT_OBJECT_HASH
python -m anystability report reference-project RESULT_OBJECT_HASH report.md --verify
python -m anystability report reference-project RESULT_OBJECT_HASH report.html --format html
python -m anystability export-json reference-project RESULT_OBJECT_HASH result.json
```

Custom inputs use `examples/reference_box_input.json` and `import-json`.
S1 dev0/dev1 results remain reproducible. File creation is exclusive; existing
projects, reports and exports are never silently overwritten.

## Install the pinned real H1 development route

Use a disposable environment rather than changing an active owner environment.
The unchanged ANYgeometry version number 0.4.5 is insufficient: this adapter
verifies the entire installed 134-file Python payload. Non-editable pure-Python
builds only; other owner revisions or native binaries are explicitly refused.

From the ANYstability checkout, with Git available:

```powershell
python -m venv .venv-h1
$py = ".\.venv-h1\Scripts\python.exe"
& $py -m pip install .
$env:ANYGEOMETRY_BUILD_NATIVE = "0"
$env:ANYGEOMETRY_REQUIRE_NATIVE = "0"
$env:ANYGEOMETRY_DISABLE_NATIVE = "1"
git init h1-owner-source
git -C h1-owner-source config core.autocrlf false
git -C h1-owner-source remote add origin https://github.com/audunarn/ANYgeometry.git
git -C h1-owner-source fetch --depth 1 origin 21d0637bc7f090e03b88f785f75ea1821489db6d
git -C h1-owner-source checkout --detach FETCH_HEAD
& $py -m pip install .\h1-owner-source

& $py -m anystability h1-export-b1 b1-snapshot.json --allow-development
& $py -m anystability h1-query --snapshot b1-snapshot.json `
    --draft-m 1.75 --allow-development --output b1-query.json
& $py -m anystability h1-query --snapshot b1-snapshot.json `
    --draft-m 1.75 --heel-rad 0.05 --trim-rad 0.03 --allow-development
```

`--draft-m` is the BODY-origin waterplane offset, not a draught-marker reading.
The B1 bottom is at BODY z=0.5 m. Angles use ANYstability's radians convention
`R=Ry(-trim)Rx(heel)`, not the owner's heel helper. `--b1` can replace `--snapshot`
to build the actual owner fixture for a query. Default order is 24, the normalized
order-doubling acceptance is 1e-8, and the child wall limit is 120 seconds.

The library accepts explicit `H1Query(HalfSpace(normal, offset))` requests after
`H1DevelopmentProvider.b1(allow_development=True)` or preparation of explicit
owner geometry. Reuse prepared geometry for multiple queries. Library call-count
and order limits are not an internal owner wall-time bound; use the CLI worker
when a hard wall limit is needed.

## Assurance and verification

Every H1 query records `owner_quadrature_estimate`, null quantity-error bounds,
`production_qualified=false`, and that equilibrium/criteria were not evaluated.
A matching checksum proves source equivalence, not numerical certification.
`provider-check` and `inspect-handoff` remain read-only and exit 2 while certified
admission is blocked. No automatic plane perturbation, tolerance relaxation or
fallback is implemented.

```bash
python -I -m unittest discover -s tests -v
```

Run unit tests against an installed wheel. Real-owner checks are separate:
`tools/verify_h1_owner.py` builds both wheels, proves owner source/wheel/installed
byte equivalence, then executes `tests/integration/check_h1_owner.py` outside
source checkouts. Its independent ellipse and panel references are tests only,
not an ANYhydro/ANYmarine campaign or a replacement geometry engine.

See `CHECKPOINT.md`, `docs/capability_matrix.md`, `docs/provider_contract.md`,
`docs/adr/0004-real-h1-quadrature-adapter.md`, and
`docs/qualification/s2_h1_development_evidence.json` for evidence and remaining
gates. The full controlling `docs/IMPLEMENTATION_PLAN.md` is unchanged.

## License

MPL-2.0. See `LICENSE` and `NOTICE`.
