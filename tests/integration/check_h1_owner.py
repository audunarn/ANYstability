"""Real installed-owner checks. Run explicitly; not included in no-owner unit CI.

Independent B1 oracle: x^2/a(z)^2 + y^2/b(z)^2 = 1, with
 a=5.4+0.15*z, b=6+0.375*z. The owner fixture occupies
 x in [1.5,3.5], y in [0,y(x,z)], z in [0.5,3].
No owner section/integration routines are used for the reference integrals.
"""
from pathlib import Path
import json
import math
import os
import statistics
import subprocess
import sys
import time

import numpy as np
from anygeometry import GeometryModel, Plane
from anygeometry.entities import OrientedEdge
from anystability.conventions import Pose
from anystability.errors import ErrorCode, StabilityError
from anystability.providers.anygeometry_h1 import H1DevelopmentProvider, H1Query, verify_installed_owner
from anystability.providers.protocol import HalfSpace
from anystability.providers.handoff import require_production_provider
from anystability.validation import canonical_bytes


def close(actual, expected, atol=1e-9, rtol=1e-9):
    assert np.allclose(actual, expected, atol=atol, rtol=rtol), (actual, expected)


def box():
    dims=np.array([2.,3.,4.]); shift=np.array([-1.,-1.5,0.])
    model=GeometryModel(); points={}
    for i in (0,1):
        for j in (0,1):
            for k in (0,1):
                points[i,j,k]=model.add_point(*(dims*np.array([i,j,k])+shift))
    quads=(((0,0,0),(0,1,0),(1,1,0),(1,0,0)),((0,0,1),(1,0,1),(1,1,1),(0,1,1)),
           ((0,0,0),(0,0,1),(0,1,1),(0,1,0)),((1,0,0),(1,1,0),(1,1,1),(1,0,1)),
           ((0,0,0),(1,0,0),(1,0,1),(0,0,1)),((0,1,0),(0,1,1),(1,1,1),(1,1,0)))
    edges={}; faces=[]
    for quad in quads:
        loop=[]
        for a,b in zip(quad,quad[1:]+quad[:1]):
            key=frozenset((a,b))
            if key not in edges:
                edges[key]=model.add_line(points[a],points[b])
            edge=edges[key]
            loop.append(OrientedEdge(edge,model.edges[edge].start==points[a]))
        p=np.array(quad,dtype=float)*dims+shift
        faces.append(model.add_face_from_loop(loop,surface=Plane(p[0],p[1]-p[0],p[3]-p[0])))
    return model,faces


def width(x,z):
    return (6.+.375*z)*np.sqrt(1.-(x/(5.4+.15*z))**2)


def reference_b1(draft,order=48):
    nodes,weights=np.polynomial.legendre.leggauss(order)
    x=2.5+nodes; wx=weights
    z=.5+(draft-.5)*.5*(nodes+1.); wz=weights*(draft-.5)*.5
    y=width(x[:,None],z[None,:]); w=wx[:,None]*wz[None,:]
    volume=float(np.sum(w*y))
    first=np.array([np.sum(w*x[:,None]*y),np.sum(w*y*y/2),np.sum(w*z[None,:]*y)])
    yw=width(x,draft); area=float(wx@yw)
    cf=np.array([float(wx@(x*yw))/area,float(wx@(yw*yw/2))/area,draft])
    moments=dict(about_xi=float(wx@(yw**3/3))-area*cf[1]**2,
                 about_eta=float(wx@(x*x*yw))-area*cf[0]**2,
                 product_xi_eta=float(wx@(x*yw*yw/2))-area*cf[0]*cf[1])
    return dict(volume=volume,cb=first/volume,area=area,cf=cf,moments=moments)


def panel_b1(draft,n):
    """Independent faceted CLOSED cut hull; tests only, never a provider fallback."""
    x=np.linspace(1.5,3.5,n+1);z=np.linspace(.5,draft,n+1);triangles=[]
    def quad(vertices,axis,sign):
        a,b,c,d=np.asarray(vertices,dtype=float)
        for tri in ((a,b,c),(a,c,d)):
            u,v,w=tri
            if np.cross(v-u,w-u)[axis]*sign<0:
                tri=(u,w,v)
            triangles.append(tri)
    for a,b in zip(x[:-1],x[1:]):
        for c,d in zip(z[:-1],z[1:]):
            quad(((a,width(a,c),c),(b,width(b,c),c),(b,width(b,d),d),(a,width(a,d),d)),1,1)
        for h,s in ((.5,-1),(draft,1)):
            quad(((a,0,h),(b,0,h),(b,width(b,h),h),(a,width(a,h),h)),2,s)
    for c,d in zip(z[:-1],z[1:]):
        for a,s in ((1.5,-1),(3.5,1)):
            quad(((a,0,c),(a,width(a,c),c),(a,width(a,d),d),(a,0,d)),0,s)
    quad(((1.5,0,.5),(3.5,0,.5),(3.5,0,draft),(1.5,0,draft)),1,-1)
    tri=np.asarray(triangles)
    signed=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2]))/6
    volume=float(signed.sum()); cb=(signed[:,None]*tri.sum(axis=1)/4).sum(axis=0)/volume
    return volume,cb,len(triangles)


def main():
    receipt=verify_installed_owner(allow_development=True)
    cases=[];timings=[]
    model,faces=box();provider=H1DevelopmentProvider(model,faces,allow_development=True)
    # Combined finite heel/trim: h=T+a*x+b*y. Exact integrals over a centred rectangle.
    for heel,trim in ((0.,0.),(.2,0.),(-.3,.1)):
        normal=Pose(heel,trim).rotation[2];nz=normal[2];T=1.5
        result=provider.evaluate(H1Query(HalfSpace(normal,T*nz)))
        v=result['values']; a,b=-normal[0]/nz,-normal[1]/nz
        cb=(a*4/(12*T),b*9/(12*T),T/2+(a*a*4+b*b*9)/(24*T))
        close(v['volume_m3'],9.);close(v['center_of_buoyancy_body_m'],cb)
        close(v['waterplane_area_m2'],6/nz);close(v['center_of_flotation_body_m'],(0,0,T))
        axes=np.asarray(v['frame']['axes_rows_body']); tangents=np.array([[1,0,a],[0,1,b]])
        uv=tangents@axes[:2].T
        C=(6/nz)*(np.outer(uv[0],uv[0])*4/12+np.outer(uv[1],uv[1])*9/12)
        for key,expected in (('about_xi',C[1,1]),('about_eta',C[0,0]),('product_xi_eta',C[0,1])):
            close(v['centroidal_waterplane_moments_m4'][key],expected)
        assert v['quantity_error_bounds'] is None and not result['production_qualified']
        cases.append(dict(case='box_finite_pose',heel=heel,trim=trim,status='numeric_comparison_pass'))
    for d,expected in ((-1.,0.),(5.,24.)):
        try:
            r=provider.evaluate(H1Query(HalfSpace((0,0,1),d)))
            close(r['values']['volume_m3'],expected)
            assert r['values']['geometric_BM'] is None
            cases.append(dict(case='box_limit',offset=d,status='numeric_comparison_pass'))
        except StabilityError as exc:
            assert exc.code == ErrorCode.ACCURACY_UNRESOLVED
            cases.append(dict(case='box_limit',offset=d,status='unresolved_not_a_numeric_pass',error=exc.to_dict()))
    # A direction parallel to the chosen longitudinal axis must remain an owner refusal.
    try:
        provider.evaluate(H1Query(HalfSpace((1,0,0),0)))
        raise AssertionError('longitudinal degeneracy silently accepted')
    except StabilityError as exc:
        assert exc.code==ErrorCode.QUERY_DEGENERATE and exc.__cause__ is not None
        cases.append(dict(case='parallel_longitudinal',status='typed_refusal_pass',error=exc.to_dict()))
    limited=H1DevelopmentProvider(model,faces,allow_development=True,max_queries=1)
    limited.evaluate(H1Query(HalfSpace((0,0,1),1.5)))
    try:
        limited.evaluate(H1Query(HalfSpace((0,0,1),1.5)))
        raise AssertionError('budget ignored')
    except StabilityError as exc:
        assert exc.code==ErrorCode.WORK_BUDGET_EXCEEDED
    # A detached snapshot ignores subsequent caller edits; private prepared edits are refused.
    model.add_point(100,100,100)
    provider.evaluate(H1Query(HalfSpace((0,0,1),1.5)))
    provider._model.add_point(100,100,100)
    try:
        provider.evaluate(H1Query(HalfSpace((0,0,1),1.5)))
        raise AssertionError('stale prepared state accepted')
    except StabilityError as exc:
        assert exc.code==ErrorCode.SOURCE_STALE
    start=time.perf_counter(); b1=H1DevelopmentProvider.b1(allow_development=True)
    preparation=time.perf_counter()-start
    last=None
    for draft in (1.,1.75,2.5):
        print("H1_CASE B1", draft, flush=True)
        r=b1.evaluate(H1Query(HalfSpace((0,0,1),draft)));v=r['values'];ref=reference_b1(draft)
        close(v['volume_m3'],ref['volume']);close(v['center_of_buoyancy_body_m'],ref['cb'])
        close(v['waterplane_area_m2'],ref['area']);close(v['center_of_flotation_body_m'],ref['cf'])
        for key,value in ref['moments'].items():
            close(v['centroidal_waterplane_moments_m4'][key],value,atol=1e-8,rtol=1e-8)
        timings.append(r['diagnostics']['owner_call_seconds'])
        cases.append(dict(case='b1_half_hull',draft=draft,status='numeric_comparison_pass',
                          volume_m3=v['volume_m3'],cb=v['center_of_buoyancy_body_m'],
                          area_m2=v['waterplane_area_m2'],indicator=v['order_doubling_indicator']))
        if draft==1.75:last=r
    ref=reference_b1(1.75);panels=[]
    for level in (4,8,16,32):
        volume,cb,count=panel_b1(1.75,level)
        panels.append(dict(subdivisions=level,triangles=count,volume_m3=volume,
                           relative_volume_error=abs(volume-ref['volume'])/ref['volume'],
                           cb_error_m=float(np.max(np.abs(cb-ref['cb'])))))
    assert panels[-1]['relative_volume_error']<1e-4
    for a,b in zip(panels,panels[1:]):
        assert b['relative_volume_error']<a['relative_volume_error']/3
        assert b['cb_error_m']<a['cb_error_m']
    # Actual owner model codec round trip, not just matching a claimed checksum.
    reopened=H1DevelopmentProvider.from_snapshot(b1.snapshot_bytes(),allow_development=True)
    after=reopened.evaluate(H1Query(HalfSpace((0,0,1),1.75)))
    assert after['binding']==last['binding']
    for key in ('volume_m3','waterplane_area_m2','center_of_buoyancy_body_m'):
        close(after['values'][key],last['values'][key],atol=1e-12,rtol=1e-12)
    # Prescribed oblique B1 query and dV/dd=A in that same fixed unit normal.
    normal=Pose(.05,.03).rotation[2];d=1.75; h=1e-3
    print("H1_CASE B1 oblique", flush=True)
    middle=reopened.evaluate(H1Query(HalfSpace(normal,d)))
    plus=reopened.evaluate(H1Query(HalfSpace(normal,d+h)))
    minus=reopened.evaluate(H1Query(HalfSpace(normal,d-h)))
    derivative=(plus['values']['volume_m3']-minus['values']['volume_m3'])/(2*h)
    close(derivative,middle['values']['waterplane_area_m2'],atol=1e-5,rtol=1e-5)
    cases.append(dict(case='b1_oblique_volume_derivative',status='numeric_comparison_pass',
                      derivative_m2=derivative,area_m2=middle['values']['waterplane_area_m2']))
    try:
        require_production_provider()
        raise AssertionError('quadrature promoted to certified production')
    except StabilityError as exc:
        assert exc.code==ErrorCode.PROVIDER_UNAVAILABLE
    folder=Path(os.environ.get('H1_EVIDENCE',str(Path.cwd()/'h1-evidence')));folder.mkdir(parents=True,exist_ok=True)
    snapshot=folder/'b1_snapshot.json';snapshot.write_bytes(b1.snapshot_bytes())
    cli=subprocess.run([sys.executable,'-I','-m','anystability','h1-query','--snapshot',str(snapshot),
                        '--draft-m','1.75','--allow-development','--wall-seconds','120'],capture_output=True,timeout=140)
    assert cli.returncode==0,cli.stderr.decode()
    close(json.loads(cli.stdout)['values']['volume_m3'],ref['volume'])
    evidence=dict(status='development_checks_passed',scope='B1 half-hull geometry, not a vessel stability qualification',
        owner=receipt,cases=cases,panel_refinement=panels,cli_subprocess='pass',
        snapshot_reproduction='pass',certified_H1_admission=False,
        timing=dict(preparation_seconds=preparation,owner_query_seconds=timings,
            median_seconds=statistics.median(timings),P0='pilot_measured',P1_1000_planes='not_executed'))
    (folder/'h1_evidence.json').write_bytes(canonical_bytes(evidence))
    (folder/'b1_query.json').write_bytes(canonical_bytes(last))
    print('H1_INTEGRATION_EVIDENCE '+json.dumps(evidence),flush=True)


if __name__=='__main__':
    main()
