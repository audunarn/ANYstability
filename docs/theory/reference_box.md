# Independent reference formulas and test domain

S1 analytical benchmark, not ship qualification. Derivation is public here.

Take a box centred in x/y, with length L, breadth B, bottom z=0 and top z=H.
At horizontal cut z=d, let h=clamp(d,0,H). Direct integration of constant
cross-section area gives V=LBh, Jx=Jy=0 and Jz=LB*h^2/2. If V>0, CB=(0,0,h/2).
For 0<d<H, A=LB, integral x^2 dA=B*L^3/12 and integral y^2 dA=L*B^3/12.
The product moment vanishes by symmetry. Outside the box A=0. At bottom/top
cuts the volume derivative is one-sided, so the S1 complete-query provider
refuses rather than silently choosing a waterplane area convention.

For mass m in water density rho, the unique partially immersed upright
vertical solution is d=m/(rho*L*B), provided 0<m<rho*L*B*H. Tests compare a
bisection implementation with this independently evaluated closed-form depth.
Total weight is mg, buoyancy rho*g*V. For CG=(xg,yg,zg), moments of gravity
about body origin are (-mg*yg, mg*xg, 0); centred buoyancy has zero torque.
Thus an offset ledger must leave a nonzero unsolved rotational residual.

The shipped example declares L=20 m, B=10 m, H=4 m; m=410000 kg;
rho=1025 kg/m^3 and CG=(0,0,2) m. Expected vertical draft is exactly 2 m,
volume 400 m^3 and CB=(0,0,1) m in the ideal mathematical model.
These are fabricated analytical test inputs, not B1 dimensions or a real vessel.

The error allowance 32*ulp(value) estimates ordinary arithmetic roundoff.
It is not an outward-rounded interval calculation or formal certificate.
The solver never labels its nominal bisection bracket a proven root enclosure.
No tilted box clipping, wall-sided large-angle formula, GZ or liquid model is
hidden behind this reference. Those functions are not implemented in S1.
