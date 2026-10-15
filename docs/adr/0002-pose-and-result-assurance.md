# ADR 0002 — pose, residuals and assurance

Accepted for the heading-fixed S1 chart, 2026-10-15.

Body x forward, y to port, z upward. WORLD waterplane z=0 and gravity -g ez.
Positive heel lowers starboard; positive trim raises the bow.
R = Ry(-theta) Rx(phi) maps BODY to WORLD. The body waterplane is
n = R^T ez, d = -origin_z; halfspace n.r <= d.

Wrenches are reported in WORLD axes about the current body origin. First volume
moments are used directly for buoyancy moments, avoiding division by a tiny
volume and cancellation from large WORLD reference translations.
Q_phi = cos(theta)*tau_x + sin(theta)*tau_z; Q_theta = -tau_y.
This work-conjugate map is not a definition of horizontal GZ at finite trim.
Finite-rotation derivative/connection terms and marine-consumer admission are
future explicit gates; a six-by-six congruence alone does not implement them.

S1 vertical equilibrium fixes heel=trim=0 and solves the vertical displacement
condition only. Remaining moments are retained. Even a centred solved reference
is not labelled a stable free-floating vessel: that needs S3 tangent/branch tests.
A prescribed-pose result explicitly makes no equilibrium claim.

Reference quantity errors are engineering roundoff allowances, not rigorous
interval bounds. Bisection uses nominal reference values; its search bracket is
not a certified root enclosure. Final acceptance requires a small state bracket,
abs(force residual)+error estimate <= tolerance, and a repeated original query.
Budget exhaustion is not proof of no root. Endpoint/full-submerged neutral draft
states are unresolved rather than arbitrary roots.

Every S1 result is analytical reference / engineering development, no curve or
criteria assessment, no external approval, and production_qualified=false.
Loading checks transport identity/algebra; explicit verify recomputes the
reference result. Hashes do not establish correctness or source authenticity.
