# ANYstability — implementation and qualification plan

**Plan version:** 1.0  
**Date:** 15 October 2026  
**Project/package:** `ANYstability` / `anystability`  
**Initial target:** the ANYgeometry B1 curved-bow barge, rigid and freely floating in calm water  
**Delivery:** a standalone, headless stability engine with a command-line interface, reproducible reports and an optional graphical application  
**Status:** proposed development programme; this document does not claim that ANYstability or the pending ANYgeometry capabilities are already implemented or qualified.

## 1. Decision and independent evaluation

Proceed with a separate ANYstability repository and package. Its purpose is to turn authoritative geometry and loading information into floating equilibrium, righting-arm curves, tank-dependent stability and explicitly scoped criteria assessments. The first product should be a reliable engineering stability application, not a miniature copy of every NAPA subsystem.

The updated division of work materially improves feasibility: ANYgeometry will own exact boundary representation, section curves, certified integration and hydrostatic geometry. ANYstability should consume those results rather than build another hull clipping, NURBS or volume-integration kernel. This **supersedes the earlier proposal to use a faceted hull as the primary production hydrostatics representation**. Panel calculations remain valuable as independent comparisons, not as an automatic fallback.

The remaining difficult work is substantial but well bounded: interpreting loading conditions without double counting; solving coupled attitude and liquid states; tracking equilibrium branches and openings; propagating numerical uncertainty; and applying rules with the right scope. The small nonlinear equilibrium system is not the main computational cost. Repeated geometry and tank queries are the likely expensive operations; this is a design hypothesis to measure, not a benchmark result.

Adopt these decisions:

1. **One production geometry authority.** ANYgeometry supplies bounded quantities or typed refusal. ANYstability must neither repair hull topology privately nor silently switch to panel approximations.
2. **A genuinely independent static product.** Basic stability must not require ANYmarine, ANYsolver, Capytaine, a BEM calculation or a GUI installation.
3. **Actual liquid redistribution.** Tank liquid levels and centres of gravity are solved at the current attitude. Rule-prescribed free-surface treatments are separate, explicit assessment modes.
4. **No silent waterline perturbation.** A nearby plane is a different query. It can assist a nonlinear search, or a justified limit calculation, but cannot masquerade as the refused original condition.
5. **Separate assurance claims.** Certified geometry is not automatically a certified equilibrium root, continuous GZ curve, rule verdict or approved loading computer.
6. **Reuse current integration contracts.** Respect ANYhydro's existing hydrostatic-source semantics and ANYmarine/ANYsolver's mechanical ownership. Do not bypass their presently unadmitted compositions.

**Definition of the first useful delivery:** a saved B1 model with named loading conditions, independently defined tank quantities, explicit opening assumptions, solved draught/heel/trim, two-sided GZ results, applicable criteria results and a self-contained report, reproduced from an installed package and independently checked.

## 2. Evidence baseline and what has actually been checked

This plan is based on live reads of GitHub `main`, selected source interfaces and documentation, primary technical documentation, and the owner's supplied ANYgeometry task summary. No repository tests, B1 geometry calculations, native benchmarks or ship-stability comparisons were executed during preparation of this plan.

### 2.1 Pinned repository observations

| Repository | GitHub `main` inspected | Relevant observation |
|---|---|---|
| ANYhydro | `3ed0a171e26bc740065bce908decded0e484b09a` | Package 0.2.0, adapter 0.6.0; direct Capytaine method is now the default. Existing `HydrostaticContract` and coefficient-frame semantics are directly relevant. |
| ANYmarine | `68e206b35c7a9295886249fd5a373d6ed1b62748` | Updated ANYhydro dependency; existing coupled-static development workflow, immutable jobs/results, rigid-body input handling and explicit surface ownership. |
| ANYgeometry | `0a3a602af7880d73d2cdac140f3ae3040b744421` | Remote snapshot only. It must not be confused with the newer owner-reported local B1/H1 work. |

ANYhydro's adapter still documents buoyancy-only hydrostatic stiffness, with dry gravity handled separately. Its current source-contract eligibility code refuses `FULL` composition and `PHYSICAL_WRENCH` conversion until their missing semantics/implementation are supplied. Completeness of transported metadata does not constitute consumer admission. [G1, G2]

ANYmarine now has a coupled-static development route through ANYsolver. Therefore, do not repeat the earlier assumption that the application lacks static-equilibrium infrastructure. That route does not establish arbitrary-hull, large-angle ship-stability qualification. Its documentation explicitly requires coefficient regeneration after a changed physical equilibrium. [G4]

### 2.2 Owner-reported ANYgeometry deliveries

| Delivery | Planning status | ANYstability treatment |
|---|---|---|
| Certified arbitrary-plane waterline curves; second-plane crossings; checked persistence | Reported merged to local main | Design against the intended contract, then require actual installed-artifact admission. |
| Trimmed faces and bounded face areas | B1 work in progress; P4b review followed by P4c/P4d/P5 | Not assumed available merely because the section curve exists. |
| Closed, outward-oriented B1 hull; full volume and centroid reference | B1 pending | Required model admission gate. |
| Submerged volume/first moments/CB and waterplane moments | H1 planned after B1 | Required production provider gate. |
| Native accelerated evaluation | Expected throughput requirement | Separate correctness and performance qualification; no invented release version. |
| General multi-patch NURBS hulls with curved shared edges | Later geometry scope | Explicitly outside first-release hull qualification. |

The reported `2^-50 × hull size` point bound and approximately 0.5 ms Python point cost are **owner-supplied statements**, not independently measured in this review. Do not interpret the point bound as an error bound on all integrated moments or real-vessel dimensions. Do not infer whole-waterplane latency from the single-point timing.

At implementation start, record fresh remote and local identities without overwriting local work. Pin the delivered geometry wheel, source commit, public API version, fixture identity and certificate verifier. Capability detection, not a guessed package version, decides which analyses are available.

## 3. Product scope and release boundaries

### 3.1 Release R1: qualified engineering analysis for B1

R1 includes:

- A full physical buoyancy envelope for one rigid vessel; the B1 curved-bow barge is the mandatory curved-hull acceptance case.
- Explicit lightship/weight items, loading conditions, seawater density, gravity, body frame and reference definitions.
- Prescribed-pose hydrostatics; free-floating equilibrium; prescribed-heel calculations with either fixed or free trim.
- Independent, constant-quantity liquid tanks with supported geometry, tank calibration, actual liquid CG movement and separately selected rule free-surface treatment.
- Positive and negative heel branches, GZ curves, relevant extrema and zero crossings, areas, deck-edge and downflooding events.
- A criteria framework and bounded, versioned general-ship and pontoon assessment profiles. Full profile coverage is claimed only for implemented, applicable provisions and admitted inputs.
- JSON project/results persistence, CLI/API parity, diagnostics, CSV/JSON data export and HTML/Markdown engineering reports.
- An optional lightweight Qt/ANY3dView interface using exactly the same application services.
- An optional marine exchange bundle for supported data. Numerical consumption is separately gated; producing a bundle is not proof that a dynamics consumer accepts it.

An analytic box demonstration alone is not R1. Mock providers and panel-only demonstrations cannot satisfy the B1/H1 acceptance gate.

### 3.2 Explicitly deferred

R1 does not implement general SOLAS probabilistic damage stability, progressive/time-domain flooding, trapped-air pressure, sloshing, grain-shift analysis, unrestricted lifting/towing rules, grounding/docking equilibrium, flexible hydroelastic stability, second-generation dynamic-stability assessment, arbitrary general NURBS hull authoring, or operational loading-computer approval.

R1.1 may add limiting-KG envelopes, conventional cross-curves, loading-range optimisation, inclining-test reduction, still-water longitudinal loads and broader hull support after their individual gates. Static final damage cases are a subsequent independently qualified programme. Do not let these features delay the bounded intact-stability delivery.

### 3.3 Meaning of “NAPA light”

Aim for a small, inspectable loading-and-stability workflow, with automation and ecosystem integration as strengths. NAPA's published scope is much broader, including extensive design and damage-stability functionality. The commercial product is a scope reference, not an R1 feature checklist. [E1]

## 4. Ownership and dependency architecture

| Owner | Responsibilities | Must not acquire through this project |
|---|---|---|
| ANYgeometry | Boundary identity/topology, exact sections, closed-volume admission, face integrals, submerged geometry, waterplane moments and their bounds; native implementation of those operations | Loading conditions, liquid inventories, GZ curves or ship-rule decisions |
| ANYstability | Loading ledger; tank-content equilibrium; free-floating static equilibrium; physical righting behaviour; events, criteria, reporting and analysis provenance | A second geometry kernel; BEM/radiation solving; general coupled structural mechanics |
| ANYhydro | Hydrodynamic data and providers, existing source and coefficient-frame contracts; explicit comparison/exchange adapters where appropriate | A new authoritative ship loading ledger |
| ANYmarine | Marine project orchestration, coupled-workflow hosting and optional stability presentation | A duplicate implementation of the stability algorithms |
| ANYsolver | Mechanical assembly, dry-body gravity/inertia validation, constraints, contact and coupled mechanical solution | Ship-rule applicability or an independently edited copy of the stability loading condition |
| Existing import/meshing/view packages | Import, derived display/panel representations and rendering under their existing ownership | Authority to silently change displacement boundaries |

The dependency direction is deliberately simple:

```text
ANYgeometry  <—  ANYstability core + geometry adapter
                         ↑
                 CLI / optional Qt app
                         ↑
                 optional ANYmarine host

ANYstability results —explicit adapter→ ANYhydro / ANYmarine / ANYsolver
```

The base implementation can use NumPy and SciPy for arrays and low-dimensional numerical algorithms. Keep ANYhydro, ANYmarine, ANYsolver, xarray, Capytaine and Qt outside base imports. The production geometry adapter must require the admitted ANYgeometry artifact; analytic test development may run without it. A missing H1 capability yields `PROVIDER_UNAVAILABLE`, not a synthetic production result.

**Mass ownership:** ANYstability owns its loading-condition ledger and computes the aggregate mass and attitude-dependent CG needed for its static calculation. A marine mechanical run consumes a frozen export of that condition; ANYsolver remains the mechanical assembly authority. Export provenance and inclusion lists prevent both applications independently editing or adding the same weight. Inertia is not required for static equilibrium and must never be fabricated just to satisfy a dynamics interface. [G6]

Do not introduce another shared-package repository merely to move a few records. Begin with a small versioned, Qt-free exchange specification and explicit adapters. Extract shared contracts only after two real consumers demonstrate the need.

## 5. Required ANYgeometry handoff

This section specifies **consumer requirements**, not existing Python function names. Agree the final public API with the geometry owner; keep that mapping in one adapter.

### 5.1 Model preparation and capability declaration

A prepared geometry binding must identify:

- Model UUID, immutable content/revision identity, selected physical boundary uses, units, frame, tolerance/accuracy policy and geometry implementation identity.
- Closedness, consistent outward orientation, non-overlap and inside/outside interpretation of the selected displacement domain.
- Qualified surface families and waterplane/attitude domain, including known degeneracies and refusal classes.
- Supported quantities, requested-error controls, batched-query support and native/reference backend identity.
- How to verify or reconstruct an admission certificate through the public owner API.

A whole structural assembly is not a displacement envelope. B1 frames and internal structural faces are excluded from the external hull boundary unless they genuinely bound the selected physical volume. Intact internal tank volumes are not subtracted from hull displacement. Numerical BEM lids and zero-thickness attached plates do not create reserve buoyancy. [G5]

Do not treat a checksum alone as proof of correctness or source authenticity. Bind it to the actual verified artifact and documented producer/verifier policy.

### 5.2 Half-space query

Use the explicit geometric definition

\[
\Omega_w(n,d)=\Omega\cap\{r:n\cdot r\le d\},\qquad \|n\|=1.
\]

The provider supplies, when requested:

| Quantity | Required semantics |
|---|---|
| `V` | Submerged geometric volume, m³, with its bound |
| `J` | First volume moments `∫ r dV`, m⁴, about the declared body origin, with component bounds |
| `CB` | `J/V`, m; available only when division is well conditioned; prefer retaining `J` for arithmetic |
| `A_wp` | Waterplane area, m², including all material regions and holes correctly |
| Waterplane first/second moments | Declared in-plane basis/origin; distinguish raw and centroidal moments, including the product moment, m³/m⁴ |
| Section/event information | Curve identity, components, tangencies, crossings and relevant query-domain diagnostics |
| Result quality | Quantity-specific bounds, provenance, work counters and status, not one generic “exact” flag |

The provider must define empty and fully submerged cases. A zero waterplane area can be physically valid; it is not automatically a geometry error, although draught inversion may then be singular. An undefined CB for zero volume is absent, never `(0,0,0)`.

For multiple waterplane components, aggregate raw moments before moving to common centroidal axes. Do not sum each component's centroidal inertia without its parallel-axis contribution. Geometry-supported holes and disconnected components must retain their signed domain meaning.

Cap-free submerged integration and contour-based waterplane moments are the planned H1 algorithms. ANYstability consumes their outputs and does not build an artificial waterplane face to compensate for missing provider functionality.

### 5.3 Accuracy and repeated evaluation

Request accuracy by physical quantity and analysis need. An early equilibrium trial need not demand the same integral accuracy as a near-limit final assessment. A tighter final request must be recomputed or proven satisfied by the retained bounds; it cannot reuse a looser cached number by relabelling it.

Prepared geometry should be reusable without mutation. Query batches must preserve per-query identity, bounds and refusals. Accuracy controls, arithmetic backend and all physically relevant inputs belong in cache keys. Numerical proximity must not make two different planes the same cache entry.

Ask the owner for a public way to evaluate certified opening/sill geometry and, when available, extrema or interval behaviour over parameter ranges. **Pointwise bounds alone do not supply derivative bounds or certify an entire angle interval.** Those are additional capabilities, or require documented derivations in the consuming analysis.

### 5.4 Handoff acceptance package

Require the geometry owner to deliver public API documentation, installed wheels, reproducible source/build identity, B1 fixture, closed-volume certificate, full/submerged integral references, quantity-bound semantics, degenerate-plane cases, native/reference comparisons and a supported-domain manifest.

ANYstability admission tests must call the installed public API. A sibling checkout on `PYTHONPATH`, mocked certificate or manually copied expected numbers cannot substitute for this gate.

## 6. Domain model and persistence

Use immutable numerical inputs. Draft GUI edits may be incomplete, but only a fully validated snapshot can start an analysis.

Recommended records, whose names are **proposed**:

| Record | Essential content |
|---|---|
| `VesselDefinition` | Stable identity; body frame; full buoyancy-envelope binding; reference dimensions and draft markers; eligible compartment/opening definitions |
| `MassItem` | Stable ID; mass; body CG or explicit position rule; source; inclusion category; uncertainty where supplied |
| `LoadingCondition` | Selected weight inventory, tank contents, environment, closure states and loading-family metadata |
| `TankDefinition` / `TankContent` | Boundary binding; capacity; allowed fluid topology; density; contained quantity; gauge definitions; physical and rule treatment |
| `OpeningDefinition` | Geometry of sill/edge; closure type/state; whether immersion permits flooding; source and applicable restrictions |
| `AnalysisSettings` | Mode; angle/trim domain; residual and output tolerances; assurance policy; continuation controls; deterministic work limits |
| `EquilibriumResult` / `GZResult` | Input identity; states and components; residuals; uncertainty; branch/events; completeness; producing versions |
| `CriteriaReport` | Rule revision; applicability; per-criterion values/limits/margins; assurance; verdicts and reasons |

Use SI internally: kg, m, s, rad, N and N·m. Presentation may use tonnes, degrees and conventional naval-architecture labels, with conversions at explicit boundaries. Reject NaN, infinity, booleans passed as numeric controls and ambiguous units. Unknown is not zero.

Lightship may be a declared aggregate or a documented collection of items. Both are allowed, but an inclusion graph must prevent their overlapping contents being added twice. The same applies to FE-derived structure weights, machinery, permanent ballast and tank liquid already included in a supplied condition.

Store portable, versioned JSON manifests with content-addressed geometry/result sidecars and atomic commits. Use bounded JSON/array encodings; do not use pickle or executable input. Keep source geometry, inputs, results and assessments distinct. Cancellation retains incomplete diagnostics but cannot publish a completed result.

Geometry, density, mass, CG, fill, opening state, numerical policy or rule-version changes invalidate the appropriate dependent results. Old results remain viewable with their producing snapshot and a clear stale/detached status. Reopening a file does not rerun an expensive analysis unless explicitly requested; it performs the documented integrity/admission checks.

## 7. Coordinate and mechanical conventions

Write and test a governing convention document before implementing GZ.

A recommended initial convention is body `x` forward, `y` to port and `z` upward; world gravity is `-g e_z`. Positive heel lowers starboard. Let `R` map body coordinates into world coordinates and `t` locate the body origin. The calm waterplane at world height `η` becomes

\[
n=R^T e_z,\qquad d=\eta-e_z\cdot t
\]

in body coordinates. Keep `R` as a proper rotation matrix. Do not mutate source geometry to heel the vessel. Large world translations should not degrade the local integration accuracy.

For an initial heading-fixed chart, a possible explicit choice is

\[
R(\phi,\theta)=R_y(-\theta)R_x(\phi),
\]

where positive `θ` is bow-up. Adopt this only with matching tests and exchange mappings. The GUI must distinguish this angle from a conventional difference in fore/aft draught. Draft readings are intersections with named ship-fixed marker lines/curves, not arbitrary subtraction of world coordinates.

Compute force and moment about one declared common reference:

\[
F_b=\rho_w gV e_z,\qquad F_w=-mg e_z,
\]

\[
\tau_O=(r_B-O)\times F_b+(r_G-O)\times F_w+\tau_{\mathrm{external}}.
\]

For liquids, `r_G` depends on attitude. Component forces and moments must remain available for diagnostics. Use local reference points and compensated/stable accumulation where cancellation matters.

Generalized forces are work-conjugate to the chosen coordinates. If `J_q` maps coordinate rates into the physical velocity/twist basis, use `Q=J_q^T W`, where `W` is the physical wrench. Its derivative includes changes in `J_q`; transforming only a six-by-six matrix is not generally sufficient when a nonzero baseline wrench exists. This distinction is already explicit in ANYhydro's coefficient-frame documentation. [G3]

For the illustrative chart above, the roll-rate axis is `R_y(-θ)e_x`. With purely vertical weight and buoyancy, `τ_z=0`, so `Q_φ=cos(θ) τ_x`. A finite-trim generalized roll force is therefore not automatically the traditional horizontal righting moment. Lock down this distinction in analytic and cross-program tests rather than hiding it in a sign convention.

## 8. Floating equilibrium and hydrostatic properties

### 8.1 Distinct analysis modes

Support named modes, not an ambiguous “calculate stability” function:

- **Prescribed pose:** report hydrostatic geometry and loads at the supplied attitude and waterline; no equilibrium claim.
- **Free floating:** solve heave, heel and trim for zero vertical force and the two independent rotational residuals.
- **Prescribed heel, free trim:** hold heel and solve heave plus trim; report the remaining righting moment.
- **Prescribed heel, fixed trim:** hold both angles and solve vertical equilibrium; report both rotational residuals.

Surge, sway and yaw are gauges for the initial calm-water free vessel. Do not regularise their neutral directions with fake springs. Mooring, contact or lateral-force equilibrium belongs in the coupled mechanical workflow, not this three-variable solver.

### 8.2 Solver strategy

Start with safeguarded Newton/trust-region methods and a bracketed vertical solve where monotonicity is available. Use continuation from an admitted previous condition, a bounded line search, dimensional residual scales and explicit iteration/query budgets. Warm starts are guesses only; every new condition requires new residual verification.

At regular waterplanes, `dV/dd=A_wp` provides a useful derivative. Verify signs against the selected heave coordinate and validate other derivatives independently. Finite differences must use steps large enough relative to geometry error and small enough for convergence; do not differentiate across a topology event as though the branch were smooth.

An overloaded vessel, a near-neutral equilibrium, a missing admissible root and a geometry refusal are different outcomes. Distinguish a converged unstable equilibrium from a stable floating condition. Do not snap negative GM or a finite list back to upright.

Convergence requires both small residuals and an adequately resolved state. For a residual enclosure `[r_mid ± r_err]`, a conservative residual test uses `|r_mid|+r_err ≤ tolerance`. Merely containing zero in a broad interval proves nothing useful. A small residual is not itself a certified root-location bound near a singular Jacobian.

Return a bounded root/state only when supported by a bracket, interval verification or another documented proof. Otherwise label it an engineering-converged solution with its sensitivity/refinement evidence. Never attach a geometry certificate to a root as a substitute for root validation.

### 8.3 Initial stability and local tangent

Provide displacement, CB, waterplane centroid/moments, KB/KM/BM and GM when their classical definitions are applicable. For upright symmetric benchmarks, `BM=I_wp/V` and `GM=KB+BM-KG`, with the correct free-liquid treatment. For asymmetric/heavily trimmed conditions, report the coupled tangent rather than presenting two uncoupled GM numbers as a full stability test.

For conservative local stability with relaxed coordinates `u=(heave,trim)`, the effective heel stiffness is the Schur complement

\[
K_{\mathrm{heel,relaxed}}=K_{\phi\phi}-K_{\phi u}K_{uu}^{-1}K_{u\phi},
\]

when the constrained Hessian and nonsingularity assumptions are satisfied. Include liquid redistribution in this derivative. Do not apply the expression through a singular block or equate convergence with positive restoring stiffness.

## 9. Tanks and liquid handling

### 9.1 Physical model for R1

Admit an incompressible liquid of specified density and fixed contained quantity in an independently closed tank with an atmospheric free surface. At each vessel attitude, invert the tank's half-space volume to find its liquid level, then use bounded first moments to compute liquid CG. Include this CG in the vessel force/moment balance at every relevant equilibrium iteration.

The tank geometry is another ANYgeometry volume binding. ANYstability owns the liquid quantity and the level inversion, not a second tank-intersection engine. Begin with independently verified rectangular/prismatic tanks and add a curved tank only when its geometry family is explicitly admitted.

**Important optimisation:** at fixed orientation and liquid quantity, the liquid configuration in body coordinates does not change with a rigid vertical translation of the whole vessel. Cache that tank state across heave iterations. Recompute for changed heel, trim, quantity, density-dependent modelling assumptions or tank geometry; do not use approximate angle matching as exact cache identity.

Handle truly empty and fully filled tanks explicitly. Do not impose an artificial minimum fill. A rule convention about nominally full tanks must not alter conserved physical liquid quantity or silently press a 98%-full tank to 100%.

### 9.2 Fluid topology and connections

A geometrically connected tank can develop separated liquid pockets at certain attitudes/fills. R1 must either demonstrate the supported single communicating-liquid state over its declared domain or refuse that case. Arbitrarily redistributing liquid between disconnected pockets is not physically justified.

A future connected-tank model needs shared levels, retained pocket quantities and communication assumptions. For R1, connected tanks, cross-flooding, free communication with the sea, significant trapped gas and sloshing are explicit unsupported states. Baffles do not reduce free surface by an arbitrary factor; only a supported compartment/connectivity model or a separately justified rule treatment can do so.

### 9.3 Actual and rule free-surface modes

Keep these separately named:

- **Actual liquid redistribution:** recompute liquid geometry/CG at every attitude. No additional virtual-KG/FSM deduction for the same physical effect.
- **Rule-prescribed treatment:** use the specified fixed-fill or limiting/free-surface procedure for the selected assessment, retaining the reference loading state and adjustment ledger.

For an upright independent tank, the familiar small-angle correction is `ρ_liquid I_free_surface / m_total` in metres. It is a useful reference test, not a universal large-angle correction. The GHS technical explanation documents the distinction between actual liquid shifts and formal FSM treatments. The IS Code's free-surface provisions also distinguish initial-GM/GZ treatments and operating fill assumptions. [E6, E7]

Do not claim that calculating the actual liquid state automatically satisfies every required worst-case filling or transfer condition. Enumerate required loading/fill cases in the assessment profile.

Provide capacity and sounding/ullage tables with named gauge geometry, attitude convention and inversion validity. Reject out-of-range or ambiguous readings instead of extrapolating silently. Dynamic liquid inertia and sloshing are not supplied by static liquid-CG calculations; exports must say so.

## 10. GZ curves, continuation and event detection

### 10.1 Righting-arm definition

For weight/buoyancy vertical equilibrium without another vertical load, define the signed physical righting arm about a declared horizontal longitudinal axis `a_h` by

\[
GZ=-a_h\cdot\big[(r_B-r_G)\times e_z\big].
\]

With the Section 7 heading-fixed convention, `a_h=e_x`; positive GZ opposes positive heel. Verify `M_righting=mg GZ` against the complete physical wrench. Keep physical moment, generalized force and their coordinate mapping as separate quantities.

Do not silently use `Q_φ/(mg)` as GZ at finite trim. Do not claim that the regulatory area `∫GZ dφ` is exactly the change in potential energy under every finite-trim coordinate convention. Its regulatory definition and an actual work integral are different objects unless their equality is derived for that path.

Where an explicit external heeling moment is supported, retain the hydrostatic GZ curve and the heeling-lever curve separately. Equilibria solve the correctly signed net moment. R1 may admit a declared pure heeling couple; it must not pretend to balance an unmodelled horizontal force from wind or towing.

### 10.2 Curve construction

For each requested heel, solve the declared heave/trim problem and all relevant tank states. Use the previous admitted solution as a continuation predictor, with adaptive steps near strong curvature, events or poor conditioning. Independently verify every accepted point.

Compute both directions for asymmetric geometry, TCG, tanks or opening arrangements. Report absolute heel and the loading condition's equilibrium list distinctly. Do not recentre an asymmetric curve, assume port/starboard equivalence or erase an unstable upright solution.

Track root/branch identity through continuation. If multiple equilibria are found, retain their identity and local stability classification. If the active branch terminates or the search cannot establish its continuation, end that branch with a diagnostic; do not jump to an unrelated root merely to complete a graph.

The initial deliverable need not discover every mathematical equilibrium globally. It must accurately describe the branch it has actually followed and the domain it has checked. A search-limited result is not a proof that no equilibrium exists anywhere.

### 10.3 Events and derived metrics

Detect and localise, as applicable:

- Deck-edge immersion, relevant opening immersion and changes in closure/flooding assumptions.
- Waterplane component/topology changes and tank geometric events.
- GZ extrema, sign-changing or tangential zero contacts, and termination of an equilibrium branch.

Use certified point/event geometry and bounded root refinement where available. A sign-change-only detector can miss tangent contacts. A sampled largest value is only a sampled maximum until the intervals between samples have been assessed.

Compute areas using adaptive, event-aware quadrature in **radians**. Store the integration intervals, quadrature/refinement evidence and uncertainty. Never integrate across a missing solution segment or an unhandled flooding event as if the curve were continuous.

For an angle of vanishing stability not reached in the admitted domain, report “not reached within the analysed range” or a justified lower bound. Do not use the final sampled angle as the actual zero. Distinguish mathematical positive-GZ range from the physically usable range before downflooding and from each rule's specific range definition.

### 10.4 Openings and reserve buoyancy

An opening record must describe the relevant sill/edge, not just an arbitrary centre point. For curved or extended geometry, the critical immersed point may be neither a supplied endpoint nor the centre. Its minimum clearance needs a geometry query or a bounded extremum search over the actual opening definition.

Deck-edge immersion and downflooding are different events. Submerging a watertight deck is not automatically flooding; submerging an unprotected opening can invalidate the intact envelope. Closure status and accepted watertight/weathertight assumptions are explicit inputs, not deductions from a rendered surface. [E2, E4]

A diagnostic, closed-envelope curve beyond an opening event may be retained only with conspicuous labelling and exclusion from assessments that no longer permit that envelope. Do not accidentally count deck cargo, numerical lids or an unqualified superstructure as reserve buoyancy.

## 11. Refusal recovery and numerical honesty

Every failure carries a typed reason, the original query identity, retained diagnostics and an explicit retry policy. Proposed application categories include:

```text
PROVIDER_UNAVAILABLE         CAPABILITY_UNSUPPORTED
GEOMETRY_INVALID            QUERY_DEGENERATE
ACCURACY_UNRESOLVED          WORK_BUDGET_EXCEEDED
NO_ROOT_IN_SEARCH_DOMAIN    EQUILIBRIUM_UNRESOLVED
EQUILIBRIUM_UNSTABLE        BRANCH_TERMINATED
TANK_STATE_UNSUPPORTED      EVENT_UNRESOLVED
SOURCE_STALE                CONVENTION_UNADMITTED
```

Retain the original geometry-owner error as structured cause data. These application names must not replace or obscure its evidence. Reserve `NO_ROOT_IN_SEARCH_DOMAIN` for a demonstrated exclusion, such as an independently bounded monotone volume range that cannot support the declared mass. Exhausted iterations or failed local Newton searches are `EQUILIBRIUM_UNRESOLVED`, not proof that a root is absent.

The recovery order is:

1. Retry the **same physical query** only through documented provider controls, with bounded additional work/precision and recorded settings.
2. During a solve, use a different trial state as a search step. The final reported equilibrium must still satisfy the original loading problem and its constraints.
3. At a singular/event plane, evaluate one-sided states only under an explicit limit/bracketing procedure. Bound the target quantity using a valid continuity, monotonicity or interval argument. Nearby successful values alone do not establish such a bound.
4. If the target cannot be resolved under those rules, preserve a refused/partial result and mark dependent metrics and criteria unresolved.

No random nudges, hidden `epsilon` offsets, ignored faces, filled-in zero loads, convex-hull repairs or silent panel fallback are allowed. In particular, never report the result at `d+ε` as the result at `d`.

A genuine physical topology change is not numerical noise to smooth away. Conversely, a removable computational degeneracy should be addressed in the owner geometry operation rather than permanently excluding ordinary upright waterlines from the product.

Budgets are execution controls, not scientific qualification. Permit explicit batch sizes and bounded work expansion without baking the BEM adapter's panel/frequency ceilings into ANYstability. Repeated failure must not cause a worker to remove a gate or widen tolerances to manufacture success.

## 12. Bounds, uncertainty and result assurance

Maintain five independent dimensions:

| Dimension | Examples |
|---|---|
| Geometry assurance | Owner-certified quantity bounds; admitted boundary; exact source revision |
| Numerical solution assurance | Residual-bounded, engineering-converged, root-enclosed or unresolved |
| Continuous-curve assurance | Sampled/refined values, estimated quadrature error, rigorously bounded interval coverage |
| Assessment applicability | Applicable, not applicable, missing inputs, unsupported interpretation |
| Approval status | Engineering use only; independently reviewed scope; separately documented external approval |

### 12.1 R1 assurance level

The default R1 target is **engineering-verified analysis using certified geometry inputs**. That requires independent physical references, convergence checks, explicit numerical error estimates and conservative near-limit handling. It is not advertised as an end-to-end formal certificate.

Provide a separate `certified_bounds` policy only for analyses whose entire calculation chain is enclosed: geometric moments, liquid levels/centroids, equilibrium state, event location, curve extrema and angular integration. Where a required step has only an estimate, that policy returns unavailable or indeterminate. Do not rename a SciPy error estimate or refinement difference a certified bound.

The plan deliberately avoids making global formal certification of arbitrary GZ curves a prerequisite for the first useful engineering product. It equally forbids inheriting that claim from certified section points.

### 12.2 Error propagation

Carry bounds/estimates through division by volume, centre translation, moment assembly, tank inversion, equilibrium and derived metrics. Treat near-zero quantities with absolute tolerances. Retain covariance/dependence information when the provider supports it; otherwise use conservative enclosures and diagnose excessive widening.

Separate numerical error from uncertain physical inputs such as lightship KG, cargo location, density, fabrication dimensions and actual closure integrity. A `2^-50` numerical statement about an idealised surface says nothing by itself about the as-built ship's uncertainty.

Assessment policy must declare its allowed assurance level. Under an engineering policy, a PASS remains an engineering verdict with the stated estimates, guard bands and validation domain. Under a certified policy, missing rigorous enclosure makes a required verdict indeterminate. Neither policy labels the vessel universally “safe”.

For a minimum requirement `value ≥ limit`, a rigorous interval passes only when its lower endpoint satisfies the requirement; it fails definitively only when its upper endpoint violates it. A straddling interval is indeterminate. For engineering estimates, use the declared conservative uncertainty/guard-band policy, with a correspondingly weaker assurance label.

## 13. Criteria framework and initial profiles

### 13.1 Criteria are not embedded in the equilibrium solver

Each versioned criterion declares its source edition/amendments, applicability, required inputs, calculation definition, boundary/event policy, free-surface mode, threshold, units, allowed assurance and interpretation decisions. Use trusted code or a bounded declarative operation set; never execute arbitrary expressions from a project file or LLM-generated text.

Required vessel metadata includes the dimensions and reference definitions used by that rule, vessel/service category, propulsion/manning/cargo assumptions where relevant, operating/loading restrictions, and the selected flag/class/code basis. Do not infer statutory applicability from the repository name or hull silhouette.

The first source-capture task must reconcile the original IS Code, relevant amendments and interpretations against the intended vessel scope. The Dutch shipping-inspectorate publication register provides useful amendment/interpretation references. It is not by itself a guarantee that every later flag/class requirement has been checked. [E10]

### 13.2 Initial implementation order

**Profile A — general intact-stability curve checks.** Implement the six checks from the selected edition's Part A 2.2: the three GZ-area requirements, required righting lever at a qualifying angle, angle of maximum GZ and initial GM. The inspected text gives 0.055/0.09/0.03 m·rad for the respective areas, 0.20 m at an angle of at least 30°, maximum-GZ angle of at least 25°, and GM of at least 0.15 m. These are a source-referenced starting profile, not universal criteria for every vessel. [E3]

Explicitly test downflooding before or at 30°, shortened integration domains, several maxima and the requirement's angle range. A missing or empty required interval is not silently skipped. The lever criterion is not reduced to an unconditional test of only the sampled `GZ(30°)`.

**Profile B — general severe-wind-and-rolling check.** Implement Part A 2.3 only with verified source equations, figures, tables, empirical-domain limits and all required ship inputs. Keep its external heeling/rolling construction separate from an arbitrary calm-water moment curve. An out-of-domain empirical factor requires a supported alternative or `NOT_EVALUATED`; it must not be clipped to the nearest table value. Completing Profile A without this and other applicable provisions is not “full IS Code compliance”. [E5]

**Profile C — pontoon assessment.** Implement the selected Part B 2.2 provisions as a distinct profile. Its normal scope includes non-self-propelled, unmanned, deck-cargo pontoons with stated fullness, dimensional and opening restrictions. B1 is not automatically eligible. Verify those conditions explicitly. The pontoon wind pressure is 540 Pa, which must not be confused with the 504 Pa general weather-criterion value. Store their source identities separately. Part B recommendations are not automatically mandatory for every vessel; record the adopted flag/class/project basis for applying them. [E4, E5]

Before coding either wind profile, obtain and visually check the controlled source's figures/tables; do not reconstruct missing tabular data from a search excerpt. A future PDF source review must preserve the inspected page references.

If the delivered B1 configuration does not satisfy the adopted pontoon profile, retain it as the mandatory numerical geometry/stability benchmark and assess the applicable supported provisions honestly. Use a separately admitted eligible fixture for full pontoon-profile tests. Do not alter applicability to make the demonstration pass.

### 13.3 Verdicts and report completeness

Use `PASS`, `FAIL`, `INDETERMINATE`, `NOT_EVALUATED` and `NOT_APPLICABLE`, with reasons. “Not applicable” requires actual applicability evidence; lack of an implementation is “not evaluated”. A required unsupported criterion cannot contribute to an overall PASS.

Show measured/calculated value, limit, margin, controlling angle/loading case, error/assurance and source clause. Keep numerical success distinct from criterion success. Reports must be able to show an accurately calculated FAIL.

Current IACS UR L5 material concerns onboard stability computers; that is a separate approval objective. The official index inspected identifies Rev.4 (June 2020), but its full technical document and any later applicable approval requirements must be captured at the approval stage. No L5 tolerance table or approval claim is inferred in this plan. [E9]

## 14. Performance strategy and native delivery

### 14.1 Architecture before acceleration

Instrument whole workflows, not only point evaluation. Record geometry preparation, section/integral calls, tank-level iterations, equilibrium iterations, event searches, quadrature, serialization and display separately.

Prioritise:

- Prepared, immutable geometry and batched quantity-specific queries.
- Continuation/warm starts without reusing stale numerical answers.
- Tank orientation/fill caching across heave iterations.
- Avoiding repeated model validation when a public immutable prepared binding already proves it.
- Reusing verified calculations within a condition and avoiding unnecessary waterline display tessellation.
- Parallelism over independent conditions only after profiling; deterministic results and controlled nested thread counts.

Do not generate thousands of display points to obtain moments already available from H1. A rendering mesh is not a numerical integration requirement.

### 14.2 Native implementation

The optional native geometry backend belongs in ANYgeometry. ANYstability should not create a rival C++ implementation of section/integration logic. Reference Python remains useful for correctness, small cases and diagnosis; accelerated installed builds are expected to be important for routine throughput.

Native acceptance requires the same geometric semantics and valid error enclosures, not merely close floating-point answers. Record compiler/options/platform. Unsafe fast-math, unchecked changes to rounding semantics or reductions that invalidate claimed bounds are unacceptable in a certified route.

GPU work is not an initial priority. The equilibrium system has only a few unknowns; speeding up its dense solve is unlikely to address expensive geometry evaluation. Reconsider only if recorded end-to-end profiles justify it.

### 14.3 Registered benchmark workloads

Commit reproducible workload definitions before optimising:

| ID | Proposed workload | Measurements |
|---|---|---|
| P0 | B1 geometry preparation and one query | Cold preparation, warm query, native/reference identity |
| P1 | 1,000 distinct admitted planes, with event-adjacent cases separately identified | Wall time, p50/p95 query latency, bounds, refusal categories, memory |
| P2 | A two-sided GZ sweep with 161 requested stations in an admitted domain; no liquid tanks | End-to-end curve time; extra adaptive calls; identical physical outputs |
| P3 | Same sweep with eight supported independent tanks at nontrivial fills | Tank-query counts, cache effectiveness, equilibrium work and memory |
| P4 | 32 loading conditions with shared geometry | Throughput, bounded parallelism, warm/cold behaviour and retained evidence size |
| P5 | Refusal-heavy/event localisation and cancellation | Worst-case work bounds, termination, no leaked jobs or false success |

The station domain must cover the supported B1 case rather than force invalid planes. Terminated physical branches count as terminated results, not as successful evaluation of all 161 stations.

At S0, name the reference workstation and commit product latency/memory budgets for these workloads; at S2, measure the first real provider baseline. Until then, no runtime is represented as measured or guaranteed. Freeze the targets before the optimisation campaign. Any later budget change needs an explicit product decision with original evidence retained, not a silent relaxation after failure.

Ship benchmark commands and counters so the user can reproduce the performance claim. Do not make physical qualification depend on one computer's clock speed; report numerical qualification and throughput acceptance separately.

## 15. Optional ANYhydro / ANYmarine / ANYsolver integration

### 15.1 Standalone result bundle

Define a versioned, Qt-free static bundle containing vessel/body identities, geometry and loading hashes, `R/t`, equilibrium convention, water density/gravity, aggregate mass/CG with inclusion lists, actual buoyancy/weight wrenches, supported local tangents, opening/tank states and assurance.

Do not create fake zero-frequency BEM requests or populate empty radiation matrices to transport a static result. Frequency-domain datasets retain their current meaning. An adapter attaches applicable hydrostatic declarations only to a real, semantically compatible dataset.

### 15.2 Existing source contract is mandatory

Map to the current public `HydrostaticContract`, including source role, force basis, derivative convention, actual baseline wrench and immutable source binding. Prefer a **buoyancy-only** contribution where the mechanical consumer separately assembles gravity. Keep combined restoring behaviour available for standalone stability, without relabelling it buoyancy-only. [G1, G2]

The inspected ANYhydro implementation transports `FULL` metadata but does not admit its composition, and refuses `PHYSICAL_WRENCH` conversion pending the appropriate rate/coordinate mapping. An ANYstability exporter cannot bypass those gates. Add supported conversion/decomposition only through an independently tested, owner-reviewed extension; otherwise the bridge returns `CONVENTION_UNADMITTED`. [G2]

For a tangent defined as `C = -∂Q/∂q`, include the derivative of the work-conjugacy map and all required baseline terms. Dry gravity, liquid gravity/redistribution and buoyancy must each have exactly one owner in the assembled mechanical model. Do not feed combined restoring stiffness into a consumer that already adds the same gravity contribution.

### 15.3 Equilibrium and geometry binding

A coefficient-frame re-expression at one fixed equilibrium is not a new physical equilibrium. ANYhydro's constant frame-map utilities do not convert upright linear stiffness into nonlinear restoring behaviour at a new heel or trim. [G3]

When adopting a new static condition, invalidate dependent wave coefficients unless a documented consumer-specific validity policy genuinely admits reuse. A new waterline/attitude may require new wetted panels and a new BEM calculation. ANYmarine already exposes the corresponding regeneration warning. [G4]

Derived panel geometry must retain its exact source binding, approximation controls and physical surface roles. An upward physical closure surface is not a downward numerical BEM lid. Zero-thickness sheets, lids, tank walls and the displacement envelope remain explicitly distinct. [G5]

### 15.4 Coupled mechanics and mass transfer

Use ANYmarine's existing coupled-static orchestration for a future moored/contacting system. ANYstability supplies admitted nonlinear hydrostatic contributions and state evaluation; it does not independently solve the same moorings or structural constraints.

The initial exchange may provide mass/CG without inertia. ANYmarine/ANYsolver must refuse dynamics preparation when valid inertia is absent, as their current input contract already requires. Static liquid redistribution does not supply a sloshing model or a qualified dynamic inertia model. [G6]

Geometry/wrench transport tests, actual numerical consumer admission and coupled physical validation are three separate tests. A successful round trip alone is not completed marine coupling.

## 16. Application, CLI and reporting

Use the headless service layer as the only calculation entry point. Proposed user workflows are:

```text
validate → hydrostatics → equilibrium → gz → assess → report
```

The eventual CLI may expose these as `python -m anystability <command>`, but these are proposed commands, not presently available ones. Every command accepts saved inputs and explicit settings, returns machine-readable status and a useful nonzero exit code on failure. Batch runs preserve per-condition failures rather than replacing them with missing rows.

The optional desktop application should provide a vessel/tank/opening tree, an editable loading table, a heel/trim/waterline view, GZ plot, criteria table and diagnostics. Clicking a GZ point should display its **solved** pose, liquid surfaces, relevant openings and numerical status—not a graphical rotation unrelated to the calculation.

Re-use public ANY3dView and existing ecosystem visual conventions. Keep a simple application shell in the ANYstability repository; an ANYmarine-hosted panel can consume the same services later. Do not import ANYmarine's private GUI modules into the stability engine.

Run analyses in cancellable workers with immutable inputs. An edit during a run affects a subsequent job only. Loading an example or report must never silently launch a BEM computation. Label reference-panel previews and synthetic/test fixtures distinctly.

Each engineering report must include:

- Vessel and geometry source; full loading ledger and tank/closure assumptions; density/gravity/units and axes.
- Analysis mode, reference definitions, solved state, residuals, assurance and supported domain.
- GZ curves with direction, equilibrium list, event markers, gaps and excluded post-downflooding regions.
- Per-criterion values/limits/margins, applicability, controlling cases and source revision.
- Reproduction command, input/result hashes, package/native identities and unresolved limitations.

Generate CSV/JSON tables plus HTML/Markdown reports in R1. A PDF rendering option is secondary to reproducibility and should not embed separate numerical logic. Never state class/flag approval without the actual scope-specific approval record.

## 17. Proposed repository structure and automation boundary

Keep modules cohesive; the tree is a starting structure, not a mandate to create empty files for every future feature.

```text
ANYstability/
  pyproject.toml
  README.md
  AGENTS.md
  src/anystability/
    __init__.py
    __main__.py
    domain.py
    loading.py
    conventions.py
    bounds.py
    errors.py
    providers/
      protocol.py
      anygeometry_adapter.py
    equilibrium.py
    tanks.py
    gz.py
    events.py
    criteria/
      registry.py
      applicability.py
      is_code_general.py
      is_code_weather.py
      is_code_pontoon.py
    persistence.py
    services.py
    cli.py
    reporting.py
    exchange.py
    adapters/                  # optional hydro/marine/solver imports
    qtapp/                     # optional desktop imports
  tests/
    unit/
    analytic/
    geometry_contract/
    physical_regression/
    adversarial/
    interop/
    installed/
  examples/
  benchmarks/
  docs/
    adr/
    theory/
    qualification/
    source_register.md
    capability_matrix.md
  tools/
```

Proposed provider operations are `prepare`, `capabilities`, `evaluate_halfspace`, `evaluate_batch`, `verify_binding` and opening-geometry queries. Their final signatures belong in a reviewed interface specification. Test-only analytic providers live under tests or an explicitly marked reference namespace; production selection cannot accidentally choose them.

Publish the ordinary Python API and a bounded JSON command schema suitable for other agents or ANYworkbenchAI. An LLM may prepare inputs or explain a report, but it must not decide whether a numerical refusal can be ignored, change a rule threshold or invent certificate evidence. All calculations and verdicts come from deterministic services.

Apply the established ANY ecosystem licensing and third-party-notice policy. Keep optional heavy dependencies out of the minimal package and verify that the built wheel does not accidentally include private benchmark data, large development evidence or sibling source trees.

## 18. Qualification programme

### 18.1 Three layers of independent evidence

**Analytical physics references.** Use boxes, rectangular tanks and other admitted primitives with equations independently derived in the repository. For a rectangular barge upright in its wall-sided domain,

\[
V=LBT,\quad KB=T/2,\quad I_{\mathrm{roll}}=LB^3/12,\quad BM=B^2/(12T).
\]

Before deck immersion or bottom/chine emergence, and under the corresponding wall-sided assumptions, a useful fixed-trim reference is

\[
GZ=\sin\phi\left(GM+\frac{BM}{2}\tan^2\phi\right).
\]

Document its derivation and validity limits. Do not extrapolate it to the curved bow or beyond its geometric domain. Use independently derived finite-fill tank moments and manufactured equilibrium cases based on independent analytic data, not outputs from the provider being tested.

**Geometry-to-panel comparisons.** Compare H1 quantities with an independently implemented panel reference over refinement levels. Capytaine's official hydrostatics facilities provide useful geometric quantities without a radiation/diffraction solve, but the comparison must verify the actual rigid-DOF path, frame, reference origin and gravity/buoyancy convention. A general-DOF approximation must not be mistaken for the rigid hydrostatic reference. [E8]

A comparison that changes only the provider while retaining ANYstability's equilibrium/GZ post-processing primarily checks geometry/provider agreement. It is not independent verification of that shared equilibrium/GZ algorithm.

**Whole-workflow comparison.** Use public reproducible reference cases or matched results from an independently implemented stability calculation. A commercial NAPA/GHS/other comparison is valuable when lawful source models and results are available, but a bare screenshot or undocumented summary is not a reproducible oracle. Freeze geometry, masses, density, trim policy, liquid treatment and opening definitions before comparing. Do not make initial public reproducibility depend on inaccessible private literature.

### 18.2 Required case matrix

| Case group | Required evidence |
|---|---|
| Q01: primitive hydrostatics | Volume, CB, waterplane moments and derivative signs against independent formulas |
| Q02: coordinate invariance | Translated/rotated representations, reference-point changes and mirrored conventions give physically equivalent results |
| Q03: vertical equilibrium | Root bracket, conserved displacement, final bounded residual; zero-area and overloaded cases handled honestly |
| Q04: coupled equilibrium | Known asymmetric LCG/TCG conditions; free heel/trim; stable, unstable and near-neutral roots |
| Q05: wall-sided GZ | Both signs; small-angle slope; valid-domain analytical curve; event-limited termination |
| Q06: tank inversion | Empty/full/partial fills; fill conservation; accurate CG; sounding/ullage inversion; unsupported pockets refused |
| Q07: free-liquid stability | Small-angle tensor/FSM check and large-angle redistribution; no double counting of correction or liquid mass |
| Q08: B1 exact route | Installed H1 provider, real owner fixture, bound/provenance checks, actual equilibrium and GZ |
| Q09: events | Curved/extended sills, deck-edge distinction, tangential contacts, downflooding before a required integration endpoint |
| Q10: branch behaviour | Multiple roots, continuation reversal, branch termination and repeatability without silent root jumping |
| Q11: curve metrics | Known maxima/zeros/areas, missing intervals, adaptive refinement and sampled-vs-global claims |
| Q12: rule assessments | Each threshold on both sides and exactly at the boundary; interval-straddling cases; applicability and missing-input tests |
| Q13: native path | Reference/native output and certificate semantics; precision-sensitive and event-adjacent cases on installed builds |
| Q14: exchange | Mass inclusion, baseline/tangent roles, work-conjugacy, stale source binding, unsupported FULL/physical-wrench admission |
| Q15: persistence/jobs | Save/reopen, corrupted/tampered sidecars, concurrent edits, cancellation, portable paths and stale reports |
| Q16: application | CLI/API/GUI numerical identity; installed minimal environment; no accidental optional imports or fake completed examples |

Where the provider admits multiple waterplane regions, add a separated-pontoon and holed-waterplane fixture to verify moment aggregation. Unsupported geometry is an explicit capability test, not a fabricated success case.

### 18.3 Initial engineering tolerances

Commit case-specific tolerances before qualification. The following are **proposed numerical development targets, not class-rule tolerances or measured performance**:

| Output/check | Initial target for metre-scale and ship-scale R1 fixtures |
|---|---|
| Vertical equilibrium | Total residual enclosure within `1e-8 × m g` |
| Rotational equilibrium | Total moment residual enclosure within `m g × 1e-6 m` for solved rotational DOFs |
| Well-conditioned state refinement | Heave change below `1e-6 m`; angle changes below `1e-6 rad`, in addition to residual checks |
| GZ numerical refinement | Below `1e-4 m` over the admitted curve, with tighter evaluation near a rule boundary |
| GZ-area numerical refinement | Below `1e-5 m·rad` on every reported assessment interval |
| Resolved event-angle bracket | Width at most `0.02°`, unless an assessment requires tighter localisation |
| Native/reference quantities | Both consistent with an independently established reference and the declared bounds; numerical closeness alone is insufficient |

Scale tiny synthetic test models through explicit nondimensional policies instead of blindly applying ship-size absolute thresholds. Geometry accuracy must be requested tightly enough to meet downstream targets; failure to achieve it is unresolved, not converged.

Independent panel/commercial comparison tolerances must account for their distinct geometry/model error. Define them from the reference's convergence and intended use before examining the final comparison; do not replace them with a convenient percentage after a discrepancy. Near-zero GZ and off-diagonal moments require absolute checks.

### 18.4 B1 release experiment

The mandatory B1 package must contain at least: a centred reference loading, a fore/aft-shifted loading, a transverse-offset loading, a partial-liquid condition, a low-stability condition and an opening-limited condition. Add an overloaded/no-root fixture as a negative test. The actual values are to be selected from the delivered B1 geometry and committed with the benchmark, not invented in this plan.

For each positive case: save the authoritative model and full input ledger; solve the appropriate initial equilibrium; calculate both heel branches with the chosen trim policy; evaluate openings/tanks; refine; compare available independent references; assess the declared criteria; and regenerate the report from stored inputs/results.

For negative cases: show the expected FAIL, unstable, refused or unresolved outcome. Product acceptance is not restricted to examples that appear green.

## 19. Implementation phases and exit gates

Use the phases below as executable work packages. The critical path is **S0 → S1 → S2 → S3/S4 → S5 → S6 → S9**, with performance work beginning at S2 and application work proceeding against stable services. Do not finish every possible integration before delivering the independently usable core.

### S0 — freeze contracts, applicability and acceptance criteria

**Can start now.**

Deliver the package ownership ADR, pose/GZ convention ADR, mass-inclusion policy, provider requirement document, public source register, B1 capability/dependency ledger, qualification case definitions and benchmark budgets. Reconcile current ANYmarine/ANYhydro interfaces with the pinned observations rather than assuming their older README summaries are complete.

Confirm which B1 fixture/dimensions and operating assumptions will be available. Determine whether the pontoon profile is applicable; record why. Obtain controlled rule material and interpretation decisions for the profiles to be implemented.

**Exit gate:** independent review finds no competing geometry authority, ambiguous mass/gravity owner, unresolved convention hidden in an implementation default, or claimed availability of pending H1 APIs. Benchmark/tolerance definitions are versioned before qualification runs. Every upstream requirement has an owner and acceptance test.

### S1 — standalone foundation and analytic vertical slice

**Can start now using explicitly test-only analytic providers.**

Implement immutable records, input validation, weight aggregation, error/assurance statuses, project/result persistence, provider protocol, service layer and CLI skeleton. Implement a complete analytic-box path from loading condition to equilibrium/report as a development proof. Add optional-import and deterministic serialization tests.

Publish the capability table so an installation without H1 honestly reports unavailable production geometry support. The analytic provider remains visibly a reference/test route.

**Exit gate:** the minimal installed wheel runs Q01–Q03/Q15/Q16 foundation tests without marine/BEM/GUI packages; corrupted inputs and duplicate masses fail; a mock or analytic result cannot acquire B1/H1 qualification status. A real report is generated from the analytic case, not a screenshot-only demo.

### S2 — admit the real B1/H1 geometry provider

**Production work depends on the B1 and H1 artifacts. Protocol tests can be prepared earlier.**

Implement the one public ANYgeometry adapter, prepared bindings, quantity/bounds conversion, owner-certificate verification, batched queries and error translation. Do not edit or duplicate the owner's integration implementation to make tests pass.

Exercise the installed B1 fixture, arbitrary admitted plane orientations, full/empty limits and adversarial event planes. Run independent primitive checks and the first panel-refinement comparison. Record P0/P1 timing and the real geometry-query cost breakdown.

**Exit gate:** actual installed H1 quantities and bounds pass Q01/Q02/Q08 geometry checks; source identity survives persistence; unsupported/degenerated queries remain typed refusals; no default panel fallback exists. The gate cannot pass from local owner status text alone.

### S3 — floating equilibrium and local stability

**Algorithm/reference work may run in parallel with S2; B1 acceptance requires S2.**

Implement the four analysis modes, scaled force/moment residuals, safeguarded root solve, final residual verification, draft-marker readings, hydrostatic tables, tangent checks and stable/unstable/unresolved classification. Document and test the work-conjugate coordinate mapping.

**Exit gate:** Q03–Q05 pass with fixed weights, finite trim and asymmetric CG. The B1 centred/offset conditions converge with actual H1 evidence. Overload, singularity and search-domain termination give correct distinct results. Prescribed-pose output never appears as a solved equilibrium.

### S4 — liquid tanks and coupled loading conditions

**Depends on admitted tank-volume queries; can develop alongside S3.**

Implement fixed-quantity level inversion, liquid CG, empty/full states, sounding/calibration, attitude-sensitive caching, tank-state integration into equilibrium and the exclusive actual/rule-treatment ledger. Add capacity and topology-domain admission checks.

**Exit gate:** Q06/Q07 pass; tank volume is conserved at each accepted state; pure heave does not trigger unnecessary body-relative tank re-solves; tilted partial tanks alter vessel equilibrium correctly; unsupported communication/pocket states refuse; actual liquid movement plus duplicate FSM or duplicate liquid mass is impossible by construction or rejected.

### S5 — complete GZ/event/metric workflow

**Depends on S3 and S4.**

Implement both heel directions, free/fixed-trim continuation, branch records, opening/deck/tank events, adaptive sampling, extrema/zero searches, event-aware quadrature and complete/partial curve reporting. Add assurance propagation and conservative near-limit handling.

**Exit gate:** Q05/Q08–Q11 pass, including the complete B1 tank-equipped GZ workflow. Every reported metric is traceable to a resolved interval; missing values are not bridged; finite-trim physical moments and generalized forces obey the documented mapping. Closed-envelope post-downflooding diagnostics cannot influence an inapplicable intact assessment.

### S6 — versioned criteria and engineering reports

**Source/applicability design starts at S0; real numerical acceptance depends on S5.**

Implement Profile A, then the scope-appropriate pontoon and weather profiles with their own source/data/domain gates. Implement loading-case coverage, per-criterion outcomes, margin/uncertainty display, rule revisioning and HTML/Markdown/CSV/JSON export.

Do not make every global ship-rule family part of this phase. Close the explicitly selected profiles completely, while exposing other provisions as unsupported rather than gradually accumulating undocumented exceptions.

**Exit gate:** Q12 passes with independent formula fixtures and both passing/failing cases. No incomplete assessment becomes an overall PASS. Every applicable implemented clause is reproducible from captured source/interpretation metadata. The B1 report states actual applicability; it does not claim statutory approval.

### S7 — measured throughput and native qualification

**Begins with the first real S2 profiles; overlaps S3–S6.**

Optimise query use, batching, prepared-state reuse and tank caching in ANYstability. Send measured geometry bottlenecks to the ANYgeometry native owner. Validate delivered native artifacts independently and re-run P0–P5 plus sensitive numerical cases.

**Exit gate:** numerical/native qualification passes without loosened physics tolerances; registered performance targets are measured with reproducible commands on the named platform; failing throughput is reported separately from physics. Cancellation/refusal paths remain bounded. No certification-sensitive arithmetic was weakened to meet a speed goal.

### S8 — desktop workflow and optional marine exchange

**GUI/service work can start after S1; real desktop acceptance follows S5/S6.**

Implement the optional-install desktop front end and static exchange bundle. Exercise API/CLI/GUI identity, producing-state visualisation, saved example loading, cancellation, stale results and report generation. Add optional adapters using the actual existing marine/hydro contracts.

The R1 desktop front end is an application deliverable; installation remains optional. A fully coupled marine dynamics consumer is not an R1-core blocker. Where current consumer admission is missing, deliver the bundle, explicit refusal and exact prerequisite instead of an apparently integrated mock.

**Exit gate:** Q14–Q16 pass for the claimed scope; the installed desktop completes the same B1 workflow as the CLI; no private sibling-module imports are needed; unsupported hydrostatic role/rate-map combinations are refused. Any claim of actual numerical marine consumption requires a separate real-consumer test, not only transport checks.

### S9 — independent qualification, release and handoff

**Depends on all mandatory core/application gates and documented disposition of optional integration gates.**

Run the complete admitted case matrix and B1 experiment from clean installed artifacts. Have an independent reviewer check physical definitions, reference independence, numerical failure handling, tank accounting and rule applicability. Rebuild the portable example and report from the shipped CLI.

**Exit gate:** the final scope-specific evidence manifest passes; source/wheel identities match; documentation contains no stale pending capability presented as released; supported platforms and remaining limitations are precise. Deliver a working R1 application, not only a library API or an evidence directory. Record separate status for full-chain certification, general-hull support and marine coupling.

## 20. Parallel execution and multi-agent operating rules

Use one coordinating implementation owner and small bounded workstreams. Avoid several agents independently changing the same numerical convention or provider interface.

| Workstream | Owned work | Interfaces / restrictions |
|---|---|---|
| Root/integration | S0, public API, package/CI, integration and final handoff | Owns cross-package decisions and source-of-truth status |
| Geometry liaison | Provider adapter, capability admission and contract tests | Does not modify ANYgeometry's kernel without an agreed owner task |
| Equilibrium/GZ | Conventions, residuals, continuation, events and metrics | Consumes frozen provider and tank contracts |
| Tanks/loading | Inventory, liquid inversion, inclusion/correction policies | No duplicate nonlinear equilibrium engine |
| Criteria/reporting | Sources, applicability, rule fixtures and reports | Consumes numerical results; cannot weaken solver/geometry gates |
| Application/exchange | CLI/GUI, persistence workflow and optional bridges | No private numerical implementations in UI code |
| Independent verification | Analytic derivations, adverse cases, review and reproduction | Must not validate an algorithm solely against the same implementation |

Agents may work in parallel where contracts are frozen. Use isolated branches/worktrees and explicit file ownership; avoid large competing edits to `domain.py`, shared serializers or package exports. Read repository `AGENTS.md` and current upstream contracts before editing. Do not run unbounded worker hierarchies or unrelated whole-ecosystem campaigns.

Parallel tasks should hand off code, exact tests/commands/results, source identities, unresolved issues and a short status statement. Review must distinguish transport evidence, geometric evidence and physical verification. Failed attempts and invalidated reports are retained in a concise evidence ledger.

Prefer focused tests while developing, a registered physical regression set at integration, and clean installed tests at release. Avoid rebuilding every dependency or rerunning expensive campaigns for unrelated documentation changes. Never reduce quality by removing a failing physical test from the accepted scope without an explicit documented scope decision.

Future implementation should reconcile local and GitHub `main` at authorised handoff, preserving unrelated user changes and active upstream work. This planning task itself does not create repositories, modify code or push branches.

## 21. Upstream dependencies, blockers and stop conditions

| Dependency or risk | Required action | Work that can continue meanwhile |
|---|---|---|
| H1 quantities not yet delivered | Record `WAITING_FOR_H1`, exact missing capability and acceptance fixture | Domain, analytic solver/tanks, criteria definitions, persistence and GUI/service work |
| B1 shell admission incomplete | Do not qualify curved-hull production calculations | Analytic references and contract/adverse tests |
| Native geometry not yet admitted | Use qualified reference evaluation within honest work limits; report performance pending | Numerical/physics qualification on bounded workloads |
| Pointwise bounds insufficient for continuous certification | Keep engineering assurance; define additional bounds/proofs needed | Useful converged/refined curves with correct assurance labels |
| No applicable complete rule profile for a B1 configuration | Report partial/applicable scope; use another admitted eligible profile fixture | B1 numerical qualification and generic criterion engine |
| Current hydrostatic consumer cannot admit the export | Preserve explicit unsupported bridge status | Standalone analysis and portable exchange bundle |
| Independent comparison disagrees | Diagnose geometry, conventions, liquid treatment and numerics separately | Unrelated workstreams; no acceptance of the failing scope |

Do not create a fake geometry backend, hard-code B1 result tables or introduce mesh fallback merely to remove an upstream blocker. Do not leave a blocker as “needs investigation”: identify the missing public operation, owner, reproducible input and pass condition.

A failed geometry certificate, unbounded physical root, unsupported tank connectivity or missing applicable criterion is a non-success for that analysis. It does not require halting all unrelated development. This distinction permits useful progress without false completion.

## 22. Reserved extensions and their additional gates

### 22.1 Limiting KG and cross-curves

Store enough loading-family information now to support these later. A limiting-KG calculation must define which weights move, whether total mass/LCG/TCG remain fixed, which tanks retain quantity and how free trim is treated. Re-run the actual constrained equilibrium and assessment at each trial where necessary.

The shortcut `GZ = KN - KG sin(φ)` is admissible only under its compatible geometry, reference, loading and trim assumptions. A free-trim curve can depend on KG/LCG through the solved trim; do not assume one table serves every such condition. Tank redistribution creates further state dependence.

Search for the controlling admissible boundary, retain the governing criterion and do not assume global monotonicity or one connected feasible KG interval without verification. This extension requires independent envelope references, branch/domain checks and bounded near-limit classification.

### 22.2 Still-water loads and structural coupling

Add longitudinal buoyancy/weight distributions and hull-girder loads only through a separately verified slicing/load-distribution contract. A single resultant CG/CB is insufficient to reconstruct a unique longitudinal load distribution.

For pressure transfer to shells, require resultant force and moment conservation, separate external and internal pressures, and explicit reference frames/source surfaces. The structural solver owns stress and resistance assessment. Do not count the same tank pressure or weight twice in the structural model.

### 22.3 Static damage stability

Reserve compartment/opening/connectivity identity in the data model, but do not implement empty “supported” damage modes. The first damage programme should address selected final-equilibrium flooding states, with explicit permeability and communication assumptions.

Adopt one consistent formulation for each flooding regime. Added water and lost buoyancy must not be mixed accidentally; their equivalence requires matched definitions and assumptions. A fixed added cargo mass is not a general substitute for a compartment open to the sea. Independently verify residual equilibrium, liquid/free-surface effects and usable stability range before adding broader scenario generation.

Probabilistic SOLAS assessment, cross/progressive flooding, transient fluid dynamics and onboard emergency decision support require additional rule/physical/approval programmes. They are not automatic consequences of passing intact B1 calculations.

## 23. Definition of done and handoff contents

R1 is complete only when the applicable items below are demonstrated, not merely listed in documentation:

- [ ] Separate ANYstability repository/package; base imports and installed CLI work without marine/BEM/GUI packages.
- [ ] Real installed B1/H1 provider admitted; full geometry and numerical-source identities retained.
- [ ] Weight/tank inclusion is unambiguous; no duplicated mass, gravity or free-surface correction.
- [ ] Prescribed pose, free floating, free-trim GZ and fixed-trim GZ are distinctly implemented and tested.
- [ ] Partial tanks redistribute liquid correctly; empty/full and unsupported states behave honestly.
- [ ] Two-sided curves, physical moment conventions, events, metrics and gaps pass independent tests.
- [ ] Refusal recovery cannot silently change the reported physical problem.
- [ ] Assurance distinguishes certified geometry, numerical convergence, full bounds, rule applicability and approval.
- [ ] Selected criteria profiles are source-versioned and completely tested within their stated scope; missing provisions cannot yield overall PASS.
- [ ] B1 loading cases and their reports reproduce from shipped input files and commands.
- [ ] Independent analytic, geometric and whole-workflow evidence is distinguished and retained.
- [ ] Native correctness and measured throughput status are documented independently.
- [ ] Optional-install desktop app reproduces the CLI result, including cancellation/staleness and refusal display.
- [ ] Static bundle and optional bridges respect existing hydro/marine contracts; actual consumer admission is claimed only where tested.
- [ ] Installed artifacts, supported platforms, license/dependency manifests and capability matrix match the source.
- [ ] Independent final review and remaining limitations are included in the handoff.

Deliver source, built installable artifacts, a minimal installation guide, a complete B1 example project, reproduction commands, engineering report, machine-readable results, case/tolerance definitions, source register, performance report, qualification manifest and a short continuation note for deferred scope.

The final handoff should answer: **what works, for which hull/loading/rule domain, at which assurance level, from which exact artifacts, with what measured evidence, and what still refuses or remains unsupported?**

## 24. Source register

The references below support the baseline observations and technical/rule distinctions. Proposed architecture, tolerances, phases and acceptance tests are design decisions in this plan, not claims that the sources prescribe them. All web/repository observations were made on 15 October 2026.

### Repository sources (pinned)

**[G1] ANYhydro README, lines 1–210 inspected.** Package scope, buoyancy-only adapter convention and direct-method default.  
<https://github.com/audunarn/ANYhydro/blob/3ed0a171e26bc740065bce908decded0e484b09a/README.md>

**[G2] ANYhydro hydrostatic contract source, lines 1–250 and 600–815 inspected.** Roles, baseline data, force/derivative semantics, immutable binding and current composition refusals.  
<https://github.com/audunarn/ANYhydro/blob/3ed0a171e26bc740065bce908decded0e484b09a/src/anyhydro/hydrostatic_contract.py>

**[G3] ANYhydro coefficient frames, lines 1–135 inspected.** Fixed-equilibrium frame transformations and finite-pose limitation.  
<https://github.com/audunarn/ANYhydro/blob/3ed0a171e26bc740065bce908decded0e484b09a/src/anyhydro/frames.py>

**[G4] ANYmarine coupled static equilibrium development workflow.** Existing solver orchestration, immutable stages and coefficient-regeneration requirement.  
<https://github.com/audunarn/ANYmarine/blob/68e206b35c7a9295886249fd5a373d6ed1b62748/docs/NATIVE_STATIC_EQUILIBRIUM.md>

**[G5] ANYmarine owned hydrodynamic surfaces.** Physical hull, sheet and numerical-lid distinctions and source/staleness binding.  
<https://github.com/audunarn/ANYmarine/blob/68e206b35c7a9295886249fd5a373d6ed1b62748/docs/SURFACE_PROJECTS.md>

**[G6] ANYmarine rigid-body mass inputs.** Explicit CG/inertia, absent-is-unknown handling and ANYsolver mechanical ownership.  
<https://github.com/audunarn/ANYmarine/blob/68e206b35c7a9295886249fd5a373d6ed1b62748/docs/RIGID_BODY_INPUTS.md>

**[G7] ANYmarine README.** Selected sections covering services, job/persistence architecture, newer native workflows and application limitations. Some status passages describe historical slices and are not a substitute for capability-specific source/acceptance checks.  
<https://github.com/audunarn/ANYmarine/blob/68e206b35c7a9295886249fd5a373d6ed1b62748/README.md>

**[G8] ANYgeometry remote-main snapshot.** Remote identity only; the owner's newer local B1/H1 deliveries were supplied in the planning request and have not been execution-verified here.  
<https://github.com/audunarn/ANYgeometry/commit/0a3a602af7880d73d2cdac140f3ae3040b744421>

**[U1] ANYgeometry owner handoff supplied with this request.** Local section-curve status; B1 P4b–P5 work; planned H1 integrals; point-bound/per-point performance statements; first-hull and later NURBS scope. Preserve this text as a dated planning input, then replace availability assumptions with actual artifact receipts during S0/S2.

### External primary technical and regulatory material

**[E1] NAPA, ship-design software scope.** Product scope reference only.  
<https://www.napa.fi/software-and-services/ship-design/software/napa/>

**[E2] IMO, Ship Design and Stability.** General statutory/approval context. This overview is not a consolidated implementation source for every current criterion.  
<https://www.imo.org/en/ourwork/safety/pages/shipdesignandstability-default.aspx>

**[E3] 2008 IS Code, Part A 2.2, published statutory text reproduction.** General GZ-property criteria. The retrieved site's publication frame identifies 2024; revalidate applicable edition/amendments for release.  
<https://www.imorules.com/GUID-CC04FC48-9A3D-487D-BB76-7B6064FA75CD.html>

**[E4] 2008 IS Code, Part B 2.2, published statutory text reproduction.** Pontoon applicability and assessment distinctions. Same source-control caveat as E3.  
<https://www.imorules.com/GUID-EA80C173-4634-4493-9F1C-8245BC202EC5.html>

**[E5] 2008 IS Code, Part A 2.3, published statutory text reproduction.** Severe wind and rolling. Implement from a checked controlled source, including figures/tables, not search excerpts.  
<https://www.imorules.com/GUID-5A600BFB-05C0-4CA7-A16B-F9FD101E4FAC.html>

**[E6] Creative Systems/GHS, Free Surface Moments.** Publisher explanation of actual liquid shifts versus formal FSM procedures.  
<https://ghsport.com/support/FSM.HTM>

**[E7] 2008 IS Code, Part B 3.1, published statutory text reproduction.** Free-surface treatment and operating-fill assumptions.  
<https://www.imorules.com/GUID-1CD30840-FE5A-429E-8C02-925EA466D8F2.html>

**[E8] Capytaine, Hydrostatics user documentation.** Hydrostatic quantities, rigid/general-DOF distinctions and mass-distribution limitations. Pin the installed comparison version and documentation snapshot when registering tests.  
<https://capytaine.org/stable/user_manual/hydrostatics.html>

**[E9] IACS, UR L5 official index, Rev.4 (June 2020).** Onboard stability-computer approval context. Only the official index/version was verified here; the full PDF technical requirements were not inspected.  
<https://iacs.org.uk/resolutions/unified-requirements/ur-l/ur-l5-rev4-cln>

**[E10] Netherlands shipping-inspectorate publication register, MSC.267(85).** Amendment/interpretation references for source-control work.  
<https://puc.overheid.nl/nsi/doc/PUC_719736_14/1/>

The original IMO resolution PDF could not be retrieved for full inspection during this planning review. Consequently, this document does not claim a complete current consolidated rule audit or visual verification of every normative table/figure. S0/S6 require that source-capture step before a rule profile is released. Preserve citations, edition/hash and interpretation records without redistributing copyrighted rule publications beyond permitted terms.

---

**Controlling direction:** finish a reproducible, independently verified B1 intact-stability application on the real ANYgeometry H1 provider. Keep geometry exactness, numerical assurance, rule scope and marine integration honest; expand each only when its own evidence is complete.
