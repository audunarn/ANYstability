# ANYstability

Standalone ship-stability development for the ANY ecosystem.

**Current scope: S1 analytical foundation, not the B1/H1 production release.**
ANYgeometry remains the production geometry authority. This initial implementation
has no admitted H1 adapter and never substitutes a mesh or analytical model for it.

## Implemented

- Immutable SI loading records, stable input identities and duplicate physical-mass checks.
- Explicit body/pose/force conventions and a consumer-owned hydrostatics protocol.
- An opt-in analytical box reference: horizontal-plane volume, first moments,
  centre of buoyancy and waterplane second moments.
- Bounded-work vertical equilibrium at fixed zero heel/trim, with final residual
  verification and the remaining rotational moments reported, not hidden.
- Atomic JSON projects and content-addressed result snapshots, stale-result
  detection, explicit reproduction, and Markdown/HTML reports.
- A standalone CLI that does not import marine, BEM, geometry or GUI dependencies.

The reference provider refuses tilted and degenerate waterplanes. Numerical
errors are labelled engineering estimates, not certified geometry bounds.
Free-floating heel/trim, tanks, GZ, rules, GUI and marine numerical coupling
are later plan phases. No result from this version has production qualification.

## Install and run

Python 3.11 or newer. The foundation has no runtime dependencies.

```bash
python -m pip install .
python -m anystability capabilities
python -m anystability example ./reference-project
python -m anystability validate ./reference-project --allow-reference
python -m anystability equilibrium ./reference-project --allow-reference
```

The last command prints a `result_object_hash`. Use that value in:

```bash
python -m anystability verify ./reference-project RESULT_OBJECT_HASH
python -m anystability report ./reference-project RESULT_OBJECT_HASH report.md --verify
python -m anystability report ./reference-project RESULT_OBJECT_HASH report.html --format html
python -m anystability export-json ./reference-project RESULT_OBJECT_HASH result.json
```

Create a custom reference condition by editing a copy of
`examples/reference_box_input.json` and running
`anystability import-json input.json ./new-project`. File creation is exclusive;
existing projects and reports are not silently overwritten.

## Development

```bash
python -m pip install .
python -m unittest discover -s tests -v
```

Run the same tests from a clean installed-wheel environment for handoff. See
`docs/IMPLEMENTATION_PLAN.md` for the full controlling plan,
`docs/capability_matrix.md` for the implemented scope and `CHECKPOINT.md` for
continuation instructions and measured evidence. A green foundation test suite
is not B1/H1 admission, R1 completion or statutory approval.

## License

MPL-2.0. See `LICENSE` and `NOTICE`.
