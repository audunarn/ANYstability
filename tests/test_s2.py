"""S2 consumer checks, not B1/H1 installed-owner qualification (Q08)."""
import copy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from anystability.conventions import Pose
from anystability.domain import GeometrySource
from anystability.errors import ErrorCode, StabilityError
from anystability.hydrostatics import integral_properties
from anystability.providers.bounds import Interval
from anystability.providers.handoff import (KIND, REQUIRED_ROLES, inspect_handoff, provider_status)
from anystability.providers.integrals import (Accuracy, IntegralRequest, IntegralSample, PlaneFrame,
    PreparedBinding, WaterplaneMoments, checked_query, checked_batch)
from anystability.providers.protocol import HalfSpace, Quantity
from anystability.reference.box import AnalyticBoxProvider
from anystability.reference.integrals import ReferenceBoxIntegrals
from anystability.services import (AnalysisRecord, analyze, analyze_integrals, example_project,
                                   provider_for, reproduce)
from anystability.validation import canonical_bytes, decode_json


def q(v, e=0):
    return Quantity(v, e)


def request(d=2., name="q", **kwargs):
    return IntegralRequest(name, HalfSpace((0, 0, 1), d), **kwargs)


def reference():
    return ReferenceBoxIntegrals(AnalyticBoxProvider(20, 10, 4))


def transformed_sample():
    """Independent *moment fixture*, not an arbitrary-plane hull implementation.

    Waterplane rectangle u in [1,5], v in [2,4]: A=8, Ju=24, Jv=24,
    integral u^2=248/3, v^2=224/3, uv=72. Plane basis is y/z at x=2.
    Volume and J are explicit test inputs, not a B1 geometry result.
    """
    r = IntegralRequest("tilted-moment-fixture", HalfSpace((1, 0, 0), 2))
    w = WaterplaneMoments(PlaneFrame((2,0,0), (0,1,0), (0,0,1)), q(8),
                         (q(24), q(24)), (q(248/3, 1e-12), q(224/3, 1e-12), q(72)), 1, 0)
    return IntegralSample(reference().binding, r, q(40), (q(20), q(40), q(60)), w, "partial", 1)


class Checks(unittest.TestCase):
    def fails(self, code, fn, *args, **kwargs):
        with self.assertRaises(StabilityError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def encloses(self, data, expected):
        expected = Fraction(expected)
        self.assertLessEqual(Fraction(data["lower"]), expected)
        self.assertGreaterEqual(Fraction(data["upper"]), expected)


class IntervalTests(Checks):
    def test_conversion_encloses_exact_decimal_binary_input(self):
        for v, e in ((.1,.03), (0,1e-320), (-1e100,1e85), (1.,math.ulp(1.)/4)):
            out = Interval.of(q(v,e))
            self.encloses(out.to_dict(), Fraction(v)-Fraction(e))
            self.encloses(out.to_dict(), Fraction(v)+Fraction(e))

    def test_arithmetic_independent_rational_endpoint_oracle(self):
        rng = random.Random(914)
        for _ in range(200):
            a,b = sorted(rng.uniform(-100,100) for _ in range(2))
            c,d = sorted(rng.uniform(1,100) for _ in range(2))
            left,right = Interval(a,b), Interval(c,d)
            for fn, ref in ((lambda:left+right, lambda x,y:x+y),
                            (lambda:left-right, lambda x,y:x-y),
                            (lambda:left*right, lambda x,y:x*y),
                            (lambda:left/right, lambda x,y:x/y)):
                output = fn().to_dict()
                for x in (a,b,(a+b)/2):
                    for y in (c,d,(c+d)/2):
                        self.encloses(output, ref(Fraction(x),Fraction(y)))

    def test_square_crosses_zero(self):
        self.assertEqual(Interval(-3,2).square(), Interval(0,9))
        self.assertEqual(Interval(-3,-2).square(), Interval(4,9))

    def test_division_zero_refused(self):
        for i in (Interval(0,0),Interval(-1,1),Interval(-1,0),Interval(0,1)):
            self.fails(ErrorCode.ACCURACY_UNRESOLVED, lambda: Interval(1,1)/i)

    def test_overflow_is_typed(self):
        self.fails(ErrorCode.ACCURACY_UNRESOLVED, lambda: Interval(1e308,1e308)*Interval(2,2))
        self.fails(ErrorCode.ACCURACY_UNRESOLVED, Interval.of, q(1e308,1e308))

    def test_subnormal_outward_enclosure(self):
        i = Interval(5e-324,5e-324)/Interval(2,2)
        self.assertEqual(i.lower,0)
        self.assertEqual(i.upper,5e-324)
        self.encloses(i.to_dict(), Fraction(5e-324)/2)

    def test_bad_endpoints(self):
        for a,b in ((2,1),(True,1),(0,math.inf),(math.nan,1)):
            self.fails(ErrorCode.INPUT_INVALID,Interval,a,b)


class RecordTests(Checks):
    def test_general_frame_moments_and_CB(self):
        s = transformed_sample(); p = integral_properties(s)
        for a,b in zip(p["center_of_buoyancy_body_m"],(.5,1,1.5)):
            self.encloses(a,b)
        for a in p["waterplane_centroid_uv_m"]:self.encloses(a,3)
        self.encloses(p["waterplane_centroidal_m4"]["uu"],Fraction(32,3))
        self.encloses(p["waterplane_centroidal_m4"]["vv"],Fraction(8,3))
        self.encloses(p["waterplane_centroidal_m4"]["uv"],0)
        self.encloses(p["geometric_BM_m"]["about_u"],Fraction(1,15))
        self.encloses(p["geometric_BM_m"]["about_v"],Fraction(4,15))
        self.assertFalse(p["assurance"]["production_qualified"])

    def test_two_component_common_centroid_not_sum_local_inertias(self):
        s=transformed_sample()
        # Two 2x2 squares centered at u=-3 and +3: total A=8,
        # integral u^2=8/3 + 8*9, integral v^2=8/3.
        w=replace(s.waterplane,first_m3=(q(0),q(0)),
                  second_m4=(q(224/3,1e-12),q(8/3,1e-12),q(0)),components=2)
        p=integral_properties(replace(s,waterplane=w))
        self.encloses(p["waterplane_centroidal_m4"]["uu"],Fraction(224,3))
        self.assertGreater(p["waterplane_centroidal_m4"]["uu"]["lower"],70)

    def test_hole_aggregate_moments(self):
        s=transformed_sample()
        # Centered 4x4 square less centered 2x2 square: A=12, I=20.
        w=replace(s.waterplane,area_m2=q(12),first_m3=(q(0),q(0)),
                  second_m4=(q(20),q(20),q(0)),holes=1)
        p=integral_properties(replace(s,waterplane=w))
        self.encloses(p["waterplane_centroidal_m4"]["uu"],20)
        self.encloses(p["geometric_BM_m"]["about_u"],Fraction(1,2))

    def test_nonzero_product_moment(self):
        s=transformed_sample()
        w=replace(s.waterplane,first_m3=(q(0),q(0)),second_m4=(q(20),q(20),q(5)))
        p=integral_properties(replace(s,waterplane=w))
        self.encloses(p["waterplane_centroidal_m4"]["uv"],5)

    def test_empty_full_no_invented_centroids(self):
        for d,volume in ((-1,0),(5,800)):
            s=checked_query(reference(),request(d));p=integral_properties(s)
            self.assertEqual(s.volume_m3.value,volume)
            self.assertIsNone(p["waterplane_centroid_uv_m"])
            self.assertIsNone(p["geometric_BM_m"])
            self.assertEqual(p["waterplane_status"],"no_section")
            self.assertEqual(p["center_of_buoyancy_body_m"] is None,d<0)

    def test_uncertain_denominators_are_absent(self):
        s=transformed_sample()
        s=replace(s,volume_m3=q(1,2),waterplane=replace(s.waterplane,area_m2=q(1,2)))
        p=integral_properties(s)
        self.assertIsNone(p["center_of_buoyancy_body_m"])
        self.assertIsNone(p["waterplane_centroid_uv_m"])
        self.assertEqual(p["waterplane_status"],"area_division_unresolved")

    def test_frame_improper_or_unnormalized(self):
        self.fails(ErrorCode.INPUT_INVALID,PlaneFrame,(0,0,2),(2,0,0),(0,1,0))
        self.fails(ErrorCode.INPUT_INVALID,PlaneFrame,(0,0,2),(1,0,0),(1,0,0))
        w=reference().evaluate_integrals(request()).waterplane
        for frame in (PlaneFrame((0,0,2),(1,0,0),(0,-1,0)),
                      PlaneFrame((0,0,3),(1,0,0),(0,1,0))):
            self.fails(ErrorCode.INPUT_INVALID,replace,reference().evaluate_integrals(request()),
                       waterplane=replace(w,frame=frame))

    def test_rotated_frame_pose_plane_identity(self):
        pose=Pose(.2,.3,-2)
        r=pose.rotation
        # WORLD x/y expressed in BODY are the first two rows of R.
        n,d=pose.waterplane()
        frame=PlaneFrame(tuple(d*v for v in n),r[0],r[1])
        frame.validate_plane(HalfSpace(n,d))
        self.assertAlmostEqual(math.fsum(a*b for a,b in zip(n,frame.origin_body_m)),d)

    def test_raw_PSD_refuses_negative_and_excess_product(self):
        w=transformed_sample().waterplane
        for values in ((q(-1),q(20),q(0)),(q(1),q(1),q(2))):
            self.fails(ErrorCode.INPUT_INVALID,replace,w,first_m3=(q(0),q(0)),second_m4=values)

    def test_centroidal_PSD_refuses_inconsistent_first_moments(self):
        w=transformed_sample().waterplane
        self.fails(ErrorCode.INPUT_INVALID,replace,w,first_m3=(q(100),q(24)))

    def test_quality_cannot_upgrade_reference(self):
        s=transformed_sample()
        self.fails(ErrorCode.INPUT_INVALID,replace,s,certificate_ref="fake")
        self.fails(ErrorCode.INPUT_INVALID,replace,s,volume_m3=Quantity(40,0,"owner_certified_bound"))

    def test_declared_owner_requires_all_quantities_and_certificate(self):
        s=transformed_sample()
        b=replace(s.binding,source=replace(s.binding.source,geometry_assurance="owner_certified"),
                  artifact_sha256="a"*64,verifier_id="test-only-declaration")
        self.fails(ErrorCode.INPUT_INVALID,replace,s,binding=b)
        self.fails(ErrorCode.INPUT_INVALID,replace,s,binding=b,certificate_ref="still-only-declared")

    def test_owner_binding_needs_artifact_and_verifier(self):
        b=transformed_sample().binding
        source=replace(b.source,geometry_assurance="owner_certified")
        self.fails(ErrorCode.INPUT_INVALID,replace,b,source=source)
        self.fails(ErrorCode.INPUT_INVALID,replace,b,source=source,artifact_sha256="a"*64)
        self.fails(ErrorCode.INPUT_INVALID,replace,b,artifact_sha256="a"*64)

    def test_declared_owner_transport_still_does_not_verify_certificate(self):
        s=transformed_sample();d=s.to_dict()
        b=d["binding"];b["source"]["geometry_assurance"]="owner_certified"
        b["artifact_sha256"]="a"*64;b["verifier_id"]="test-only-nonexecuted"
        d["certificate_ref"]="not-a-real-owner-certificate"
        def mark(value):
            if isinstance(value,dict):
                if set(value)=={"value","error","assurance"}:value["assurance"]="owner_certified_bound"
                else:
                    for v in value.values():mark(v)
            elif isinstance(value,list):
                for v in value:mark(v)
        mark(d)
        restored=IntegralSample.from_dict(d)
        out=integral_properties(restored)
        self.assertEqual(out["assurance"]["owner_certificate"],"not_verified_by_postprocessing")
        self.assertFalse(out["assurance"]["production_qualified"])
        self.assertFalse(provider_status()["available"])

    def test_empty_and_component_consistency(self):
        s=transformed_sample()
        self.fails(ErrorCode.INPUT_INVALID,replace,s,immersion="empty")
        self.fails(ErrorCode.INPUT_INVALID,replace,s,immersion="full")
        self.fails(ErrorCode.INPUT_INVALID,replace,s.waterplane,components=0)
        self.fails(ErrorCode.INPUT_INVALID,replace,s.waterplane,components=True)

    def test_nested_json_roundtrip_and_detachment(self):
        s=transformed_sample();data=s.to_dict()
        self.assertEqual(s,IntegralSample.from_dict(decode_json(canonical_bytes(data))))
        data["binding"]["boundary_ids"].append("injected")
        self.assertNotIn("injected",s.binding.boundary_ids)
        with self.assertRaises(FrozenInstanceError):s.immersion="full"

    def test_nested_unknown_fields_and_versions(self):
        for edit in (lambda d:d.update(admitted=True),lambda d:d.update(version="future"),
                     lambda d:d["waterplane"].update(convention="inertia_tensor"),
                     lambda d:d["binding"].update(frame="WORLD"),
                     lambda d:d["binding"].update(units="mm"),
                     lambda d:d["volume_m3"].update(certified=True),
                     lambda d:d["request"]["accuracy"].update(extra=1)):
            d=transformed_sample().to_dict();edit(d)
            self.fails(ErrorCode.INPUT_INVALID,IntegralSample.from_dict,d)

    def test_nonstring_assurance_and_immersion_are_typed(self):
        for bad in ([], {}, True, None):
            self.fails(ErrorCode.INPUT_INVALID,Quantity,1,0,bad)
            self.fails(ErrorCode.INPUT_INVALID,replace,reference().binding.source,geometry_assurance=bad)
            self.fails(ErrorCode.INPUT_INVALID,replace,transformed_sample(),immersion=bad)

    def test_empty_volume_cannot_be_called_full(self):
        s=checked_query(reference(),request(-1))
        self.fails(ErrorCode.INPUT_INVALID,replace,s,immersion="full")

    def test_bounded_vectors_and_unique_boundary_selection(self):
        s=transformed_sample()
        for value in (None, (), (q(1),), (q(1),q(2),q(3),q(4))):
            self.fails(ErrorCode.INPUT_INVALID,replace,s,first_moments_m4=value)
        for ids in ((), ("x","x"), (True,)):
            self.fails(ErrorCode.INPUT_INVALID,replace,s.binding,boundary_ids=ids)

    def test_accuracy_bad_controls(self):
        for value in (True,-1,float("inf"),"1"):
            self.fails(ErrorCode.INPUT_INVALID,Accuracy,volume_m3=value)
        for value in (True,0,1.5,10000001):
            self.fails(ErrorCode.INPUT_INVALID,request,max_work_units=value)


class QueryTests(Checks):
    def test_reference_contract_and_properties(self):
        s=checked_query(reference(),request())
        p=integral_properties(s)
        self.encloses(p["volume_m3"],400)
        self.encloses(p["geometric_BM_m"]["about_u"],Fraction(25,6))
        self.encloses(p["geometric_BM_m"]["about_v"],Fraction(50,3))

    def test_cache_all_relevant_identity_changes(self):
        p=reference();r=request();h=r.cache_identity(p.binding)
        for changed in (replace(r,query_id="q2"),replace(r,plane=HalfSpace((0,0,1),math.nextafter(2,3))),
                        replace(r,accuracy=replace(r.accuracy,volume_m3=1e-9)),replace(r,max_work_units=4)):
            self.assertNotEqual(h,changed.cache_identity(p.binding))
        for b in (replace(p.binding,revision="new"),replace(p.binding,backend="native"),
                  replace(p.binding,supported_domain="other"),replace(p.binding,boundary_ids=("deck",))):
            self.assertNotEqual(h,r.cache_identity(b))

    def _changed(self, edit):
        base=reference()
        class Wrong:
            binding=base.binding
            def evaluate_integrals(self,r):return edit(base.evaluate_integrals(r))
        return Wrong()

    def test_changed_plane_rejected_even_sub_ulp_scale(self):
        # Change the whole returned request, updating frame to stay self-consistent.
        def edit(s):
            d=math.nextafter(s.request.plane.offset_m,3)
            r=replace(s.request,plane=HalfSpace((0,0,1),d))
            w=replace(s.waterplane,frame=replace(s.waterplane.frame,origin_body_m=(0,0,d)))
            return replace(s,request=r,waterplane=w)
        self.fails(ErrorCode.SOURCE_STALE,checked_query,self._changed(edit),request())

    def test_changed_accuracy_rejected(self):
        self.fails(ErrorCode.SOURCE_STALE,checked_query,self._changed(lambda s:replace(s,
            request=replace(s.request,accuracy=Accuracy(volume_m3=1)))),request())

    def test_foreign_binding_rejected(self):
        self.fails(ErrorCode.SOURCE_STALE,checked_query,self._changed(lambda s:replace(s,
            binding=replace(s.binding,revision="foreign"))),request())

    def test_untyped_result(self):
        self.fails(ErrorCode.INPUT_INVALID,checked_query,self._changed(lambda s:s.to_dict()),request())

    def test_all_five_accuracy_groups_enforced(self):
        base=reference()
        for field in Accuracy.__dataclass_fields__:
            with self.subTest(group=field):
                r=request(accuracy=replace(Accuracy(),**{field:0}))
                self.fails(ErrorCode.ACCURACY_UNRESOLVED,checked_query,base,r)

    def test_work_limit_enforced(self):
        self.fails(ErrorCode.WORK_BUDGET_EXCEEDED,checked_query,
                   self._changed(lambda s:replace(s,work_units=2)),request(max_work_units=1))

    def test_source_change_during_success(self):
        base=reference()
        class Changed:
            binding=base.binding
            def evaluate_integrals(self,r):
                result=base.evaluate_integrals(r)
                self.binding=replace(self.binding,revision="changed")
                return result
        self.fails(ErrorCode.SOURCE_STALE,checked_query,Changed(),request())

    def test_original_refusal_unchanged(self):
        error=StabilityError(ErrorCode.QUERY_DEGENERATE,"owner tangent",owner_code="P4")
        class Refusing:
            binding=reference().binding
            def evaluate_integrals(self,r):raise error
        caught=self.fails(ErrorCode.QUERY_DEGENERATE,checked_query,Refusing(),request())
        self.assertIs(caught,error)

    def test_source_change_during_refusal(self):
        class Refusing:
            binding=reference().binding
            def evaluate_integrals(self,r):
                self.binding=replace(self.binding,revision="changed")
                raise StabilityError(ErrorCode.QUERY_DEGENERATE,"tangent",owner_code="P4")
        e=self.fails(ErrorCode.SOURCE_STALE,checked_query,Refusing(),request())
        self.assertEqual(e.details["provider_cause"]["details"]["owner_code"],"P4")

    def test_batch_refusal_retained_with_original_plane(self):
        result=checked_batch(reference(),[request(1,"a"),request(0,"b"),request(2,"c")])
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["attempted_count"],3)
        self.assertEqual([e["status"] for e in result["entries"]],["evaluated","refused","evaluated"])
        bad=result["entries"][1]
        self.assertEqual(bad["request"]["plane"]["offset_m"],0)
        self.assertEqual(bad["error"]["code"],"QUERY_DEGENERATE")

    def test_bad_batch_fails_before_any_provider_call(self):
        with patch.object(ReferenceBoxIntegrals,"evaluate_integrals",side_effect=AssertionError("no queries")):
            self.fails(ErrorCode.WORK_BUDGET_EXCEEDED,checked_batch,reference(),[request(),request(name="b")],max_queries=1)
            self.fails(ErrorCode.INPUT_INVALID,checked_batch,reference(),[request(),request()])
            self.fails(ErrorCode.INPUT_INVALID,checked_batch,reference(),[None])
            self.fails(ErrorCode.INPUT_INVALID,checked_batch,reference(),[],max_queries=True)
            self.fails(ErrorCode.INPUT_INVALID,checked_batch,reference(),[])

    def test_fatal_batch_refusal_aborts_remaining_work(self):
        result=checked_batch(self._changed(lambda s:s.to_dict()),[request(1,"a"),request(2,"b")])
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["attempted_count"],1)
        self.assertEqual(result["entries"][1]["status"],"not_executed")

    def test_unexpected_exception_not_hidden(self):
        class Broken:
            binding=reference().binding
            def evaluate_integrals(self,r):raise RuntimeError("bug")
        with self.assertRaises(RuntimeError):checked_batch(Broken(),[request()])

    def test_reference_never_clips_tilted_hull(self):
        self.fails(ErrorCode.CAPABILITY_UNSUPPORTED,checked_query,reference(),
                   IntegralRequest("sideways",HalfSpace((1,0,0),2)))


class HandoffTests(Checks):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.manifest=self.root/"handoff.json"

    def make_bundle(self, *, wheel_name="ANYgeometry", wheel_version="9.9.dev0"):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            z.writestr("anygeometry/__init__.py",'raise AssertionError("MUST NOT EXECUTE")\n')
            z.writestr("anygeometry-9.9.dev0.dist-info/METADATA",f"Name: {wheel_name}\nVersion: {wheel_version}\n")
        d=dict(kind=KIND,provider_id="anygeometry_h1",source_commit="1"*40,
               distribution_version="9.9.dev0",owner_api_version="test-only",artifacts=[])
        for role in sorted(REQUIRED_ROLES):
            filename=role+(".whl" if role=="wheel" else ".txt")
            data=stream.getvalue() if role=="wheel" else b"test-only, no B1 evidence"
            (self.root/filename).write_bytes(data)
            d["artifacts"].append(dict(role=role,path=filename,sha256=hashlib.sha256(data).hexdigest()))
        self.write(d)
        return d

    def write(self,d):self.manifest.write_bytes(canonical_bytes(d))

    def test_complete_byte_receipt_is_still_not_admission(self):
        self.make_bundle();r=inspect_handoff(self.manifest)
        self.assertEqual(r["missing_roles"],[])
        self.assertEqual(r["status"],"blocked_not_admitted")
        self.assertFalse(r["production_qualified"])
        self.assertFalse(r["owner_code_executed"])
        self.assertEqual(r["Q08"],"not_executed")
        self.assertEqual(r["source_authenticity"],"not_verified")

    def test_missing_role_report_not_fabricated(self):
        d=self.make_bundle();d["artifacts"]=[];self.write(d)
        r=inspect_handoff(self.manifest)
        self.assertEqual(r["missing_roles"],sorted(REQUIRED_ROLES))
        self.assertIsNone(r["wheel_metadata"])

    def test_handoff_cli_returns_nonzero_even_with_complete_declared_bytes(self):
        self.make_bundle()
        r=subprocess.run([sys.executable,"-m","anystability","inspect-handoff",str(self.manifest)],
                         capture_output=True,text=True)
        self.assertEqual(r.returncode,2,r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"],"blocked_not_admitted")

    def test_corrupt_bytes_refused(self):
        d=self.make_bundle();(self.root/d["artifacts"][0]["path"]).write_bytes(b"changed")
        self.fails(ErrorCode.INTEGRITY_ERROR,inspect_handoff,self.manifest)

    def test_wrong_distribution_refused(self):
        self.make_bundle(wheel_name="other")
        self.fails(ErrorCode.INTEGRITY_ERROR,inspect_handoff,self.manifest)

    def test_wrong_version_refused(self):
        self.make_bundle(wheel_version="1.0")
        self.fails(ErrorCode.INTEGRITY_ERROR,inspect_handoff,self.manifest)

    def test_unknown_admission_or_code_instructions_refused(self):
        for key in ("admitted","verifier_module","run_command"):
            d=self.make_bundle();d[key]="arbitrary.py";self.write(d)
            self.fails(ErrorCode.INPUT_INVALID,inspect_handoff,self.manifest)

    def test_unsafe_paths(self):
        for path in ("../escape","/absolute","a//b","./a","a/../b","C:/x","a\\b"):
            d=self.make_bundle();d["artifacts"][0]["path"]=path;self.write(d)
            self.fails(ErrorCode.INPUT_INVALID,inspect_handoff,self.manifest)

    def test_symlink_and_parent_symlink(self):
        self.make_bundle()
        link=self.root/"link"
        try:link.symlink_to(self.root,target_is_directory=True)
        except OSError:self.skipTest("platform does not permit symlink creation")
        self.fails(ErrorCode.IO_ERROR,inspect_handoff,link/"handoff.json")
        d=self.make_bundle();a=d["artifacts"][0]
        p=self.root/a["path"];p.unlink();p.symlink_to(self.manifest)
        self.fails(ErrorCode.IO_ERROR,inspect_handoff,self.manifest)

    def test_missing_file_and_oversize_limits(self):
        d=self.make_bundle();(self.root/d["artifacts"][0]["path"]).unlink()
        self.fails(ErrorCode.IO_ERROR,inspect_handoff,self.manifest)
        self.make_bundle()
        with patch("anystability.providers.handoff.MAX_ARTIFACT_BYTES",1):
            self.fails(ErrorCode.IO_ERROR,inspect_handoff,self.manifest)

    def test_duplicate_role_or_path(self):
        d=self.make_bundle();d["artifacts"].append(d["artifacts"][0]);self.write(d)
        self.fails(ErrorCode.INPUT_INVALID,inspect_handoff,self.manifest)
        d=self.make_bundle();d["artifacts"][1]["path"]=d["artifacts"][0]["path"];self.write(d)
        self.fails(ErrorCode.INPUT_INVALID,inspect_handoff,self.manifest)

    def test_invalid_wheel_archive(self):
        d=self.make_bundle();a=next(a for a in d["artifacts"] if a["role"]=="wheel")
        data=b"not a zip";a["sha256"]=hashlib.sha256(data).hexdigest()
        (self.root/a["path"]).write_bytes(data);self.write(d)
        self.fails(ErrorCode.INTEGRITY_ERROR,inspect_handoff,self.manifest)

    def test_wheel_traversal_and_duplicate_metadata(self):
        for extra in ("../escape","other.dist-info/METADATA"):
            d=self.make_bundle();a=next(a for a in d["artifacts"] if a["role"]=="wheel")
            p=self.root/a["path"]
            with zipfile.ZipFile(p,"a") as z:z.writestr(extra,b"bad")
            a["sha256"]=hashlib.sha256(p.read_bytes()).hexdigest();self.write(d)
            self.fails(ErrorCode.INPUT_INVALID,inspect_handoff,self.manifest)

    def test_metadata_probe_does_not_admit_any_version(self):
        with patch("anystability.providers.handoff.metadata.version",return_value="999.0"):
            status=provider_status()
            self.assertEqual(status["installed_distribution_version"],"999.0")
            self.assertFalse(status["available"])
            p=example_project();s=GeometrySource("anygeometry_h1",'{"model_id":"declared"}')
            self.fails(ErrorCode.PROVIDER_UNAVAILABLE,provider_for,
                       replace(p,vessel=replace(p.vessel,geometry=s)),allow_reference=True)


class S2ServiceTests(Checks):
    def test_integral_service_requires_explicit_opt_in(self):
        self.fails(ErrorCode.CAPABILITY_UNSUPPORTED,analyze_integrals,example_project(),pose=Pose(origin_z_m=-2))
        r=analyze_integrals(example_project(),pose=Pose(origin_z_m=-2),allow_reference=True)
        self.encloses(r["volume_m3"],400)
        self.assertFalse(r["assurance"]["production_qualified"])

    def test_legacy_result_engine_retained_during_reproduction(self):
        d=analyze(example_project(),allow_reference=True).to_dict()
        d["engine"]["version"]="0.1.0.dev0"
        old=AnalysisRecord(canonical_bytes(d).decode())
        self.assertEqual(reproduce(old),old)
        d["engine"]["version"]="0.0.0"
        self.fails(ErrorCode.CAPABILITY_UNSUPPORTED,AnalysisRecord,canonical_bytes(d).decode())

    def test_s2_record_not_misloaded_as_completed_analysis(self):
        self.fails(ErrorCode.INPUT_INVALID,AnalysisRecord,canonical_bytes(transformed_sample().to_dict()).decode())

    def test_cli_provider_check_nonzero_and_optional_imports(self):
        r=subprocess.run([sys.executable,"-m","anystability","provider-check"],capture_output=True,text=True)
        self.assertEqual(r.returncode,2,r.stderr)
        self.assertEqual(json.loads(r.stdout)["Q08"],"blocked_not_executed")
        code='''import sys
before=set(sys.modules)
from anystability.providers.handoff import provider_status
from anystability.providers.integrals import checked_batch
from anystability.hydrostatics import integral_properties
provider_status()
for p in ('anygeometry','anyhydro','anymarine','anysolver','numpy','scipy','PySide6','capytaine'):
    assert p not in set(sys.modules)-before, p
'''
        r=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_cli_integrals_and_strict_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            def cli(*args):return subprocess.run([sys.executable,"-m","anystability",*args],capture_output=True,text=True)
            root=str(Path(tmp)/"p");self.assertEqual(cli("example",root).returncode,0)
            r=cli("integrals",root,"--draft-m","2","--allow-reference")
            self.assertEqual(r.returncode,0,r.stderr)
            self.encloses(json.loads(r.stdout)["volume_m3"],400)
            acc=Path(tmp)/"accuracy.json";acc.write_bytes(canonical_bytes(Accuracy(volume_m3=0).to_dict()))
            r=cli("integrals",root,"--draft-m","2","--allow-reference","--accuracy-json",str(acc))
            self.assertEqual(r.returncode,2)
            self.assertEqual(json.loads(r.stderr)["code"],"ACCURACY_UNRESOLVED")
