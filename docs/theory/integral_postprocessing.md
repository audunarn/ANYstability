# S2 geometric postprocessing and arithmetic enclosure

These equations are derived from the definitions of the supplied integrals.
No new hull quadrature or curve-integration algorithm is implemented here.

For submerged volume V and first moments J, CB = J/V. When the supplied V
interval includes zero, this division is unresolved and CB is absent.

In an owner-declared waterplane frame with coordinates u,v, write:

    A = integral dA
    U = integral u dA; W = integral v dA
    UU = integral u^2 dA; WW = integral v^2 dA; UW = integral uv dA

For positive A, expand integral (u-U/A)^2 dA and use integral u dA = U:

    u_c = U/A; v_c = W/A
    C_uu = UU - U^2/A
    C_vv = WW - W^2/A
    C_uv = UW - U*W/A
    BM_about_u = C_vv/V; BM_about_v = C_uu/V

These are geometric ratios about the declared IN-PLANE axes. They are not an
assertion that a finite-attitude body's roll/pitch axes lie in that plane, and
are not its full stability stiffness or corrected GM. Physical righting moments
and work-conjugate forces remain separate later-phase calculations.

Raw moments must be combined across all material components/holes BEFORE
centroidal conversion. Two separated squares must include the parallel-axis
terms; a central void subtracts its signed raw integrals. The owner, not this
postprocessor, establishes which geometric regions are physically inside.

Each input Quantity supplies a binary64 nominal value and nonnegative absolute
error. Interval.of uses exact fractions of those binary inputs for value +/-
error, then rounds the endpoints outward with nextafter. Addition/subtraction,
multiplication, division and squaring similarly evaluate rational endpoint
expressions before outward conversion. Division by an interval containing zero
or any inability to return a finite enclosure raises ACCURACY_UNRESOLVED.

This encloses arithmetic on the SUPPLIED intervals. For estimated inputs it is
an enclosure of an estimate, not a proof that the true integral lies inside.
For genuinely owner-certified inputs it still does not independently verify the
owner certificate, frame-coordinate uncertainty, equilibrium-root error or the
real vessel's geometry. Coordinate frame checks use declared 1e-12 numerical
consistency tolerances; no formal pose map is asserted. The output states these
limitations and never sets production_qualified to true.

Independent tests use rational rectangle integrals, a separated two-component
section, a central hole, a nonzero product moment, degenerate/uncertain
denominators, and 200 deterministic rational endpoint-oracle trials for each
basic arithmetic operation. These are Q01/Q02 consumer subsets, not real Q08.
