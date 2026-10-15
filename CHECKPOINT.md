# ANYstability checkpoint — S0/S1 start

Date: 2026-10-15. Package: 0.1.0.dev0. This is an implementation handoff, not R1.

## Delivered in this slice

S0 foundation ownership/pose/mass/provider contracts, controlling plan retained,
capability/dependency ledger, analytical derivation and registered case targets.
S1 immutable records, strict JSON/numeric validation, disjoint physical-mass
inclusion, opt-in analytical box hydrostatics, fixed-attitude vertical solver,
retained force/moment residuals, portable atomic project/results storage,
explicit result reproduction, CLI and Markdown/HTML reports.

The reference example solves 410000 kg in 1025 kg/m^3 water on a 20x10x4 m box:
expected draft 2 m; calculated draft 1.999999988824129 m, 33 provider queries,
vertical residual -0.022467559669166803 N. This is not B1 geometry or GZ evidence.

## Executed verification

55 unittest cases passed, no failures/skips, against a clean installed wheel
on Linux x86_64 / Python 3.13.5 from outside the repository. None of NumPy,
SciPy, ANYgeometry, ANYhydro, ANYmarine, ANYsolver, Capytaine, xarray or PySide6
was installed or imported in that environment. CLI create/validate/solve/save/
verify/report/export and independent analytical/negative checks are included.
Detailed machine-readable evidence: docs/qualification/s1_evidence.json.

One initial source-run import test found the host's preloaded NumPy rather than
an ANYstability import. The test now checks newly introduced imports; the clean
venv independently verified actual absence. No numerical failure was suppressed.
Review in this task was self-review and executed tests, not independent review.
Windows/Linux 3.11/3.13 CI is configured; observe the actual run before claiming
remote coverage. The original wheel hash is in the evidence file; rebuilding can
change archive metadata without changing the source.

## Remaining gates and next actions

1. Complete S0 independent contract review and controlled rule-source/applicability
   work before any statutory profile. No criteria or overall PASS exists in S1.
2. S2: obtain the actual installed ANYgeometry B1/H1 artifact receipt and public
   API, extend the sample with general waterplane basis/first moments and owner
   certificate verification, then implement the one owner adapter and Q08.
3. S3 reference work may proceed meanwhile: free-floating heave/heel/trim,
   safeguarded continuation and local stability. Do not turn the horizontal
   reference box into a private general hull clipping engine.
4. S4-S9 remain not implemented/unqualified: tanks, GZ/events, rules, native
   throughput, GUI/exchange and final B1 qualification.

The production selector deliberately returns PROVIDER_UNAVAILABLE regardless
of whether an arbitrary ANYgeometry version happens to be installed. Only a
real admitted adapter changes that status. Analytical/mock transport checks
cannot be substituted for the H1 receipt or B1 physical qualification.
