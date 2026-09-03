"""
Highway corridor configuration.

This module intentionally contains no Google Earth Engine calls so that it
can be imported anywhere (including before ee.Initialize() has run) without
side effects. Geometry construction from these definitions happens in
gee_utils.py.

Coordinates are approximate prototype route points (WGS84, [lon, lat]) traced
along the general path of each highway across the Dubai-Sharjah border. They
are sufficient for a corridor-level SAR proxy analysis but are NOT surveyed
centerlines and should be refined with authoritative GIS data (e.g. RTA/DM
road network layers) before any operational use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

Coordinate = Tuple[float, float]  # (longitude, latitude)


@dataclass(frozen=True)
class Corridor:
    """Definition of a single highway corridor used for SAR proxy analysis."""

    road_code: str
    name: str
    coordinates: List[Coordinate]
    buffer_meters: int = 100
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "road_code": self.road_code,
            "name": self.name,
            "coordinates": self.coordinates,
            "buffer_meters": self.buffer_meters,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Corridor registry
#
# To add a new corridor: append a new Corridor(...) entry below and register
# it in CORRIDORS. No other file needs to change for it to appear throughout
# the app (sidebar selector, comparison mode, map layers, etc.).
# ---------------------------------------------------------------------------

_E311 = Corridor(
    road_code="E311",
    name="Sheikh Mohammed Bin Zayed Road / E311",
    coordinates=[
        (55.3720, 25.2075),  # Dubai side, near Al Twar / Manama St interchange
        (55.4020, 25.2500),  # Dubai-Sharjah border area
        (55.4330, 25.2950),  # Sharjah Airport interchange vicinity
        (55.4600, 25.3400),  # Sharjah, towards Al Dhaid Rd junction
    ],
    buffer_meters=100,
    description=(
        "Major inland freeway connecting Dubai and Sharjah, continuing "
        "further to the Northern Emirates. Carries substantial daily "
        "commuter and freight traffic between the two emirates."
    ),
)

_E11 = Corridor(
    road_code="E11",
    name="Al Ittihad Road / E11",
    coordinates=[
        (55.3402, 25.2965),  # Dubai side, near Al Mamzar
        (55.3550, 25.3150),  # Dubai-Sharjah border crossing
        (55.3720, 25.3400),  # Sharjah, near Buhaira Corniche approach
        (55.3900, 25.3650),  # Sharjah, towards Al Ittihad corridor north
    ],
    buffer_meters=100,
    description=(
        "Coastal arterial route (part of the wider E11 Sheikh Zayed Road "
        "corridor) linking Deira, Dubai with central Sharjah. One of the "
        "most heavily congested cross-emirate commuter routes in the UAE."
    ),
)

_E611 = Corridor(
    road_code="E611",
    name="Emirates Road / E611",
    coordinates=[
        (55.4550, 25.1450),  # Dubai side, near Dubai Silicon Oasis / Academic City
        (55.4780, 25.2050),  # Dubai-Sharjah border area
        (55.5000, 25.2700),  # Sharjah, University City vicinity
        (55.5150, 25.3300),  # Sharjah, towards Al Dhaid Rd interchange
    ],
    buffer_meters=100,
    description=(
        "Outer beltway (part of the wider Emirates Road ring connecting "
        "Ras Al Khaimah through the Northern Emirates to Abu Dhabi) linking "
        "eastern Dubai with eastern Sharjah. Rounds out cross-emirate "
        "coverage alongside the coastal E11 and inland E311 corridors, for "
        "a more complete picture of Dubai-Sharjah traffic activity."
    ),
)

CORRIDORS: dict = {
    "E311": _E311.as_dict(),
    "E11": _E11.as_dict(),
    "E611": _E611.as_dict(),
}


def list_corridor_codes() -> List[str]:
    """Return all configured road codes, e.g. ['E311', 'E11']."""
    return list(CORRIDORS.keys())


def get_corridor(road_code: str) -> dict:
    """Look up a corridor definition by road code.

    Raises:
        KeyError: if the road code is not configured.
    """
    if road_code not in CORRIDORS:
        raise KeyError(
            f"Unknown corridor road_code '{road_code}'. "
            f"Available corridors: {list_corridor_codes()}"
        )
    return CORRIDORS[road_code]


def add_corridor(
    road_code: str,
    name: str,
    coordinates: List[Coordinate],
    buffer_meters: int = 100,
    description: str = "",
) -> None:
    """Register an additional corridor at runtime.

    Provided so new corridors can be added programmatically (e.g. from a
    future admin UI or config file) without editing this module.
    """
    corridor = Corridor(
        road_code=road_code,
        name=name,
        coordinates=coordinates,
        buffer_meters=buffer_meters,
        description=description,
    )
    CORRIDORS[road_code] = corridor.as_dict()
