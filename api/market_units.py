"""Canonical, dimension-safe market-product quantity normalization."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ProductUnit = Literal["mg", "g", "kg", "oz", "lb", "mL", "L", "fl oz", "gal", "count"]
UnitDimension = Literal["weight", "volume", "count"]
NormalizedUnit = Literal["mg", "mL", "count"]


@dataclass(frozen=True)
class NormalizedQuantity:
    value: float
    unit: NormalizedUnit
    dimension: UnitDimension


# Factors use mg for weight and mL for volume. These are the internal comparison
# bases only: callers retain the seller-entered quantity and display unit.
_UNIT_SPECS: dict[str, tuple[UnitDimension, NormalizedUnit, Decimal]] = {
    "mg": ("weight", "mg", Decimal("1")),
    "g": ("weight", "mg", Decimal("1000")),
    "kg": ("weight", "mg", Decimal("1000000")),
    "oz": ("weight", "mg", Decimal("28349.523125")),
    "lb": ("weight", "mg", Decimal("453592.37")),
    "mL": ("volume", "mL", Decimal("1")),
    "L": ("volume", "mL", Decimal("1000")),
    "fl oz": ("volume", "mL", Decimal("29.5735295625")),
    "gal": ("volume", "mL", Decimal("3785.411784")),
    "count": ("count", "count", Decimal("1")),
}


def normalize_quantity(quantity: float | None, unit: str | None) -> NormalizedQuantity | None:
    """Convert a complete declared measurement to its dimension's base unit."""
    if quantity is None and unit is None:
        return None
    if quantity is None or unit is None:
        raise ValueError("quantity and unit must be provided together")
    try:
        dimension, normalized_unit, factor = _UNIT_SPECS[unit]
    except KeyError as error:
        raise ValueError("unit is not supported") from error
    return NormalizedQuantity(
        value=float(Decimal(str(quantity)) * factor),
        unit=normalized_unit,
        dimension=dimension,
    )


def units_are_compatible(first: str | None, second: str | None) -> bool:
    """Return true only when both units represent the same physical dimension."""
    if first is None or second is None:
        return False
    first_normalized = normalize_quantity(1, first)
    second_normalized = normalize_quantity(1, second)
    return (
        first_normalized is not None
        and second_normalized is not None
        and first_normalized.dimension == second_normalized.dimension
    )
