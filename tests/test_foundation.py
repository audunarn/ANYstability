"""Analytical and adverse checks. Run against an installed wheel, not PYTHONPATH."""
import copy
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from anystability.conventions import Pose, generalized_rotation_forces
from anystability.domain import (AnalysisSettings, GeometrySource, LoadingCondition,
                                 MassItem, Project)
from anystability.equilibrium import evaluate, solve_vertical
from anystability.errors import ErrorCode, StabilityError
from anystability.loading import aggregate_mass
from anystability.persistence import (atomic_write, load_project, load_result,
                                     save_project, save_result)
from anystability.providers.protocol import HalfSpace, Quantity
from anystability.reference.box import AnalyticBoxProvider
from anystability.reporting import html_report, markdown_report
from anystability.services import (AnalysisRecord, analyze, capabilities, example_project,
                                  provider_for, reproduce)
from anystability.validation import canonical_bytes, decode_json, real


class Checks(unittest.TestCase):
    def assert_code(self, expected, fn, *args, **kwargs):
        with self.assertRaises(StabilityError) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.code, expected)
        return cm.exception


class InputTests(Checks):
    def test_bad_numbers(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"), "1", None, 10**1000):
            with self.subTest(value=str(value)[:50]):
                self.assert_code(ErrorCode.INPUT_INVALID, real, value, "test")

    def test_deep_immutable(self):
        xyz, covers = [1, 2, 3], ["A"]
        item = MassItem("x", 10, xyz, "test", covers)
        xyz[0] = 90
        covers.append("B")
        self.assertEqual(item.cg_body_m, (1, 2, 3))
        self.assertEqual(item.covers, ("A",))
        with self.assertRaises(FrozenInstanceError):
            item.mass_kg = 3

    def test_duplicate_item(self):
        item = example_project().condition.items[0]
        self.assert_code(ErrorCode.INPUT_INVALID, LoadingCondition, "a", "A", (item, item))

    def test_overlap_of_aggregate_and_part(self):
        whole = MassItem("lightship", 100, (0, 0, 0), "test", ("steel", "machinery"))
        part = MassItem("engine", 20, (0, 0, 0), "test", ("machinery",))
        self.assert_code(ErrorCode.INPUT_INVALID, LoadingCondition, "a", "A", (whole, part))

    def test_empty_duplicate_covers(self):
        for covers in ((), ("a", "a"), ("",)):
            self.assert_code(ErrorCode.INPUT_INVALID, MassItem, "x", 1, (0,0,0), "test", covers)

    def test_bad_mass_inputs(self):
        for value in (0, -1, True, float("inf")):
            self.assert_code(ErrorCode.INPUT_INVALID, MassItem, "x", value, (0,0,0), "test", ("x",))
        for xyz in ([], (1,2), (1,2,3,4), (0,0,True)):
            self.assert_code(ErrorCode.INPUT_INVALID, MassItem, "x", 1, xyz, "test", ("x",))

    def test_settings(self):
        for kwargs in ({"max_queries":True}, {"max_queries":0}, {"max_queries":3.2},
                       {"draft_tolerance_m":0}, {"force_relative_tolerance":1}):
            self.assert_code(ErrorCode.INPUT_INVALID, AnalysisSettings, **kwargs)

    def test_strict_schema(self):
        data = example_project().to_dict()
        for mutate in (lambda d:d.update(extra=1), lambda d:d.update(schema_version=True),
                       lambda d:d["condition"].update(tanks=[]),
                       lambda d:d["settings"].update(assurance="certified")):
            d = copy.deepcopy(data); mutate(d)
            self.assert_code(ErrorCode.INPUT_INVALID, Project.from_dict, d)

    def test_json_rejection(self):
        for value in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{"a":Infinity}',
                      b'\xff', b'not json', b' ' * 2_000_001):
            self.assert_code(ErrorCode.INPUT_INVALID, decode_json, value)

    def test_roundtrip_and_order_identity(self):
        p = example_project()
        self.assertEqual(p, Project.from_dict(decode_json(canonical_bytes(p.to_dict()))))
        self.assertEqual(p.identity, replace(p, condition=replace(p.condition, items=p.condition.items[::-1])).identity)
        d = p.to_dict(); d["condition"]["items"][0]["mass_kg"] = 2
        self.assertNotEqual(p.identity, Project.from_dict(d).identity)

    def test_geometry_source_cannot_mutate(self):
        p = example_project()
        d = p.vessel.geometry.to_dict(); d["definition"]["length_m"] = 4
        self.assertEqual(p.vessel.geometry.to_dict()["definition"]["length_m"], 20)

    def test_integer_geometry_definition_retains_identity(self):
        p = example_project(); d = p.to_dict()
        d["vessel"]["geometry"]["definition"] = dict(length_m=20, breadth_m=10, height_m=4)
        p = Project.from_dict(d)
        r = analyze(p, allow_reference=True)
        self.assertEqual(r.to_dict()["output"]["state"]["hydrostatics"]["binding"]["source_hash"], p.vessel.geometry.identity)


class LoadingTests(Checks):
    def test_aggregate_against_independent_moments(self):
        c = LoadingCondition("a", "A", (MassItem("1", 2, (1, 3, 5), "ref", ("A",)),
                                         MassItem("2", 3, (4, 8, 2), "ref", ("B",))))
        result = aggregate_mass(c)
        self.assertEqual(result.mass_kg, 5)
        for got, expected in zip(result.cg_body_m, (14/5, 30/5, 16/5)):
            self.assertAlmostEqual(got, expected)

    def test_translated_cg(self):
        c = example_project().condition
        shifted = replace(c, items=tuple(replace(i, cg_body_m=(1e9, -1e9, i.cg_body_m[2]+1e9)) for i in c.items))
        self.assertEqual(aggregate_mass(shifted).cg_body_m, (1e9, -1e9, 1e9+2))

    def test_aggregate_overflow(self):
        c = LoadingCondition("a", "A", (MassItem("1", 1e308, (0,0,0), "ref", ("A",)),
                                         MassItem("2", 1e308, (0,0,0), "ref", ("B",))))
        self.assert_code(ErrorCode.INPUT_INVALID, aggregate_mass, c)


class ConventionsTests(Checks):
    def test_heel_lowers_starboard_trim_raises_bow(self):
        self.assertLess(Pose(heel_rad=.2).rotate((0,-1,0))[2], 0)
        self.assertGreater(Pose(trim_rad=.2).rotate((1,0,0))[2], 0)

    def test_proper_rotation(self):
        for phi, theta in ((0,0), (.5,.3), (-.7,-.4), (2,1)):
            r = Pose(phi,theta).rotation
            for i in range(3):
                for j in range(3):
                    self.assertAlmostEqual(sum(r[k][i]*r[k][j] for k in range(3)), float(i==j), places=14)
            det = (r[0][0]*(r[1][1]*r[2][2]-r[1][2]*r[2][1])
                   -r[0][1]*(r[1][0]*r[2][2]-r[1][2]*r[2][0])
                   +r[0][2]*(r[1][0]*r[2][1]-r[1][1]*r[2][0]))
            self.assertAlmostEqual(det, 1, places=14)

    def test_waterplane_without_geometry_mutation(self):
        pose = Pose(.23,-.1,-4)
        n, d = pose.waterplane()
        for body_point in ((2,3,4), (0,0,0), (-1,2,-3)):
            world_z = pose.rotate(body_point)[2] + pose.origin_z_m
            self.assertAlmostEqual(sum(a*b for a,b in zip(n,body_point))-d, world_z)

    def test_finite_trim_work_conjugacy(self):
        pose = Pose(.2,.4)
        tau = (120,30,9)
        qphi,qtheta = generalized_rotation_forces(pose,tau)
        self.assertAlmostEqual(qphi, math.cos(.4)*120+math.sin(.4)*9)
        self.assertEqual(qtheta, -30)
        # Coordinate rates -> WORLD angular velocity, then physical virtual power.
        pd,td = .13,-.7
        omega = (math.cos(.4)*pd, -td, math.sin(.4)*pd)
        self.assertAlmostEqual(qphi*pd+qtheta*td, sum(a*b for a,b in zip(tau,omega)))
        self.assertNotEqual(qphi, tau[0])

    def test_nonunit_plane_rejected(self):
        self.assert_code(ErrorCode.INPUT_INVALID, HalfSpace, (0,0,2), 1)


class HydrostaticsTests(Checks):
    def setUp(self):
        self.box = AnalyticBoxProvider(20,10,4)

    def test_volume_centroid_moments(self):
        for d in (.1, .5, 1.3, 2.0, 3.9):
            with self.subTest(draft=d):
                s = self.box.evaluate_halfspace(HalfSpace((0,0,1),d))
                self.assertAlmostEqual(s.volume_m3.value, 200*d)
                self.assertAlmostEqual(s.first_moments_m4[2].value, 100*d*d)
                self.assertEqual(s.first_moments_m4[0].value, 0)
                self.assertEqual(s.center_of_buoyancy_m, (0,0,d/2))
                self.assertEqual(s.waterplane_area_m2.value, 200)
                self.assertAlmostEqual(s.waterplane_raw_xx_m4.value, 10*20**3/12)
                self.assertAlmostEqual(s.waterplane_raw_yy_m4.value, 20*10**3/12)
                self.assertEqual(s.waterplane_raw_xy_m4.value, 0)

    def test_empty_and_fully_submerged(self):
        empty = self.box.evaluate_halfspace(HalfSpace((0,0,1),-1))
        full = self.box.evaluate_halfspace(HalfSpace((0,0,1),5))
        self.assertEqual(empty.volume_m3.value, 0)
        self.assertIsNone(empty.center_of_buoyancy_m)
        self.assertEqual(full.volume_m3.value, 800)
        self.assertEqual(full.center_of_buoyancy_m, (0,0,2))
        self.assertEqual(full.waterplane_area_m2.value, 0)

    def test_volume_derivative(self):
        a = self.box.evaluate_halfspace(HalfSpace((0,0,1),1.3-1e-5)).volume_m3.value
        b = self.box.evaluate_halfspace(HalfSpace((0,0,1),1.3+1e-5)).volume_m3.value
        self.assertAlmostEqual((b-a)/2e-5, 200, places=7)

    def test_degenerate_no_nudge(self):
        for d in (0,4):
            e = self.assert_code(ErrorCode.QUERY_DEGENERATE, self.box.evaluate_halfspace, HalfSpace((0,0,1),d))
            self.assertEqual(e.details["query"]["offset_m"], d)

    def test_tilt_refused_not_projected(self):
        self.assert_code(ErrorCode.CAPABILITY_UNSUPPORTED, self.box.evaluate_halfspace, HalfSpace((0,1,0),1))
        self.assert_code(ErrorCode.CAPABILITY_UNSUPPORTED, self.box.evaluate_halfspace, HalfSpace((1e-20,0,1),1))

    def test_reference_cannot_claim_certificate(self):
        s = self.box.evaluate_halfspace(HalfSpace((0,0,1),2))
        self.assert_code(ErrorCode.INPUT_INVALID, replace, s, volume_m3=Quantity(400,0,"owner_certified_bound"))

    def test_unsafe_dimension_range(self):
        for dim in (0, -1, True, 1e200, 1e-300):
            self.assert_code(ErrorCode.INPUT_INVALID, AnalyticBoxProvider, dim, dim, dim)

    def test_substituted_plane_or_binding(self):
        box = self.box
        class Shifted:
            binding = box.binding
            def evaluate_halfspace(self, plane):
                return box.evaluate_halfspace(HalfSpace(plane.normal, plane.offset_m+1e-6))
        self.assert_code(ErrorCode.SOURCE_STALE, evaluate, Shifted(), HalfSpace((0,0,1),2))
        class Foreign:
            binding = box.binding
            def evaluate_halfspace(self, plane):
                s = box.evaluate_halfspace(plane)
                return replace(s, binding=replace(s.binding, source_hash="a"*64))
        self.assert_code(ErrorCode.SOURCE_STALE, evaluate, Foreign(), HalfSpace((0,0,1),2))


class EquilibriumTests(Checks):
    def test_independent_drafts_for_many_loads(self):
        p = example_project()
        for depth in (.1, .333, 1.1, 2, 3.75, 3.9):
            item = MassItem("m", 1025*200*depth, (0,0,1), "ref", ("m",))
            c = replace(p.condition, items=(item,))
            r = analyze(replace(p, condition=c), allow_reference=True).to_dict()["output"]
            self.assertAlmostEqual(r["draft_m"], depth, delta=1e-6)
            self.assertLessEqual(abs(r["state"]["vertical_residual_N"])+r["state"]["vertical_residual_error_estimate_N"], r["force_limit_N"])
            self.assertLessEqual(r["search_bracket_m"][1]-r["search_bracket_m"][0], 1e-6)
            self.assertEqual(r["rotational_equilibrium"], "not_solved")

    def test_force_and_cg_moments(self):
        p = example_project()
        c = replace(p.condition, items=(MassItem("m",410000,(1,2,3),"ref",("m",)),))
        r = analyze(replace(p,condition=c),allow_reference=True).to_dict()["output"]
        weight = 410000*c.gravity_m_s2
        self.assertEqual(r["state"]["net_moment_Nm"], [-2*weight,weight,0])
        self.assertEqual(r["rotational_equilibrium"], "not_solved")
        self.assertAlmostEqual(r["draft_m"], 2, delta=1e-6)

    def test_overload_is_not_iteration_failure(self):
        p = example_project()
        c = replace(p.condition, items=(MassItem("m",1e6,(0,0,1),"ref",("m",)),))
        self.assert_code(ErrorCode.NO_ROOT_IN_SEARCH_DOMAIN, analyze, replace(p,condition=c), allow_reference=True)

    def test_neutral_full_submergence(self):
        p = example_project()
        c = replace(p.condition, items=(MassItem("m",820000,(0,0,1),"ref",("m",)),))
        self.assert_code(ErrorCode.EQUILIBRIUM_UNRESOLVED, analyze, replace(p,condition=c), allow_reference=True)

    def test_budget_failure(self):
        p = replace(example_project(), settings=AnalysisSettings(max_queries=2))
        e = self.assert_code(ErrorCode.WORK_BUDGET_EXCEEDED, analyze, p, allow_reference=True)
        self.assertEqual(e.details["query_count"], 2)

    def test_too_tight_tolerance_fails(self):
        p = replace(example_project(), settings=AnalysisSettings(force_relative_tolerance=1e-20))
        self.assert_code(ErrorCode.ACCURACY_UNRESOLVED, analyze, p, allow_reference=True)

    def test_final_query_is_repeated(self):
        p = example_project(); box = provider_for(p,allow_reference=True)
        planes=[]
        class Recording:
            binding=box.binding
            def vertical_search_domain(self):return box.vertical_search_domain()
            def evaluate_halfspace(self, plane):
                planes.append(plane)
                return box.evaluate_halfspace(plane)
        r = solve_vertical(Recording(),p.condition,p.settings)
        self.assertEqual(planes[-1], planes[-2])
        self.assertEqual(len(planes),r["query_count"])

    def test_refusal_cause_retained(self):
        p = example_project(); box = provider_for(p,allow_reference=True)
        class Broken:
            binding=box.binding
            def vertical_search_domain(self):return box.vertical_search_domain()
            def evaluate_halfspace(self,plane):
                raise StabilityError(ErrorCode.QUERY_DEGENERATE,"owner refusal",certificate_id="abc")
        e=self.assert_code(ErrorCode.QUERY_DEGENERATE,solve_vertical,Broken(),p.condition,p.settings)
        self.assertEqual(e.details["provider_cause"]["details"]["certificate_id"],"abc")

    def test_explicit_reference_only(self):
        self.assert_code(ErrorCode.CAPABILITY_UNSUPPORTED, analyze, example_project())
        self.assertFalse(capabilities()["production_geometry"]["available"])
        p=example_project()
        source=GeometrySource("anygeometry_h1",'{"model_id":"future"}')
        p=replace(p,vessel=replace(p.vessel,geometry=source))
        self.assert_code(ErrorCode.PROVIDER_UNAVAILABLE,analyze,p,allow_reference=True)

    def test_prescribed_pose_not_equilibrium(self):
        r=analyze(example_project(),calculation="hydrostatics",pose=Pose(origin_z_m=-1),allow_reference=True)
        self.assertEqual(r.to_dict()["output"]["status"],"evaluated_not_equilibrated")
        self.assertNotEqual(r.to_dict()["output"]["state"]["vertical_residual_N"],0)
        self.assertEqual(reproduce(r),r)

    def test_unknown_calculation_refused(self):
        self.assert_code(ErrorCode.CAPABILITY_UNSUPPORTED,analyze,example_project(),calculation="gz",allow_reference=True)
        self.assert_code(ErrorCode.INPUT_INVALID,analyze,example_project(),pose=Pose(.1),allow_reference=True)


class PersistenceTests(Checks):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"study"
        self.p=example_project()
        self.r=analyze(self.p,allow_reference=True)
        save_project(self.p,self.root)

    def test_project_and_result_roundtrip(self):
        self.assertEqual(load_project(self.root),self.p)
        rid=save_result(self.r,self.root)
        restored=load_result(self.root,rid)
        self.assertEqual(restored,self.r)
        self.assertEqual(reproduce(restored),self.r)

    def test_load_does_not_execute(self):
        rid=save_result(self.r,self.root)
        with patch.object(AnalyticBoxProvider,"evaluate_halfspace",side_effect=AssertionError("must not solve")):
            self.assertEqual(load_project(self.root),self.p)
            self.assertEqual(load_result(self.root,rid),self.r)

    def test_portable_copy(self):
        import shutil
        rid=save_result(self.r,self.root)
        other=Path(self.tmp.name)/"moved"
        shutil.copytree(self.root,other)
        self.assertEqual(load_result(other,rid),self.r)

    def test_stale_snapshot_preserved(self):
        rid=save_result(self.r,self.root)
        changed=replace(self.p,condition=replace(self.p.condition,water_density_kg_m3=1000))
        save_project(changed,self.root,overwrite=True)
        old=load_result(self.root,rid)
        self.assertTrue(old.is_stale(load_project(self.root)))
        self.assertEqual(reproduce(old),self.r)
        self.assertIn("STALE",markdown_report(old,current_project=changed))

    def test_no_overwrite(self):
        before=(self.root/"project.json").read_bytes()
        with self.assertRaises(FileExistsError):save_project(self.p,self.root)
        self.assertEqual(before,(self.root/"project.json").read_bytes())
        with self.assertRaises(FileExistsError):atomic_write(self.root/"project.json",b"bad")

    def test_interrupted_manifest_publish(self):
        before=(self.root/"project.json").read_bytes()
        with patch("anystability.persistence.os.replace",side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):save_project(self.p,self.root,overwrite=True)
        self.assertEqual((self.root/"project.json").read_bytes(),before)
        self.assertEqual(load_project(self.root),self.p)
        self.assertFalse(list(self.root.glob(".anystability-*")))

    def test_corrupt_sidecar(self):
        path=self.root/"objects"/(self.p.identity+".json")
        path.write_bytes(b'{"corrupted":true}')
        self.assert_code(ErrorCode.INTEGRITY_ERROR,load_project,self.root)
        self.assert_code(ErrorCode.INTEGRITY_ERROR,save_project,self.p,self.root,overwrite=True)

    def test_path_traversal_digest(self):
        for rid in ("../outside", "a"*63, "A"*64, "./"+"a"*64):
            self.assert_code(ErrorCode.INPUT_INVALID,load_result,self.root,rid)

    def test_symlink_refused(self):
        other=Path(self.tmp.name)/"link"
        try:other.symlink_to(self.root,target_is_directory=True)
        except OSError:self.skipTest("symlink creation not permitted on this platform")
        self.assert_code(ErrorCode.IO_ERROR,load_project,other)
        self.assert_code(ErrorCode.IO_ERROR,atomic_write,other/"sub"/"x.md",b"bad")

    def test_result_tampering_and_forged_assurance(self):
        for mutate in (lambda d:d["assurance"].update(production_qualified=True),
                       lambda d:d["output"].update(rotational_equilibrium="stable"),
                       lambda d:d["output"]["state"].update(extra=1),
                       lambda d:d["output"]["state"]["mass"].update(mass_kg=1),
                       lambda d:d["output"]["state"]["hydrostatics"]["volume_m3"].update(assurance="owner_certified_bound")):
            d=self.r.to_dict();mutate(d)
            self.assert_code(ErrorCode.INPUT_INVALID,AnalysisRecord,canonical_bytes(d).decode())

    def test_result_binding_tamper(self):
        d=self.r.to_dict();d["input_hash"]="a"*64
        self.assert_code(ErrorCode.INTEGRITY_ERROR,AnalysisRecord,canonical_bytes(d).decode())
        d=self.r.to_dict();d["output"]["state"]["hydrostatics"]["binding"]["source_hash"]="a"*64
        self.assert_code(ErrorCode.SOURCE_STALE,AnalysisRecord,canonical_bytes(d).decode())

    def test_reproduction_detects_rehashed_evidence_edit(self):
        d=self.r.to_dict();d["output"]["query_count"]+=1
        altered=AnalysisRecord(canonical_bytes(d).decode())
        self.assert_code(ErrorCode.INTEGRITY_ERROR,reproduce,altered)

    def test_report_not_second_solver(self):
        with patch.object(AnalyticBoxProvider,"evaluate_halfspace",side_effect=AssertionError("no solve")):
            text=markdown_report(self.r)
        self.assertIn("not numerically reproduced",text)
        self.assertIn("rotational equilibrium",text)
        self.assertIn("2",text)

    def test_report_html_escape(self):
        p=replace(self.p,vessel=replace(self.p.vessel,name='<script>alert(1)</script>'))
        r=analyze(p,allow_reference=True)
        self.assertNotIn("<script>",html_report(r))
        self.assertNotIn("<script>",markdown_report(r))


class InstalledCliTests(Checks):
    def test_optional_import_boundaries(self):
        code='''import sys
before=set(sys.modules)
import anystability.cli
for x in ("numpy","scipy","anygeometry","anyhydro","anymarine","anysolver","capytaine","xarray","PySide6"):
    assert x not in set(sys.modules)-before, x
print("base imports clean")'''
        r=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_cli_complete_workflow_and_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=str(Path(tmp)/"project")
            def cli(*args):
                return subprocess.run([sys.executable,"-m","anystability",*args],capture_output=True,text=True)
            for args in (("capabilities",),("example",root),("validate",root,"--allow-reference")):
                r=cli(*args);self.assertEqual(r.returncode,0,r.stderr)
            refusal=cli("equilibrium",root)
            self.assertEqual(refusal.returncode,2)
            self.assertEqual(json.loads(refusal.stderr)["code"],"CAPABILITY_UNSUPPORTED")
            r=cli("equilibrium",root,"--allow-reference")
            self.assertEqual(r.returncode,0,r.stderr)
            rid=json.loads(r.stdout)["result_object_hash"]
            for args in (("verify",root,rid),("report",root,rid,str(Path(tmp)/"report.md"),"--verify"),
                         ("export-json",root,rid,str(Path(tmp)/"result.json"))):
                r=cli(*args);self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn("REFERENCE ONLY",(Path(tmp)/"report.md").read_text(encoding="utf-8"))
            degenerate=cli("hydrostatics",root,"--draft-m","0","--allow-reference")
            self.assertEqual(degenerate.returncode,2)
            self.assertEqual(json.loads(degenerate.stderr)["code"],"QUERY_DEGENERATE")
            tilted=cli("hydrostatics",root,"--draft-m","1","--heel-rad","0.2","--allow-reference")
            self.assertEqual(tilted.returncode,2)
            self.assertEqual(json.loads(tilted.stderr)["code"],"CAPABILITY_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
