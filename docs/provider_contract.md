# Geometry provider handoff — S1 compatibility and S2 consumer contract

Production remains NOT ADMITTED. The new names below belong to ANYstability and
are not alleged ANYgeometry API names. The real H1 adapter cannot be written
against unpublished/undelivered interfaces. See ADR 0003 and CHECKPOINT.md.

## Existing S1 route

providers.protocol.HalfSpace, ProviderBinding, Quantity and HydrostaticSample
keep their existing serialization. reference_box_v1 still permits only exact
+z-normal planes and refuses top/bottom coincidence. Its raw x/y moments retain
the original body basis. S1 saved results remain readable and reproducible.

## S2 records (providers.integrals)

PreparedBinding binds a source identity, selected external boundaries, model ID,
revision, implementation/API, backend and supported-domain declaration. An
owner-certified declaration additionally requires artifact_sha256 and verifier_id.
These fields describe expected identity; they do not execute an owner verifier.
Geometry units are metres in BODY coordinates. Internal frames, intact tank
volumes, numerical BEM lids and zero-thickness sheets must not be mistaken for
additional displacement envelopes.

IntegralRequest carries an exact HalfSpace (n dot r <= d), query_id, five explicit
absolute-error requests (V, J, waterplane area, waterplane first and second
moments), and max_work_units. Its cache identity includes the entire preparation,
request and accuracy/work policy: adjacent planes and tighter requests never
silently share an identity. No result cache is enabled in this slice.

PlaneFrame gives an origin on the requested plane and already-orthonormal u/v
axes with u cross v = n. No normalization, reflection or geometry repair occurs.
WaterplaneMoments contains A, (integral u, integral v), and
(integral u^2, integral v^2, integral uv). These are RAW moments, not the signed
entries of a mass-inertia tensor. Components and holes describe the aggregated
material section; multiple components must include their separation terms.
Definitely non-positive-semidefinite raw or centroidal data are refused, using
supplied quantity intervals rather than an unexplained numerical clamp.

IntegralSample binds the complete request and preparation; V/J; waterplane data;
empty/full/partial/boundary state; actual work units; and optional owner
certificate/section references and event codes. Absent section/event references
mean unmeasured or not requested, never proof of no events. Empty/full states
away from a boundary have no section. A boundary query can carry an explicit
owner result or a typed refusal. A vanishing denominator yields no derived
centroid/BM; it never fabricates a zero centre of buoyancy.

from_dict/to_dict provide strict versioned JSON round trips with immutable
nested inputs. These records are not completed analysis/admission receipts.

## Checked queries and batches

checked_query validates returned type, exact request, unchanged preparation,
actual work and every quantity-error group. Original typed provider exceptions
are re-raised unchanged, unless the preparation itself changed during refusal;
then SOURCE_STALE wraps and retains the original cause.

checked_batch is a bounded SEQUENTIAL consumer batch, not native batching.
Requests and duplicate IDs are checked before any query. Geometric/accuracy/work
refusals are retained per item; remaining independent requests may continue.
Binding, integrity or input-contract failures abort remaining items as
not_executed. No incomplete batch is labelled all_queries_evaluated. Unexpected
programming exceptions propagate instead of masquerading as physical refusal.
The geometry work-unit meaning remains the declared backend's responsibility.

## Postprocessing and independent checks

hydrostatics.integral_properties exposes interval CB, waterplane centroid in its
u/v coordinates, centroidal moments and geometric BM about those in-plane axes.
BM ABOUT u uses integral (v-v_c)^2 / V, not integral (u-u_c)^2 / V.
It does not compute GM at arbitrary attitude, GZ, equilibrium or a criteria pass.
See theory/integral_postprocessing.md for arithmetic/uncertainty scope.

reference.integrals.ReferenceBoxIntegrals exercises this contract with the old
horizontal analytical box. Arbitrary-plane tests use explicitly authored moment
fixtures, not a new tilted-hull integration algorithm. Neither is B1/Q08 evidence.

## Consumer delivery-bundle format

inspect-handoff reads a proposed consumer manifest of kind
anystability-geometry-handoff-v1 with exactly these fields:

- kind, provider_id (anygeometry_h1), source_commit (Git SHA),
  distribution_version, owner_api_version, artifacts.
- Each artifact has role, path (normalized relative POSIX), sha256.
- Required roles: wheel, b1_fixture, api_document, bound_semantics,
  supported_domain, verification_evidence.

This is not an ANYgeometry model codec. The owner may deliver its existing
formats; the adapter will consume their documented public reader. The manifest
only inventories those files. See examples/h1_handoff_request.json for the known
remote baseline with an intentionally empty artifact list. Its null delivery is
not a downloadable or qualified H1 wheel.

Inspection verifies bounded local bytes, wheel Name/Version metadata, safe paths
and unique role/file inventory. It never extracts, imports, installs or executes
anything. Hash equality is only integrity against the declaration. It does not
prove publisher authenticity, installability, installed/source equivalence or
certificate truth. Symlinks/traversal are refused under the same trusted-workspace
threat model as project persistence; this is not protection against a hostile
concurrent process rewriting filesystem paths.

provider-check and inspect-handoff exit 2 while production admission is blocked,
including when every declared file's checksum matches. JSON retains missing
roles and outstanding gates. Malformed/corrupt input is a typed non-success.
No JSON field can choose a Python module/function to execute or turn admission on.

## Required real owner delivery and exit gate

Require installed source/wheel/public API identity, callable public certificate
verification, B1 physical boundary and independent references, V/J/CB and full
waterplane-moment bounds, supported-domain/empty/full/degenerate semantics, and
read-only prepared/batch/native controls. Native evidence is required before
native qualification, not to run the analytical contract tests. Map actual
owner errors to stable consumer codes with original evidence intact.

Pass the S2 geometry portions of Q01/Q02/Q08 using the real installed artifact;
retain source/certificate identity across persistence; perform independent panel
refinement and P0/P1 measurements. Full Q08 equilibrium/GZ is completed by later
phases. This gate is BLOCKED, not skipped-as-passing, in the current delivery.
