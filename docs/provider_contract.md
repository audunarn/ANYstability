# Geometry provider handoff — S1 boundary and S2 requirements

This document specifies a consumer protocol; it does not declare installed
ANYgeometry APIs. The production selector currently raises PROVIDER_UNAVAILABLE.
The owner-reported B1/H1 work remains an upstream dependency, not an implemented
substitute inside ANYstability.

S1 has immutable HalfSpace, ProviderBinding, Quantity and HydrostaticSample
records; a provider supplies evaluate_halfspace and a vertical search domain.
The service checks that the returned sample belongs to exactly the requested
plane and initial source binding. A nearby plane is never admitted as the input.

The shipped reference_box_v1 provider admits only the exact normal (0,0,1).
Its volume occupies x in [-L/2,L/2], y in [-B/2,B/2], z in [0,H]. At z=0,H it
refuses the complete area/moment query because the waterplane derivative is
one-sided. It does not permanently exclude these common planes from the future
production product: H1 must handle them or explicitly declare the available
one-sided quantities. No epsilon recovery is implemented in S1.

S1 waterplane second moments have a deliberately limited body-x/y basis at
(0,0,d), raw integrals of x*x, y*y and x*y. This is not a generic H1 basis contract.
Before S2 admission, extend the sample with the actual in-plane basis/origin,
first moments, component/holes semantics, requested-error controls, event data,
owner verification and batch receipts from the delivered public API.

Required upstream receipt, owner ANYgeometry:

1. Installed source/wheel/API identity and callable public verifier.
2. B1 full physical boundary fixture, closedness/outward-orientation evidence,
   units/frame, supported families and operating waterplane domain.
3. V, integral r dV, conditioned CB, waterplane area/first/second moments, each
   with precise quantity-specific bound semantics; empty/full and tangent cases.
4. A reusable prepared binding, immutable read-only queries, typed failures,
   work/accuracy policy, and native/reference identity where supplied.
5. Independent primitive/submerged references and certificate reload checks.

Q08 must exercise the real installed owner API and B1 fixture. Mock protocol
checks and the analytic reference never pass Q08. Do not parse undocumented
owner files or fabricate certificate flags. Do not automatically import unknown
owner modules based on user JSON. Full production adapter work is S2.
