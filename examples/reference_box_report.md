# ANYstability — analytical development report

**REFERENCE ONLY. Not B1/H1, not production-qualified and not an approved stability assessment.**

Vessel: Analytical box (not B1)
Condition: Analytical reference condition

Result input identity: `050ca2246cf4d2ed2d4a8ed3d7e8188dec52b0e1b46b17301a754ec02a8f601d`
Result content identity: `605e3f0ec9024ec9bed1da38b3119350cbc4e1143859e0fd58e471926f6196da`

Stored-result check: reproduced by the current reference engine.
Current-project status: not compared.

## Loading ledger

| Item | Mass (kg) | Body CG (m) | Covered components |
|---|---:|---|---|
| cargo | 205000 | (0.0, 0.0, 2.5) | cargo |
| lightship | 205000 | (0.0, 0.0, 1.5) | structure |

Total mass: 410000 kg.
Aggregate body CG: [0.0, 0.0, 2.0] m.
Water density: 1025 kg/m³; gravity: 9.80665 m/s².

## Calculation

Mode: `fixed_attitude_vertical`; status: `engineering_converged`.
Axes: body x forward, y port, z up; WORLD waterplane z=0. Angles in radians.
Pose: `{'heel_rad': 0.0, 'origin_z_m': -1.999999988824129, 'rotation_body_to_world': [[1.0, -0.0, -0.0], [0.0, 1.0, -0.0], [0.0, 0.0, 1.0]], 'trim_rad': 0.0}`
Provider queries: 33.

Submerged volume: 399.999997765 m³.
Body centre of buoyancy: [0.0, 0.0, 0.9999999944120646] m.
Vertical force residual: -0.0224675596692 N.
Vertical residual error estimate: 3.3185308439e-08 N.
Remaining WORLD moments about body origin: [0.0, 0.0, 0.0] N·m.
Draft from the reference-box bottom: 1.99999998882 m.
Search bracket: [1.9999999776482582, 2.0] m (not a certified root enclosure).
Force tolerance: 0.040207265 N.
Heel and trim are constrained: rotational equilibrium and local stability were NOT solved.

## Limitations and reproduction

Quantity errors are engineering roundoff estimates, not certified geometry bounds. No tanks, GZ curves, opening events, criteria or marine consumer admission are implemented in S1.
Input and result sidecars are self-contained. Loading does not execute a solver. Use the verify command with the stored result-object hash for explicit numerical reproduction.

```text
anystability verify PROJECT_DIRECTORY RESULT_OBJECT_HASH
anystability equilibrium PROJECT_DIRECTORY --allow-reference
```
