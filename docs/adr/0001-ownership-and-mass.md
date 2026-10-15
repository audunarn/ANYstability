# ADR 0001 — ownership and immutable mass ledger

Accepted for S0/S1, 2026-10-15. Scope: foundation, not full R1 qualification.

ANYgeometry owns production volumes, section curves, integrals and certificates.
ANYstability owns loading conditions, tank inventories, free-floating equilibrium,
GZ, events and assessment. ANYhydro remains the hydrodynamic data/provider owner.
ANYmarine hosts coupled workflows. ANYsolver owns mechanical assembly in those
workflows; static loading aggregation here does not require a mechanical solver.

S1 deliberately uses only the standard library. No matrix solution, BEM, GPU,
GUI, CAD or source geometry package is needed for the vertical analytical proof.
The production provider is unavailable until the S2 installed H1 contract is
admitted. The initial consumer protocol is NOT a guessed public ANYgeometry API.

Each mass item declares the indivisible physical components it covers. Covers
must be nonempty and disjoint across the included ledger, even when item IDs
are different. An aggregate lightship must list the components already included
so a second machinery/structure item cannot overlap them. This is a declared
inclusion contract, not automatic inference of physical identity from names.
Mass, CG and density are finite SI values. Static calculations require no inertia.

GeometrySource stores canonical immutable JSON; only its registered provider
interprets the definition. Source hashes identify exact supplied definitions,
including distinct integer/float encodings; they are not geometric-equivalence
proofs. Names and project settings belong to the producing input identity.
