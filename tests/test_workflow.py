"""Independent analytic prisms; these tests never import a real geometry owner."""
import copy
import math
from pathlib import Path
import tempfile
import types
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from anystability.conventions import Pose
from anystability.domain import LoadingCondition, MassItem
from anystability.errors import ErrorCode, StabilityError
from anystability.validation import canonical_bytes, content_hash
from anystability import workflow as w


def source():
    vertices=[[x,y,z] for x in (-5.,5.) for y in (-2.,2.) for z in (0.,4.)]
    tv=[[x,y,z] for x in (-1.,1.) for y in (-.5,.5) for z in (0.,4.)]
    return dict(manifest=dict(owner=dict(version='historical'),capacity_comparisons={
        'HULL':dict(volume_m3=160.,centroid_body_m=[0.,0.,2.]),
        'WB3':dict(volume_m3=8.,centroid_body_m=[0.,0.,2.])}),
        files={'definition.json':dict(hull=dict(faces_body_m=[vertices]),spaces={'WB3':dict(faces_body_m=[tv])}),
            'HULL.geometry.json':{},'WB3.geometry.json':{}})


def study(tanks=False,**kw):
    # 40m3 displaced at z=-1, body CG at0.5; GM=4/3+0.5-0.5=4/3.
    base=LoadingCondition('test','Analytic test',(MassItem('dry',40000.-(1000. if tanks else 0.),(0.,0.,.5),'analytic',('dry',)),),1000.,10.)
    return w.create_stability_study(source(),base_condition=base,
        targets_m3={'WB3':1.} if tanks else {}, densities_kg_m3={'WB3':1000.} if tanks else {},
        initial_pose=Pose(0.,0.,-1.),pose_bounds=[[-3.5,-.2],[-.5,.5],[-.3,.3]],
        owner_wheel='fake-wheel',allow_development=True,**kw)


class AnalyticProvider:
    calls=[]
    def __init__(self,spec,poll,deadline):
        self.spec=spec; self.poll=poll
    def query(self,name,pose,offset,identity):
        self.poll(); self.calls.append((name,pose,offset))
        # Direct integral of z=c+sx*x+sy*y over an uncut rectangular footprint.
        nx,ny,nz=pose.rotation[2]; c=offset/nz; sx=-nx/nz; sy=-ny/nz
        length,beam=(10.,4.) if name=='HULL' else (2.,1.)
        if c>=4+abs(sx)*length/2+abs(sy)*beam/2:
            return dict(volume_m3=length*beam*4,cg_body_m=[0.,0.,2.],assurance='analytic_fake',waterplane_area_m2=0.,i_transverse_m4=0.)
        if c<=abs(sx)*length/2+abs(sy)*beam/2 or c>=4-abs(sx)*length/2-abs(sy)*beam/2:
            raise StabilityError(ErrorCode.QUERY_DEGENERATE,'analytic fixture excludes top/bottom clipping')
        volume=length*beam*c
        cg=[sx*length**2/(12*c),sy*beam**2/(12*c),(c*c+(sx*sx*length**2+sy*sy*beam**2)/12)/(2*c)]
        area=length*beam/nz
        u,v=pose.rotation[1][0]+pose.rotation[1][2]*sx,pose.rotation[1][1]+pose.rotation[1][2]*sy
        return dict(volume_m3=volume,cg_body_m=cg,assurance='analytic_fake',
            waterplane_area_m2=area,i_transverse_m4=area*(u*u*length**2+v*v*beam**2)/12)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        AnalyticProvider.calls=[]
        self.p=patch.object(w,'_OwnerProvider',AnalyticProvider); self.p.start(); self.addCleanup(self.p.stop)

    def test_analytic_equilibrium_and_immutability(self):
        s=study(); original=s.identity
        detached=s.to_dict(); detached['targets_m3']['WB3']=4
        self.assertEqual(s.identity,original)
        r=w.solve_floating_equilibrium(s).to_dict()
        self.assertEqual(r['status'],'complete')
        eq=r['equilibrium']; self.assertAlmostEqual(eq['mass_kg'],40000.)
        self.assertAlmostEqual(eq['gz_m'],0.)
        self.assertAlmostEqual(eq['hydrostatic_GM_m'],4/3)
        self.assertEqual(r['work']['attempted_owner_queries'],1)
        self.assertFalse(r['assurance']['production_qualified'])

    def test_newton_solve_from_wrong_initial_draft(self):
        s=study(); d=s.to_dict(); d['initial_pose']=Pose(.02,.01,-1.15).to_dict()
        r=w.solve_floating_equilibrium(w.EngineeringStudy(canonical_bytes(d))).to_dict()
        self.assertEqual(r['status'],'complete',r['failures'])
        self.assertLess(abs(r['equilibrium']['vertical_residual_N']),1.)
        self.assertLess(abs(r['equilibrium']['generalized_Qheel_Nm']),1.)

    def test_mirror_branches_and_signed_area(self):
        s=study(); r=w.calculate_gz_curve(s,heels_rad=[-.1,0,.1],controls={'max_points':25,'max_evaluations':200}).to_dict()
        self.assertEqual(r['status'],'complete',r['failures'])
        points={round(p['heel_rad'],9):p for p in r['points']}
        self.assertAlmostEqual(points[.1]['gz_m'],-points[-.1]['gz_m'],places=10)
        self.assertGreater(r['metrics']['branches']['positive']['signed_area_estimate_mrad'],0)
        self.assertLess(r['metrics']['branches']['negative']['signed_area_estimate_mrad'],0)
        self.assertAlmostEqual(r['metrics']['effective_moving_liquid_gz_slope_m'],4/3,delta=.003)

    def test_actual_tank_conservation_cache_and_weight_once(self):
        s=study(True); ex=w._Execution(s,{'controls':w.workflow_defaults()},None,None)
        pose=Pose(.08,.015,-1.); a=ex.tank('WB3',pose)
        count=len(ex.queries); b=ex.tank('WB3',Pose(.08,.015,-1.5))
        self.assertEqual(a,b); self.assertEqual(len(ex.queries),count)
        self.assertLessEqual(abs(a['residual_volume_m3']),1e-9)
        self.assertNotEqual(a['cg_body_m'][1],0.)
        state=ex.evaluate([-1.,.08,.015],'test')
        self.assertEqual(state['mass_kg'],40000.)
        self.assertEqual(state['free_surface_treatment'],'actual_CG_only_no_added_FSM')

    def test_cancel_budget_checkpoint_and_safe_resume(self):
        events=[]; cancelled=[False]
        def progress(e):
            events.append(e)
            if e['phase']=='accepted_equilibrium': cancelled[0]=True
        s=study(); r=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],progress=progress,cancellation_check=lambda:cancelled[0],controls={'max_points':15}).to_dict()
        self.assertEqual(r['status'],'cancelled')
        checkpoint=next(e['result'] for e in events if e['phase']=='accepted_equilibrium')
        self.assertEqual(checkpoint['equilibrium'],r['equilibrium'])
        seed=w.EngineeringResult(canonical_bytes(r)); cancelled[0]=False
        resumed=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],seed_result=seed,controls={'max_points':15}).to_dict()
        self.assertGreater(resumed['work']['attempted_owner_queries'],r['work']['attempted_owner_queries'])
        self.assertGreaterEqual(resumed['work']['elapsed_wall_seconds'],r['work']['elapsed_wall_seconds'])
        budget=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],controls={'max_owner_queries':1}).to_dict()
        self.assertEqual(budget['status'],'partial')
        self.assertEqual(budget['work']['attempted_owner_queries'],1)
        self.assertIsNone(budget['metrics']['branches']['negative']['sampled_signed_area_mrad'])

    def test_refusal_stops_one_branch_and_keeps_other(self):
        original=AnalyticProvider.query
        def query(self,name,pose,*args):
            if pose.heel_rad<-.04: raise StabilityError(ErrorCode.QUERY_DEGENERATE,'exact event')
            return original(self,name,pose,*args)
        with patch.object(AnalyticProvider,'query',query):
            r=w.calculate_gz_curve(study(),heels_rad=[-.05,0,.05],controls={'max_points':15}).to_dict()
        self.assertEqual(r['branches']['negative']['status'],'partial')
        self.assertTrue(any(p['heel_rad']>0 for p in r['points']))
        self.assertEqual(r['status'],'partial')

    def test_point_cap_is_partial_and_metrics_unavailable(self):
        r=w.calculate_gz_curve(study(),heels_rad=[-.1,0,.1],controls={'max_points':3}).to_dict()
        self.assertEqual(r['status'],'partial')
        self.assertIsNone(r['metrics']['branches']['positive']['signed_area_estimate_mrad'])

    def test_saved_reopen_report_and_corruption(self):
        s=study(); r=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],controls={'max_points':15})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'study.json'; w.save_stability_study(s,path,result=r)
            with patch.object(w,'_OwnerProvider',side_effect=AssertionError('owner-free')):
                a,b=w.load_stability_study(path); self.assertEqual(b.identity,r.identity)
                report=w.export_stability_report(a,b,Path(folder)/'report')
                self.assertEqual(len(report['manifest']['files']),6)
                self.assertTrue((Path(folder)/'report'/'manifest.json').exists())
            raw=path.read_bytes(); path.write_bytes(raw.replace(b'40000.0',b'40001.0',1))
            with self.assertRaises(StabilityError): w.load_stability_study(path)

    def test_empty_full_and_invalid_mass_coverage(self):
        s=study(True); d=s.to_dict(); d['targets_m3']['WB3']=0.
        ex=w._Execution(w.EngineeringStudy(canonical_bytes(d)),{'controls':w.workflow_defaults()},None,None)
        self.assertEqual(ex.tank('WB3',Pose())['state'],'empty'); self.assertEqual(len(ex.queries),0)
        d['targets_m3']['WB3']=8.
        ex=w._Execution(w.EngineeringStudy(canonical_bytes(d)),{'controls':w.workflow_defaults()},None,None)
        self.assertEqual(ex.tank('WB3',Pose())['state'],'full')
        d['base_condition']['items'][0]['covers']=['tank:WB3:liquid']
        with self.assertRaises(StabilityError): w.EngineeringStudy(canonical_bytes(d))

    def test_opening_immersion_refinement(self):
        opening=dict(name='port opening',point_body_m=[0.,2.,1.05],closing_status='open',limits_intact=True)
        r=w.calculate_gz_curve(study(openings=[opening]),heels_rad=[-.1,0,.1],controls={'max_points':80,'max_evaluations':300}).to_dict()
        limit=r['branches']['negative']['intact_limit']
        self.assertIsNotNone(limit)
        self.assertLessEqual(limit['angle_uncertainty_rad'],math.radians(.1))
        self.assertEqual(r['metrics']['criteria'],'not_evaluated')

    def test_finite_trim_physical_and_generalized_distinct(self):
        s=study(); ex=w._Execution(s,{'controls':w.workflow_defaults()},None,None)
        state=ex.evaluate([-1.,.08,.03],'finite_attitude')
        tx,ty,tz=state['physical_torque_world_Nm']
        self.assertAlmostEqual(state['generalized_Qheel_Nm'],math.cos(.03)*tx+math.sin(.03)*tz)
        self.assertEqual(state['righting_moment_Nm'],-tx)
        self.assertNotEqual(state['generalized_Qheel_Nm'],-state['righting_moment_Nm'])

    def test_initially_immersed_opening_stops_both_branches_at_origin(self):
        for closing_status in ('open','unknown'):
            opening=dict(name='already wet',point_body_m=[0.,0.,.9],closing_status=closing_status,limits_intact=True)
            r=w.calculate_gz_curve(study(openings=[opening]),heels_rad=[-.1,0.,.1]).to_dict()
            self.assertEqual(r['work']['attempted_owner_queries'],1)
            self.assertEqual(len(r['points']),1)
            for name,branch in r['branches'].items():
                self.assertEqual(branch['status'],'intact_limit')
                self.assertEqual(branch['intact_limit']['resolution'],'initially_immersed')
                self.assertEqual(branch['intact_limit']['heel_rad'],0.)
                self.assertEqual(branch['intervals'],[])
                self.assertIsNone(r['metrics']['branches'][name]['signed_area_estimate_mrad'])
                self.assertIsNone(r['metrics']['branches'][name]['sampled_signed_area_mrad'])

    def test_opening_immersed_at_fixed_trim_origin_stops_before_targets(self):
        opening=dict(name='forward opening',point_body_m=[-4.,0.,1.01],closing_status='open',limits_intact=True)
        r=w.calculate_gz_curve(study(openings=[opening]),mode='fixed_trim',fixed_trim_rad=.02,
            heels_rad=[-.1,0.,.1]).to_dict()
        self.assertFalse(r['equilibrium']['openings'][0]['immersed'])
        self.assertTrue(r['points'][0]['openings'][0]['immersed'])
        self.assertEqual(r['points'][0]['trim_rad'],.02)
        self.assertTrue(all(e['pose']['heel_rad']==0. for e in r['work']['evaluations']))
        self.assertTrue(all(b['intact_limit']['resolution']=='initially_immersed' for b in r['branches'].values()))

    def test_exact_zero_and_coarse_peak_angle_not_fabricated(self):
        r=w.calculate_gz_curve(study(),heels_rad=[0,.05,.1],controls={'max_points':25}).to_dict()
        eq=r['equilibrium']; branch=r['branches']['positive']
        points=[]
        for angle,value in ((0.,0.),(.05,.02),(.1,0.)):
            points.append(w._point(dict(eq,heel_rad=angle,gz_m=value),'positive'))
        r['points']=points; branch['point_identities']=[p['identity'] for p in points]
        branch['status']='complete'; branch['intervals']=[dict(status='engineering_estimate_resolved')]
        r['branches']={'positive':branch}
        metrics=w._metrics(r)['branches']['positive']
        self.assertEqual(metrics['vanishing_angle_estimate_rad'],.1)
        self.assertIsNone(metrics['maximum_gz_angles_estimate_rad'])
        self.assertEqual(metrics['maximum_angle_reason'],'unresolved_extremum_angle_bracket')

    def test_peak_on_coarse_point_and_offset_peak_refine(self):
        for centre in (.05,.063):
            real_solve=w._Execution.solve
            def solve(ex,q,axes,purpose):
                state=real_solve(ex,q,axes,purpose)
                if purpose!='initial_equilibrium':
                    # Independent prescribed smooth GZ diagnostic fixture.
                    state['gz_m']=q[1]*(2*centre-q[1])*10
                return state
            with patch.object(w._Execution,'solve',solve):
                r=w.calculate_gz_curve(study(),heels_rad=[0,.025,.05,.075,.1],
                    controls={'max_points':180,'max_evaluations':600}).to_dict()
            m=r['metrics']['branches']['positive']
            self.assertIsNotNone(m['maximum_gz_angles_estimate_rad'],r['failures'])
            self.assertAlmostEqual(m['maximum_gz_angles_estimate_rad'][0],centre,delta=math.radians(.1))

    def test_cli_saved_metrics_and_report_owner_free(self):
        from anystability.cli import parser,execute
        s=study(); r=w.solve_floating_equilibrium(s)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'saved.json'; w.save_stability_study(s,path,result=r)
            metrics=execute(parser().parse_args(['stability-metrics',str(path)]))
            self.assertAlmostEqual(metrics['hydrostatic_GM_m'],4/3)
            report=execute(parser().parse_args(['stability-report',str(path),str(Path(folder)/'report')]))
            self.assertIn('result.json',report['manifest']['files'])

    def test_certified_bridge_actual_envelope_and_deadline(self):
        from anystability.providers import certified
        module=types.ModuleType('anygeometry'); serialization=types.ModuleType('anygeometry.serialization')
        serialization.from_dict=lambda document:SimpleNamespace(faces={4:None})
        runtime=dict(version='0.4.8',wheel_sha256=w.PIN)
        section=dict(convention='raw_u2_v2_uv',area_m2={'value':40.},first_m3=[{'value':0.},{'value':0.}],
            second_m4=[{'value':1000/3},{'value':160/3},{'value':0.}])
        sample=dict(volume_m3={'value':40.},first_moments_m4=[{'value':0.},{'value':0.},{'value':20.}],waterplane=section)
        record=dict(payload=dict(sample=sample),sha256='test-only')
        # Restore actual provider implementation while every optional import and
        # public owner operation is replaced with an explicit fabricated module.
        self.p.stop()
        with patch.dict('sys.modules',{'anygeometry':module,'anygeometry.serialization':serialization}), \
                patch.object(certified,'authenticate_installed_owner',return_value=runtime), \
                patch.object(certified,'certified_point',return_value=record) as call:
            d=study().to_dict(); d['geometry_mode']='certified_point'
            provider=w._OwnerProvider(d,lambda:None,1234.)
            answer=provider.query('HULL',Pose(0,0,-1),1.,'fixture')
            self.assertEqual(answer['volume_m3'],40.)
            self.assertEqual(answer['cg_body_m'],[0.,0.,.5])
            self.assertEqual(answer['owner_record'],record)
            self.assertEqual(call.call_args.kwargs['deadline'],1234.)
            self.assertEqual(answer['i_transverse_m4'],160/3)
            self.assertEqual(section['convention'],'raw_u2_v2_uv')
            self.assertNotEqual(section['second_m4'][1],section['second_m4'][2])
            provider.finish()
        self.p.start()

    def test_review_opening_limit_never_requeues_post_limit_endpoints(self):
        opening=dict(name='port opening',point_body_m=[0.,2.,1.05],closing_status='open',limits_intact=True)
        r=w.calculate_gz_curve(study(openings=[opening]),heels_rad=[-.1,0,.1],
            controls={'max_points':100,'max_evaluations':400}).to_dict()
        branch=r['branches']['negative']; limit=branch['intact_limit']['heel_rad']
        ids=set(branch['point_identities'])
        self.assertTrue(all(p['heel_rad']>=limit for p in r['points'] if p['identity'] in ids))
        self.assertTrue(all(i['from_heel_rad']>=limit and i['to_heel_rad']>=limit for i in branch['intervals']))
        self.assertEqual(r['metrics']['downflooding_reason'],'engineering_angle_bracket')

    def test_review_negative_restoring_maximum_preserves_signed_area(self):
        r=w.calculate_gz_curve(study(),heels_rad=[-.1,0,.1],controls={'max_points':25}).to_dict()
        a=r['metrics']['branches']['negative']; b=r['metrics']['branches']['positive']
        self.assertEqual(a['restoring_direction'],-1)
        self.assertGreater(a['maximum_gz_estimate_m'],0.)
        self.assertAlmostEqual(a['maximum_gz_estimate_m'],b['maximum_gz_estimate_m'])
        self.assertLess(a['sampled_maximum_signed_raw_gz_m'],0.)
        self.assertLess(a['signed_area_estimate_mrad'],0.)

    def test_review_bad_owner_response_retained_and_capacity_tolerance(self):
        s=study(); original=AnalyticProvider.query
        def response(provider,name,pose,*args):
            answer=original(provider,name,pose,*args)
            answer['cg_body_m']=[0.,0.,100.]
            return answer
        with patch.object(AnalyticProvider,'query',response):
            r=w.solve_floating_equilibrium(s).to_dict()
        self.assertEqual(r['status'],'unresolved')
        self.assertEqual(r['failures'][0]['error']['code'],'ACCURACY_UNRESOLVED')
        self.assertIsNotNone(r['work']['queries'][0]['failure'])
        d=s.to_dict(); ex=w._Execution(w.EngineeringStudy.from_dict(d),{'controls':w.workflow_defaults()},None,None)
        def almost_full(*args):
            return dict(volume_m3=160.+5e-10,cg_body_m=[0.,0.,2.],assurance='analytic_fake')
        with patch.object(ex.provider,'query',almost_full):
            self.assertGreater(ex.query('HULL',Pose(),10.)['volume_m3'],160.)

    def test_review_global_integrity_abort_carries_quarantined_evidence(self):
        original=AnalyticProvider.query
        for code in (ErrorCode.INTEGRITY_ERROR,ErrorCode.SOURCE_STALE):
            def query(provider,name,pose,*args):
                if pose.heel_rad<-.04:
                    raise StabilityError(code,'runtime identity changed')
                return original(provider,name,pose,*args)
            with patch.object(AnalyticProvider,'query',query),self.assertRaises(StabilityError) as caught:
                w.calculate_gz_curve(study(),heels_rad=[-.05,0,.05])
            evidence=caught.exception.evidence.to_dict()
            self.assertTrue(evidence['assurance']['quarantined'])
            self.assertFalse(evidence['work']['resumable'])
            self.assertFalse(any(p['heel_rad']>0 for p in evidence['points']))

    def test_review_progress_failure_and_nonresumable_checkpoint(self):
        events=[]
        def broken(event):
            if event['phase']=='accepted_equilibrium':
                events.append(event)
                raise PermissionError('simulated Windows replace race')
        s=study(); final=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],progress=broken)
        self.assertEqual(final.to_dict()['failures'][0]['error']['code'],'IO_ERROR')
        self.assertTrue(final.to_dict()['work']['resumable'])
        checkpoint=w.EngineeringResult.from_dict(events[0]['result'])
        self.assertFalse(checkpoint.to_dict()['work']['resumable'])
        resumed=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],seed_result=checkpoint)
        self.assertEqual(resumed.to_dict()['failures'][0]['error']['code'],'CAPABILITY_UNSUPPORTED')

    def test_review_deadline_reserves_finalization_inside_same_cap(self):
        ex=w._Execution(study(),{'controls':w.workflow_defaults()},None,None)
        self.assertEqual(ex.finalization_reserve,2.)
        ex.start-=89.
        with self.assertRaises(StabilityError) as caught: ex.poll()
        self.assertEqual(caught.exception.code,ErrorCode.DEADLINE_EXCEEDED)

    def test_identity_is_cached_after_immutable_validation(self):
        from dataclasses import FrozenInstanceError
        s=study(); result=w.solve_floating_equilibrium(s)
        sid=s.identity; rid=result.identity
        with patch.object(w.EngineeringResult,'to_dict',side_effect=AssertionError('no repeated parse')), \
                patch.object(w.EngineeringStudy,'to_dict',side_effect=AssertionError('no repeated parse')):
            self.assertEqual(result.identity,rid)
            self.assertEqual(s.identity,sid)
        with self.assertRaises(FrozenInstanceError):
            result._identity='forged'

    def test_host_launch_anchor_charges_startup_and_validates_past_time(self):
        s=study(); anchor=time.monotonic()-4.
        r=w.solve_floating_equilibrium(s,controls={'max_wall_seconds':3.},execution_started_monotonic=anchor).to_dict()
        self.assertEqual(r['failures'][0]['error']['code'],'DEADLINE_EXCEEDED')
        self.assertGreaterEqual(r['work']['elapsed_wall_seconds'],4.)
        self.assertEqual(r['work']['attempted_owner_queries'],0)
        self.assertNotIn('execution_started_monotonic',r['request'])
        with self.assertRaises(StabilityError):
            w.solve_floating_equilibrium(s,execution_started_monotonic=time.monotonic()+10.)

    def test_missing_resume_marker_fails_closed(self):
        s=study(); original=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05]).to_dict()
        original['work'].pop('resumable'); legacy=w._result(original)
        refused=w.calculate_gz_curve(s,heels_rad=[-.05,0,.05],seed_result=legacy).to_dict()
        self.assertEqual(refused['failures'][0]['error']['code'],'CAPABILITY_UNSUPPORTED')
        self.assertEqual(refused['work']['attempted_owner_queries'],0)

    def test_invalid_cancel_contract_not_reclassified_as_owner_response(self):
        counter=[0]
        def cancel():
            counter[0]+=1
            return 'invalid' if counter[0]>=3 else False
        ex=w._Execution(study(),{'controls':w.workflow_defaults()},cancel,None)
        with self.assertRaises(StabilityError) as caught:
            ex.query('HULL',Pose(0.,0.,-1.),1.)
        self.assertEqual(caught.exception.code,ErrorCode.INPUT_INVALID)
        self.assertEqual(ex.queries[0]['failure']['code'],'INPUT_INVALID')

    def test_query_progress_io_failure_attached_to_pending_record(self):
        def broken(event): raise PermissionError('publication locked')
        r=w.solve_floating_equilibrium(study(),progress=broken).to_dict()
        # The first evaluation event can fail before a query; directly force the
        # geometry-query publication edge to verify its retained row as well.
        ex=w._Execution(study(),{'controls':w.workflow_defaults()},None,broken)
        with self.assertRaises(StabilityError): ex.query('HULL',Pose(),1.)
        self.assertEqual(ex.queries[0]['failure']['code'],'IO_ERROR')
        self.assertIsNotNone(ex.pending)

    def test_origin_roundoff_resolves_both_branches_under_unchanged_preview_budget(self):
        original=w._Execution.solve
        for sign in (-1,1):
            def solve(ex,q,axes,purpose):
                state=original(ex,q,axes,purpose)
                if purpose=='initial_equilibrium':state['gz_m']=sign*1.311261620553066e-16
                return state
            with self.subTest(sign=sign),patch.object(w._Execution,'solve',solve):
                d=w.calculate_gz_curve(study(),heels_rad=[-math.radians(2),0,math.radians(2)],
                    controls={'max_points':33,'max_evaluations':48}).to_dict()
                self.assertEqual(d['status'],'complete',d['failures'])
                self.assertEqual(len(d['points']),9)
                self.assertLessEqual(d['work']['evaluation_count'],48)
                self.assertEqual(d['equilibrium']['gz_m'],sign*1.311261620553066e-16)
                for name in ('negative','positive'):
                    self.assertEqual(d['branches'][name]['status'],'complete')
                    self.assertEqual(len(d['branches'][name]['intervals']),2)
                    self.assertIsNone(d['metrics']['branches'][name]['vanishing_angle_estimate_rad'])

    def test_nonzero_origin_roundoff_uses_retained_equilibrium_identity(self):
        angle=.01;normal=Pose(angle,0.,-1.).rotation[2];c=1/normal[2]
        sy=-normal[1]/normal[2]
        cb=[0.,sy*16/(12*c),(c*c+sy*sy*16/12)/(2*c)]
        s=study().to_dict();s['initial_pose']=Pose(angle,0.,-1.).to_dict()
        item=s['base_condition']['items'][0];item['mass_kg']=40000*c
        item['cg_body_m']=[v+.2*n for v,n in zip(cb,normal)]
        original=w._Execution.solve
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            if purpose=='initial_equilibrium':state['gz_m']=1e-16
            return state
        with patch.object(w._Execution,'solve',solve):
            d=w.calculate_gz_curve(w.EngineeringStudy.from_dict(s),heels_rad=[-.025,.045],
                controls={'max_points':33,'max_evaluations':48}).to_dict()
        self.assertEqual(d['status'],'complete',d['failures'])
        self.assertEqual(d['equilibrium']['heel_rad'],angle)
        self.assertEqual(len(d['points']),9)

    def test_origin_roundoff_resume_preserves_semantics_and_spent_work(self):
        original=w._Execution.solve;cancelled=[False]
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            if purpose=='initial_equilibrium':state['gz_m']=1e-16
            return state
        def progress(event):
            if event['phase']=='accepted_point':cancelled[0]=True
        s=study();options=dict(heels_rad=[-.03,0,.03],controls={'max_points':33,'max_evaluations':48})
        with patch.object(w._Execution,'solve',solve):
            prefix=w.calculate_gz_curve(s,progress=progress,cancellation_check=lambda:cancelled[0],**options)
            self.assertEqual(prefix.to_dict()['status'],'cancelled')
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'prefix.json';w.save_stability_study(s,path,result=prefix)
                reopened,seed=w.load_stability_study(path)
            d=w.calculate_gz_curve(reopened,seed_result=seed,**options).to_dict()
        self.assertEqual(d['status'],'complete',d['failures'])
        self.assertGreaterEqual(d['work']['evaluation_count'],prefix.to_dict()['work']['evaluation_count'])
        self.assertEqual(d['equilibrium'],prefix.to_dict()['equilibrium'])

    def test_distinct_midpoint_crossing_is_not_hidden_by_known_origin(self):
        original=w._Execution.solve
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            state['gz_m']=1e-16 if purpose=='initial_equilibrium' else q[1]*(.06-q[1])
            return state
        with patch.object(w._Execution,'solve',solve):
            d=w.calculate_gz_curve(study(),heels_rad=[0,.1],
                controls={'max_points':200,'max_evaluations':1000}).to_dict()
        metric=d['metrics']['branches']['positive']
        self.assertEqual(d['branches']['positive']['status'],'complete')
        self.assertAlmostEqual(metric['vanishing_angle_estimate_rad'],.06,delta=math.radians(.1))
        self.assertGreater(len(d['branches']['positive']['intervals']),1)

    def test_fixed_trim_origin_is_not_automatically_an_accepted_heel_root(self):
        original=w._Execution.solve
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            if purpose!='initial_equilibrium':state['gz_m']=.02-q[1]
            return state
        with patch.object(w._Execution,'solve',solve):
            d=w.calculate_gz_curve(study(),mode='fixed_trim',fixed_trim_rad=.025,heels_rad=[0,.08],
                controls={'max_points':100,'max_evaluations':400}).to_dict()
        origin=next(p for p in d['points'] if p['branch']=='equilibrium')
        self.assertFalse(w._accepted_root(origin,d['equilibrium']))
        self.assertNotEqual(origin['gz_m'],d['equilibrium']['gz_m'])
        self.assertAlmostEqual(d['metrics']['branches']['positive']['vanishing_angle_estimate_rad'],.02,delta=math.radians(.1))

    def test_distinct_crossings_before_old_midpoint_remain_visible_on_both_sides(self):
        original=w._Execution.solve
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            h=q[1];direction=-1 if h<0 else 1
            state['gz_m']=1e-16 if purpose=='initial_equilibrium' else direction*.1*abs(h)*(.02-abs(h))
            return state
        with patch.object(w._Execution,'solve',solve):
            d=w.calculate_gz_curve(study(),heels_rad=[-.1,0,.1],
                controls={'max_points':300,'max_evaluations':1000}).to_dict()
        for name,direction in (('negative',-1),('positive',1)):
            metric=d['metrics']['branches'][name]
            self.assertEqual(d['branches'][name]['status'],'complete')
            self.assertAlmostEqual(metric['vanishing_angle_estimate_rad'],direction*.02,delta=math.radians(.1))
            probe=direction*d['request']['controls']['angle_tolerance_rad']
            self.assertTrue(any(p['heel_rad']==probe for p in d['points']))

    def test_immersed_origin_probe_trims_both_mirrored_intact_domains(self):
        original=w._Execution.solve;tol=w.workflow_defaults()['angle_tolerance_rad']
        opening=dict(name='near-root event',point_body_m=[0.,2.,1.05],closing_status='open',limits_intact=True)
        for direction,name in ((-1,'negative'),(1,'positive')):
            def solve(ex,q,axes,purpose):
                state=original(ex,q,axes,purpose)
                for item in state['openings']:
                    item['height_above_water_m']=.75*tol-direction*q[1]
                    item['immersed']=item['height_above_water_m']<=0
                return state
            with self.subTest(direction=direction),patch.object(w._Execution,'solve',solve):
                d=w.calculate_gz_curve(study(openings=[opening]),heels_rad=[-.1,0,.1],
                    controls={'max_points':100,'max_evaluations':400}).to_dict()
                branch=d['branches'][name];limit=branch['intact_limit']['heel_rad']
                self.assertEqual(branch['status'],'intact_limit')
                self.assertLessEqual(abs(limit),tol)
                self.assertLessEqual(branch['intact_limit']['angle_uncertainty_rad'],tol)
                indexed={p['identity']:p for p in d['points']}
                for identity in branch['point_identities']:self.assertLessEqual(abs(indexed[identity]['heel_rad']),abs(limit))
                for interval in branch['intervals']:
                    self.assertLessEqual(max(abs(interval['from_heel_rad']),abs(interval['to_heel_rad'])),abs(limit))

    def test_origin_probe_cancellation_resume_and_point_limit_keep_accounting(self):
        cancelled=[False]
        def progress(event):
            if event['phase']=='accepted_origin_probe':cancelled[0]=True
        s=study();options=dict(heels_rad=[-.03,0,.03],controls={'max_points':33,'max_evaluations':48})
        prefix=w.calculate_gz_curve(s,progress=progress,cancellation_check=lambda:cancelled[0],**options)
        self.assertEqual(prefix.to_dict()['status'],'cancelled')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'probe.json';w.save_stability_study(s,path,result=prefix)
            reopened,seed=w.load_stability_study(path)
        d=w.calculate_gz_curve(reopened,seed_result=seed,**options).to_dict()
        self.assertEqual(d['status'],'complete',d['failures'])
        self.assertGreaterEqual(d['work']['attempted_owner_queries'],prefix.to_dict()['work']['attempted_owner_queries'])
        limited=w.calculate_gz_curve(s,heels_rad=[-.03,0,.03],controls={'max_points':4}).to_dict()
        self.assertEqual(limited['status'],'partial')
        self.assertEqual(limited['work']['accepted_point_count'],4)
        self.assertTrue(any(i['status']=='unresolved_point_budget' for b in limited['branches'].values() for i in b['intervals']))

    def test_final_opening_cut_labels_borrowed_parent_estimate_at_tolerance(self):
        opening=dict(name='event fixture',point_body_m=[0.,2.,1.05],closing_status='open',limits_intact=True)
        original=w._Execution.solve
        def solve(ex,q,axes,purpose):
            state=original(ex,q,axes,purpose)
            # Prescribed event threshold forces a parent interval width in
            # (angle_tolerance,2*angle_tolerance] and an immersed midpoint.
            for item in state['openings']:
                item['immersed']=q[1]<-.098
                item['height_above_water_m']=q[1]+.098
            return state
        with patch.object(w._Execution,'solve',solve):
            r=w.calculate_gz_curve(study(openings=[opening]),heels_rad=[-.1,0,.1],
                controls={'max_points':100,'max_evaluations':400}).to_dict()
        branch=r['branches']['negative']; tol=r['request']['controls']['angle_tolerance_rad']
        borrowed=[i for i in branch['intervals'] if i.get('estimate_source')=='parent_interval']
        self.assertTrue(borrowed)
        self.assertTrue(any(tol/2<abs(i['to_heel_rad']-i['from_heel_rad'])<=tol for i in borrowed))


if __name__=='__main__': unittest.main()
