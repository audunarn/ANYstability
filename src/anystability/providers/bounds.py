"""Outward binary64 interval arithmetic, not a certificate for input geometry.

Fractions are used only for small consumer-side moment calculations. The hull
query path remains with ANYgeometry. An estimate stays an estimate even when
arithmetic on its supplied interval is enclosed exactly.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
from ..errors import ErrorCode, StabilityError
from ..validation import invalid, real
from .protocol import Quantity


def _outward(value: Fraction, upper: bool) -> float:
    try:
        out = float(value)
    except OverflowError as exc:
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "interval overflow") from exc
    if not math.isfinite(out):
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "interval overflow")
    if (Fraction(out) < value if upper else Fraction(out) > value):
        out = math.nextafter(out, math.inf if upper else -math.inf)
    if not math.isfinite(out):
        raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "finite enclosure unavailable")
    return out


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float

    def __post_init__(self):
        for name in ("lower", "upper"):
            object.__setattr__(self, name, real(getattr(self, name), name))
        if self.lower > self.upper:
            invalid("interval endpoints are reversed")

    @classmethod
    def enclosing(cls, lower: Fraction, upper: Fraction):
        return cls(_outward(lower, False), _outward(upper, True))

    @classmethod
    def of(cls, q: Quantity):
        if not isinstance(q, Quantity):
            invalid("interval conversion requires a Quantity")
        return cls.enclosing(Fraction(q.value)-Fraction(q.error),
                             Fraction(q.value)+Fraction(q.error))

    def __add__(self, other):
        return Interval.enclosing(Fraction(self.lower)+Fraction(other.lower),
                                  Fraction(self.upper)+Fraction(other.upper))

    def __sub__(self, other):
        return Interval.enclosing(Fraction(self.lower)-Fraction(other.upper),
                                  Fraction(self.upper)-Fraction(other.lower))

    def __mul__(self, other):
        values = [Fraction(a)*Fraction(b) for a in (self.lower, self.upper)
                  for b in (other.lower, other.upper)]
        return Interval.enclosing(min(values), max(values))

    def __truediv__(self, other):
        if other.lower <= 0 <= other.upper:
            raise StabilityError(ErrorCode.ACCURACY_UNRESOLVED, "divisor interval includes zero")
        values = [Fraction(a)/Fraction(b) for a in (self.lower, self.upper)
                  for b in (other.lower, other.upper)]
        return Interval.enclosing(min(values), max(values))

    def square(self):
        values = [Fraction(self.lower)**2, Fraction(self.upper)**2]
        return Interval.enclosing(Fraction(0) if self.lower <= 0 <= self.upper else min(values),
                                  max(values))

    def to_dict(self):
        return dict(lower=self.lower, upper=self.upper)
