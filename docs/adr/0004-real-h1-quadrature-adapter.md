# ADR 0004 — Real H1 development integration without certified admission

Date: 2026-10-15. Status: implemented development decision; no R1 claim.
Controlling plan: `docs/IMPLEMENTATION_PLAN.md` (unchanged).

## Actual owner delivery

ANYgeometry main `21d0637bc7f090e03b88f785f75ea1821489db6d` contains public
`anygeometry.hydrostatics.hydrostatics`, `shell_volume.closed_shell`, and
`b1_example.build_b1_half_hull`. It still calls itself version 0.4.5. Its latest
review fixes are explicitly marked unreviewed in the commit message.

The hydrostatic API computes volume, CB, waterplane area/CF, centroidal second
moments, product moment and geometric BM. Its `estimate` is a normalized
order-doubling quadrature indicator, NOT a rigorous bound for these quantities.
Raw first moments, quantity-specific errors, a hydrostatic certificate verifier
and an explicit certified immersion classification are not returned.

The supplied B1 shape is a closed **half-hull bow segment** between two frames
and a centreline closure, not the complete future barge. `closed_shell` checks
connected, consistently oriented edge incidence. That is neither an outward
normal certificate nor a proof of a simple embedded displacement solid. The
owner can reverse the overall sign during integration. We do not hide this.

## Decision

Implement exactly one real owner adapter, `H1DevelopmentProvider`, requiring
literal `allow_development=True`. Keep the existing `anygeometry_h1` production
selector blocked. Do not weaken `IntegralSample`, `Quantity` or their assurance
rules and do not invent absolute errors by multiplying the single indicator by
individual output values. The development result has its own versioned schema.

Verify all 134 installed Python files against the observed aggregate SHA-256
`2c8c0cf0fae861b88f966db9960c15add693fb4e6214befd77e1fec84467b5aa` before
optional owner imports. This is code equivalence in a trusted environment, not
publisher authentication. Editable builds, a different payload, shadowed imports
and native extensions are not admitted by this pure-Python candidate.

Geometry is detached using the owner's own JSON codec and bound to model UUID,
revision, serialized content and selected face IDs. Only explicit metre-valued
BODY geometry is supported; implicit CRS transforms refuse. Topology and
numerical errors retain original owner causes. No private clipping, mesh
fallback, repairs, tolerance relaxation or waterplane perturbations exist.

## Conventions and scope

ANYstability retains `R = Ry(-trim) Rx(heel)`. Pass its explicit half-space to
`hydrostatics`; do not call the owner's `heel_normal`, `float_at` or `gz_curve`.
The source's `shift` argument avoids forming a rounded point as `normal*offset`.
Record and check the returned frame, its normal and plane residual. Floating
coordinate mapping is not advertised as exact-certified arithmetic.

`i_transverse` maps to the area moment about the plane's xi axis;
`i_longitudinal` maps to the moment about eta. The product is an area product,
not a negated mechanical inertia tensor entry. Both BM values remain geometric
`I/V`; no KG correction or stability conclusion is added.

The library caps order and call count, not the owner's internal subdivisions.
CLI jobs additionally use an isolated installed Python child with an explicit
wall limit. Expired/failed jobs cannot return a completed result. Near-zero
positive waterplane area below 1e-12 m2 is unresolved because the source has no
area enclosure; no small negative values are silently clamped.

## Evidence and remaining acceptance

No-owner tests exercise transport and refusals, not B1 physics. Real installed
checks separately compare finite-pose boxes to polynomial closed forms, B1 to
an independent elliptical cross-section integral, and a four-level faceted
reference to the same continuum. The panel reference lives only in tests and
is neither a production provider nor an ANYhydro qualification claim.

Even passing these comparisons does not close the original certified S2 gate.
Required follow-on deliveries include quantity-specific bounds, actual owner
certificate verification, supported-domain admission, full physical Q08,
matched ANYhydro/ANYmarine panel comparisons and the 1,000-plane/native
throughput programme. Free-floating equilibrium, GZ, tanks and rules remain
later ANYstability phases; the owner's helper routines do not shortcut them.
