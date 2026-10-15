"""Immutable SI input records; storage codecs return copies, not mutable aliases."""
from dataclasses import dataclass
import math
from .validation import (canonical_bytes, content_hash, decode_json, exact, integer,
                         invalid, real, sequence, text, vector)


@dataclass(frozen=True)
class MassItem:
    item_id: str
    mass_kg: float
    cg_body_m: tuple[float, float, float]
    source: str
    covers: tuple[str, ...]

    def __post_init__(self):
        text(self.item_id, "item_id")
        text(self.source, "mass source")
        object.__setattr__(self, "mass_kg", real(self.mass_kg, "mass_kg", positive=True))
        object.__setattr__(self, "cg_body_m", vector(self.cg_body_m, "cg_body_m"))
        covers = tuple(text(v, "covered component") for v in sequence(self.covers, "covers"))
        if not covers or len(set(covers)) != len(covers):
            invalid("each mass item must cover unique, explicitly named physical components")
        object.__setattr__(self, "covers", tuple(sorted(covers)))

    def to_dict(self):
        return dict(item_id=self.item_id, mass_kg=self.mass_kg,
                    cg_body_m=list(self.cg_body_m), source=self.source, covers=list(self.covers))

    @classmethod
    def from_dict(cls, data):
        return cls(**exact(data, {"item_id", "mass_kg", "cg_body_m", "source", "covers"}, "mass item"))


@dataclass(frozen=True)
class LoadingCondition:
    condition_id: str
    name: str
    items: tuple[MassItem, ...]
    water_density_kg_m3: float = 1025.0
    gravity_m_s2: float = 9.80665

    def __post_init__(self):
        text(self.condition_id, "condition_id")
        text(self.name, "condition name")
        items = sequence(self.items, "mass items")
        if not items or any(not isinstance(v, MassItem) for v in items):
            invalid("a loading condition requires validated mass items")
        ids, covered = set(), set()
        for item in items:
            if item.item_id in ids:
                invalid(f"duplicate mass item: {item.item_id}")
            overlap = covered.intersection(item.covers)
            if overlap:
                invalid(f"double-counted physical mass components: {sorted(overlap)}")
            ids.add(item.item_id)
            covered.update(item.covers)
        object.__setattr__(self, "items", tuple(sorted(items, key=lambda v: v.item_id)))
        for name in ("water_density_kg_m3", "gravity_m_s2"):
            object.__setattr__(self, name, real(getattr(self, name), name, positive=True))

    def to_dict(self):
        return dict(condition_id=self.condition_id, name=self.name,
                    items=[item.to_dict() for item in self.items],
                    water_density_kg_m3=self.water_density_kg_m3, gravity_m_s2=self.gravity_m_s2)

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"condition_id", "name", "items", "water_density_kg_m3", "gravity_m_s2"}, "condition")
        d["items"] = tuple(MassItem.from_dict(v) for v in sequence(d["items"], "mass items"))
        return cls(**d)


@dataclass(frozen=True)
class GeometrySource:
    """Opaque, canonical, immutable owner input. Only a provider interprets it."""
    provider_id: str
    definition_json: str

    def __post_init__(self):
        text(self.provider_id, "provider_id")
        if not isinstance(self.definition_json, str):
            invalid("geometry definition must be JSON text")
        data = decode_json(self.definition_json.encode("utf-8"))
        if not isinstance(data, dict):
            invalid("geometry definition must be an object")
        object.__setattr__(self, "definition_json", canonical_bytes(data).decode("utf-8"))

    def to_dict(self):
        return dict(provider_id=self.provider_id, definition=decode_json(self.definition_json.encode()))

    @property
    def identity(self):
        return content_hash(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"provider_id", "definition"}, "geometry source")
        return cls(d["provider_id"], canonical_bytes(d["definition"]).decode())


@dataclass(frozen=True)
class VesselDefinition:
    vessel_id: str
    name: str
    geometry: GeometrySource

    def __post_init__(self):
        text(self.vessel_id, "vessel_id")
        text(self.name, "vessel name")
        if not isinstance(self.geometry, GeometrySource):
            invalid("geometry must be a GeometrySource")

    def to_dict(self):
        return dict(vessel_id=self.vessel_id, name=self.name, geometry=self.geometry.to_dict())

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"vessel_id", "name", "geometry"}, "vessel")
        d["geometry"] = GeometrySource.from_dict(d["geometry"])
        return cls(**d)


@dataclass(frozen=True)
class AnalysisSettings:
    force_relative_tolerance: float = 1e-8
    draft_tolerance_m: float = 1e-6
    max_queries: int = 128

    def __post_init__(self):
        for name in ("force_relative_tolerance", "draft_tolerance_m"):
            object.__setattr__(self, name, real(getattr(self, name), name, positive=True))
        if self.force_relative_tolerance >= 1:
            invalid("force_relative_tolerance must be smaller than one")
        integer(self.max_queries, "max_queries", 1, 100000)

    def to_dict(self):
        return dict(force_relative_tolerance=self.force_relative_tolerance,
                    draft_tolerance_m=self.draft_tolerance_m, max_queries=self.max_queries)

    @classmethod
    def from_dict(cls, data):
        return cls(**exact(data, {"force_relative_tolerance", "draft_tolerance_m", "max_queries"}, "settings"))


@dataclass(frozen=True)
class Project:
    vessel: VesselDefinition
    condition: LoadingCondition
    settings: AnalysisSettings = AnalysisSettings()

    def __post_init__(self):
        if not isinstance(self.vessel, VesselDefinition) or not isinstance(self.condition, LoadingCondition):
            invalid("project requires validated vessel and condition records")
        if not isinstance(self.settings, AnalysisSettings):
            invalid("project requires validated analysis settings")

    def to_dict(self):
        return dict(schema_version=1, vessel=self.vessel.to_dict(),
                    condition=self.condition.to_dict(), settings=self.settings.to_dict())

    @property
    def identity(self):
        return content_hash(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        d = exact(data, {"schema_version", "vessel", "condition", "settings"}, "project")
        integer(d["schema_version"], "schema_version", 1, 1)
        return cls(VesselDefinition.from_dict(d["vessel"]), LoadingCondition.from_dict(d["condition"]),
                   AnalysisSettings.from_dict(d["settings"]))
