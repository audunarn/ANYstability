# ADR 0003 — S2 consumer preparation, not fabricated H1 admission

Date: 2026-10-15. Status: implemented consumer slice; owner integration blocked.

GitHub main observations: ANYstability `16941a4284d966fd7d9914d98a382752c9e13160`;
ANYgeometry `0a3a602af7880d73d2cdac140f3ae3040b744421`. The latest three published
ANYgeometry releases were inspected: the newest is v0.4.5, published 1 October.
The owner-reported newer local main remains distinct. The available remote
device was offline; its local B1/H1 work and wheel were not inspected or changed.
These are availability observations, not a claim that the owner has stopped work.

## Decision

Implement the preparable consumer parts of S2 now: versioned prepared-source and
half-space records, explicit waterplane basis and raw moments, quantity-specific
accuracy, checked sequential batches, bounded geometric postprocessing, and a
read-only delivery-bundle inspector. Keep the existing S1 provider/result format
unchanged; never reinterpret its body-x/y moments as arbitrary-plane data.

Do NOT guess an ANYgeometry module, install an old wheel as H1, write a private
integration kernel, auto-nudge a plane, or use the analytical box as B1 evidence.
Production provider selection still raises PROVIDER_UNAVAILABLE. Metadata
probing calls importlib.metadata only; no optional geometry module is imported.
A declared certificate ID is data, not permission. Even a complete handoff whose
hashes match cannot pass the missing real-owner admission gates.

## Assurance

IntegralSample describes the producer's assertions. checked_query validates
transport identity, work and supplied error sizes, not geometric truth.
integral_properties computes outward scalar enclosures on the supplied intervals.
Its output explicitly does not verify an owner certificate or qualify a model.
Frame orthogonality/on-plane checks are numerical consistency checks, not formal
interval pose bounds. Arithmetic cannot turn an estimated interval into a
certified geometric result.

## Compatibility

Package 0.1.0.dev1 still accepts the exact S1 algorithm identifier and original
0.1.0.dev0 producing engine. Reproduction runs the unchanged reference algorithm
and retains the original engine identity before comparing the full result.
Unknown engine/algorithm records remain refused. New integral transport records
cannot be loaded as completed S1 equilibrium results.

## Actual S2 completion remains required

Use the controlling plan unchanged. Obtain the actual public H1 API and wheel,
map it in one reviewed adapter, verify the installed bytes and owner certificate,
exercise the real B1 fixture, run the geometry part of Q01/Q02/Q08 and independent
panel refinement, and measure P0/P1. None of these gates is replaced by this ADR.
