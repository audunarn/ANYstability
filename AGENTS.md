# ANYstability implementation rules

Read CHECKPOINT.md, docs/capability_matrix.md and docs/IMPLEMENTATION_PLAN.md first.
Implement bounded, tested slices of the controlling plan; do not fill the tree
with empty future modules. Keep the handoff and installed capability table honest.

- ANYgeometry alone owns production boundary/section/integral geometry. No private
  clipping kernel, geometry repairs, automatic nudges or panel fallback here.
- Only installed-artifact admission may enable B1/H1. Owner status text, mocks,
  reference boxes and passing transport tests cannot confer that admission.
- Keep analytical references explicitly opted-in and in the reference namespace.
- SI internally. Body x forward/y port/z up. R=Ry(-trim)Rx(heel). Distinguish
  physical torque, horizontal GZ and generalized roll force at finite trim.
- Fixed-attitude vertical equilibrium does not solve heel/trim or prove stability.
- Never double-count weight components, liquid mass, free-surface correction,
  gravity or buoyancy. No invented inertia to please a marine interface.
- Separate geometry bounds, solver estimates, continuous-curve assurance,
  rule applicability and external approval. Never upgrade one from another.
- Validate inputs and preserve typed refusals, exact queries and original causes.
- Use immutable input snapshots, bounded work and atomic persistence. No pickle,
  arbitrary executable input, source-relative imports or optional imports in core.
- Tests must include analytic expectations independently derived from the code,
  adverse/corrupt inputs, installed-wheel execution and original failure records.
- Do not change unrelated repositories or live user environments. Preserve active
  upstream work. Recheck main before publishing; never force-push user changes.
- Do not claim an independent review, remote CI success or qualification without
  actual evidence. Local self-review and unit tests must be named as such.
