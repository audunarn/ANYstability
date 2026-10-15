"""No-owner tests for the development boundary, NOT real H1 qualification."""
import copy
from dataclasses import FrozenInstanceError
from importlib import metadata
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from anystability.errors import ErrorCode, StabilityError
from anystability.providers.anygeometry_h1 import (H1DevelopmentProvider, H1Query,
    map_owner_result, verify_installed_owner, _payload_digest)
from anystability.providers.h1_worker import execute_job, run_job
from anystability.providers.handoff import require_production_provider
from anystability.providers.protocol import HalfSpace
from anystability.providers.integrals import IntegralRequest


def sample():
    return dict(volume=400., waterplane_area=200., estimate=1e-15,
        frame=SimpleNamespace(origin=(0.,0.,2.), axes=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))),
        buoyancy_centre=(0.,0.,1.), flotation_centre=(0.,0.,2.),
        i_transverse=5000/3, i_longitudinal=20000/3, i_product=0.,
        bm_transverse=25/6, bm_longitudinal=50/3)


class H1BoundaryTests(unittest.TestCase):
    def fails(self, code, func, *args, **kwargs):
        with self.assertRaises(StabilityError) as caught:
            func(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_opt_in_before_discovery(self):
        with patch('anystability.providers.anygeometry_h1.metadata.distribution') as lookup:
            for value in (False, None, 1, 'yes'):
                self.fails(ErrorCode.CAPABILITY_UNSUPPORTED, verify_installed_owner, allow_development=value)
            lookup.assert_not_called()

    def test_missing_owner(self):
        with patch('anystability.providers.anygeometry_h1.metadata.distribution', side_effect=metadata.PackageNotFoundError):
            self.fails(ErrorCode.PROVIDER_UNAVAILABLE, verify_installed_owner, allow_development=True)

    def test_plain_production_stays_unavailable(self):
        self.fails(ErrorCode.PROVIDER_UNAVAILABLE, require_production_provider)

    def test_bad_order(self):
        for order in (True, 0, 3, 49, 24.5):
            self.fails(ErrorCode.INPUT_INVALID, H1Query, HalfSpace((0,0,1),2), order)

    def test_bad_rtol(self):
        for value in (True, 0., 1e-15, .1, math.inf, math.nan):
            self.fails(ErrorCode.INPUT_INVALID, H1Query, HalfSpace((0,0,1),2), rtol=value)

    def test_typed_request_only(self):
        self.fails(ErrorCode.INPUT_INVALID, H1Query, {'normal':[0,0,1], 'offset_m':2})
        self.fails(ErrorCode.INPUT_INVALID, H1Query, IntegralRequest('p',HalfSpace((0,0,1),2)))

    def test_request_immutable(self):
        q=H1Query(HalfSpace((0,0,1),2))
        with self.assertRaises(FrozenInstanceError):
            q.rtol=1e-4

    def test_source_hash_changes_with_code_or_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'__init__.py').write_text('x=1\n')
            a,n=_payload_digest(p)
            self.assertEqual(n,1)
            (p/'__init__.py').write_text('x=2\n')
            self.assertNotEqual(a,_payload_digest(p)[0])
            (p/'extra.py').write_text('x=1\n')
            self.assertEqual(_payload_digest(p)[1],2)

    def test_unverified_native_code_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'_core.so').write_bytes(b'not admitted')
            self.fails(ErrorCode.CAPABILITY_UNSUPPORTED,_payload_digest,Path(d))

    def test_map_units_and_assurance(self):
        value=map_owner_result(sample(), H1Query(HalfSpace((0,0,1),2)))
        self.assertEqual(value['volume_m3'],400)
        self.assertAlmostEqual(value['geometric_BM']['about_xi_m'],25/6)
        self.assertIsNone(value['quantity_error_bounds'])
        self.assertIsNone(value['section_topology'])
        self.assertFalse(value['plane_mapping']['exact_mapping_certified'])
        self.assertEqual(value['order_doubling_indicator'],1e-15)

    def test_map_rejects_extra_certification_flag(self):
        raw=sample(); raw['certified']=True
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_map_rejects_shifted_plane(self):
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,sample(),H1Query(HalfSpace((0,0,1),2.01)))

    def test_map_rejects_improper_frame(self):
        raw=sample(); raw['frame'].axes=((1.,0.,0.),(0.,-1.,0.),(0.,0.,1.))
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_map_rejects_inconsistent_BM(self):
        raw=sample(); raw['bm_transverse']=1
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_missing_BM_not_invented(self):
        raw=sample(); del raw['bm_transverse']; del raw['bm_longitudinal']
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_unsettled_owner_indicator_refused(self):
        raw=sample(); raw['estimate']=1e-4
        self.fails(ErrorCode.ACCURACY_UNRESOLVED,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_negative_values_not_clamped(self):
        for name in ('volume','waterplane_area','i_transverse','i_longitudinal'):
            raw=sample(); raw[name]=-1e-15
            self.fails(ErrorCode.ACCURACY_UNRESOLVED,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_centroid_presence_consistency(self):
        raw=sample(); raw['buoyancy_centre']=None
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_CF_plane_consistency(self):
        raw=sample(); raw['flotation_centre']=(0,0,3)
        self.fails(ErrorCode.INTEGRITY_ERROR,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_empty_and_full_do_not_invent_BM(self):
        for volume,cb in ((0,None),(800,(0,0,2))):
            raw=sample(); raw.update(volume=volume,buoyancy_centre=cb,waterplane_area=0.,flotation_centre=None,
                                    i_transverse=0.,i_longitudinal=0.,i_product=0.)
            del raw['bm_transverse'];del raw['bm_longitudinal']
            v=map_owner_result(raw,H1Query(HalfSpace((0,0,1),2)))
            self.assertIsNone(v['geometric_BM'])
            self.assertEqual(v['immersion'],'not_certified_by_owner')

    def test_nearzero_area_without_bound_refused(self):
        raw=sample();raw['waterplane_area']=1e-15
        self.fails(ErrorCode.ACCURACY_UNRESOLVED,map_owner_result,raw,H1Query(HalfSpace((0,0,1),2)))

    def test_job_unknown_action_rejected_before_owner(self):
        self.fails(ErrorCode.INPUT_INVALID,execute_job,dict(action='exec',allow_development=True,query=None,snapshot=None))

    def test_job_unknown_fields_rejected_before_owner(self):
        self.fails(ErrorCode.INPUT_INVALID,execute_job,dict(action='query_b1',allow_development=True,query=None,snapshot=None,code='ignored'))

    def test_process_timeout_never_admits_result(self):
        with patch('anystability.providers.h1_worker.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',1)):
            self.fails(ErrorCode.WORK_BUDGET_EXCEEDED,run_job,dict(allow_development=True),wall_seconds=1)

    def test_process_wall_limit_validation(self):
        for limit in (0,301,True,math.inf):
            self.fails(ErrorCode.INPUT_INVALID,run_job,dict(allow_development=True),wall_seconds=limit)

    def test_cli_opt_in_required(self):
        result=subprocess.run([sys.executable,'-I','-m','anystability','h1-query','--b1','--draft-m','1.75'],capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertIn(b'CAPABILITY_UNSUPPORTED',result.stderr)

    def test_legacy_dev1_result_preserved(self):
        from anystability.services import AnalysisRecord, analyze, example_project, reproduce
        from anystability.validation import canonical_bytes
        record=analyze(example_project(),allow_reference=True)
        data=record.to_dict();data['engine']['version']='0.1.0.dev1'
        old=AnalysisRecord(canonical_bytes(data).decode())
        self.assertEqual(reproduce(old).to_dict()['engine']['version'],'0.1.0.dev1')


if __name__ == '__main__':
    unittest.main()
