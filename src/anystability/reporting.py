"""Reports consume stored/reproduced results; never a second numerical solver."""
import html
from .services import reproduce
from .validation import canonical_bytes


def _label(value):
    # Keep user names from injecting HTML or Markdown tables/headings.
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def markdown_report(record, *, verify=False, current_project=None):
    if verify:
        record = reproduce(record)
    d = record.to_dict()
    o, p = d["output"], record.project
    s = o["state"]
    stale = current_project is not None and record.is_stale(current_project)
    lines = ["# ANYstability — analytical development report", "",
             "**REFERENCE ONLY. Not B1/H1, not production-qualified and not an approved stability assessment.**", "",
             f"Vessel: {_label(p.vessel.name)}", f"Condition: {_label(p.condition.name)}", "",
             f"Result input identity: `{p.identity}`", f"Result content identity: `{record.identity}`", "",
             f"Stored-result check: {'reproduced by the current reference engine' if verify else 'integrity/transport only; not numerically reproduced'}.",
             f"Current-project status: {'STALE — shown using producing inputs' if stale else 'matching' if current_project else 'not compared'}.", "",
             "## Loading ledger", "", "| Item | Mass (kg) | Body CG (m) | Covered components |",
             "|---|---:|---|---|"]
    for item in p.condition.items:
        lines.append(f"| {_label(item.item_id)} | {item.mass_kg:.12g} | {item.cg_body_m} | {_label(', '.join(item.covers))} |")
    lines += ["", f"Total mass: {s['mass']['mass_kg']:.12g} kg.",
              f"Aggregate body CG: {s['mass']['cg_body_m']} m.",
              f"Water density: {p.condition.water_density_kg_m3:.12g} kg/m³; gravity: {p.condition.gravity_m_s2:.12g} m/s².", "",
              "## Calculation", "", f"Mode: `{o['mode']}`; status: `{o['status']}`.",
              "Axes: body x forward, y port, z up; WORLD waterplane z=0. Angles in radians.",
              f"Pose: `{s['pose']}`", f"Provider queries: {o['query_count']}.", "",
              f"Submerged volume: {s['hydrostatics']['volume_m3']['value']:.12g} m³.",
              f"Body centre of buoyancy: {s['hydrostatics']['center_of_buoyancy_body_m']} m.",
              f"Vertical force residual: {s['vertical_residual_N']:.12g} N.",
              f"Vertical residual error estimate: {s['vertical_residual_error_estimate_N']:.12g} N.",
              f"Remaining WORLD moments about body origin: {s['net_moment_Nm']} N·m."]
    if o["mode"] == "fixed_attitude_vertical":
        lines += [f"Draft from the reference-box bottom: {o['draft_m']:.12g} m.",
                  f"Search bracket: {o['search_bracket_m']} m (not a certified root enclosure).",
                  f"Force tolerance: {o['force_limit_N']:.12g} N.",
                  "Heel and trim are constrained: rotational equilibrium and local stability were NOT solved."]
    lines += ["", "## Limitations and reproduction", "",
              "Quantity errors are engineering roundoff estimates, not certified geometry bounds. No tanks, GZ curves, opening events, criteria or marine consumer admission are implemented in S1.",
              "Input and result sidecars are self-contained. Loading does not execute a solver. Use the verify command with the stored result-object hash for explicit numerical reproduction.", "",
              "```text", "anystability verify PROJECT_DIRECTORY RESULT_OBJECT_HASH",
              "anystability equilibrium PROJECT_DIRECTORY --allow-reference", "```", ""]
    return "\n".join(lines)


def html_report(record, **kwargs):
    # Deliberately no Markdown renderer dependency or raw user HTML execution.
    body = html.escape(markdown_report(record, **kwargs))
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>ANYstability reference report</title><body><pre>' + body + '</pre></body></html>\n'
