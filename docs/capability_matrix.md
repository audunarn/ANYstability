# Capability matrix — initial implementation

| Capability | Status | Evidence / next gate |
|---|---|---|
| S0 ownership, pose, mass and provider contracts | Implemented for foundation | ADRs; independent review and controlled rule sources still pending |
| S1 immutable loading/validation | Implemented | Duplicate IDs/component inclusion; numeric/schema/immutability tests |
| S1 reference box hydrostatics | Implemented, reference only | Q01 subset: horizontal cuts, volume/CB/moments/full/empty |
| S1 coordinate mapping | Implemented, reference checks | Q02 subset: proper rotations, waterplane and virtual power |
| S1 vertical equilibrium | Implemented, fixed attitude only | Q03 subset: analytic drafts, offset torque, overload, neutral, budgets |
| S1 persistence/CLI/report | Implemented, reference only | Q15/Q16 foundation subset; installed-wheel reproduction |
| ANYgeometry B1/H1 production adapter | NOT IMPLEMENTED / NOT ADMITTED | S2 installed owner receipt and Q08 required |
| Free-floating heel/trim and local stability | NOT IMPLEMENTED | S3 |
| Tanks and free-surface handling | NOT IMPLEMENTED | S4 |
| GZ, branch/event/continuous metrics | NOT IMPLEMENTED | S5 |
| Statutory criteria and applicability | NOT IMPLEMENTED | S6; no overall PASS allowed |
| Native throughput qualification | NOT MEASURED | S7 on real owner geometry |
| GUI and marine numerical consumption | NOT IMPLEMENTED | S8; preserve current upstream source-contract refusals |
| R1 / general hulls / formal full-chain bounds | NOT QUALIFIED | S9 and separate extension gates |

Tests cover the named foundation subsets, not the full Q01-Q16 matrix.
The shipped installation exposes the same production refusal through capabilities.
Installed ANYgeometry by itself does not enable the still-unimplemented adapter.
User-reported local main and GitHub remote main are distinct availability records.
