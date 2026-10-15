"""Derived geometric properties; no geometry integration, GZ or rule assessment."""
from .providers.bounds import Interval
from .providers.integrals import IntegralSample
from .validation import invalid


def integral_properties(sample: IntegralSample) -> dict:
    """Bound arithmetic on supplied intervals, without upgrading their assurance.

    In-plane covariance integrals are not moments about identically named axes:
    the second moment ABOUT u is integral (v-v_c)^2, and vice versa.
    Frame-coordinate uncertainty is not enclosed by these scalar operations.
    """
    if not isinstance(sample, IntegralSample):
        invalid("properties require a typed integral sample")
    volume = Interval.of(sample.volume_m3)
    cb = None if volume.lower <= 0 else [
        (Interval.of(q)/volume).to_dict() for q in sample.first_moments_m4]
    w = sample.waterplane
    area = Interval.of(w.area_m2)
    centroid, central, bm = None, None, None
    if area.lower > 0:
        u, v = (Interval.of(q) for q in w.first_m3)
        uu, vv, uv = (Interval.of(q) for q in w.second_m4)
        centroid = [(u/area).to_dict(), (v/area).to_dict()]
        cuu, cvv, cuv = uu-u.square()/area, vv-v.square()/area, uv-u*v/area
        central = dict(uu=cuu.to_dict(), vv=cvv.to_dict(), uv=cuv.to_dict())
        if volume.lower > 0:
            bm = dict(about_u=(cvv/volume).to_dict(), about_v=(cuu/volume).to_dict())
    return dict(version="anystability-integral-properties-v1",
                input=sample.to_dict(), volume_m3=volume.to_dict(),
                center_of_buoyancy_body_m=cb,
                waterplane_centroid_uv_m=centroid, waterplane_frame=w.frame.to_dict(),
                waterplane_centroidal_m4=central, geometric_BM_m=bm,
                waterplane_status=("no_section" if w.components == 0 else
                                   "area_division_unresolved" if centroid is None else "available"),
                assurance=dict(input_geometry=sample.binding.source.geometry_assurance,
                    arithmetic="outward_enclosure_of_supplied_quantity_intervals",
                    coordinate_mapping="declared_frame_not_an_interval_pose_map",
                    owner_certificate="not_verified_by_postprocessing",
                    physical_model="not_qualified", production_qualified=False))
