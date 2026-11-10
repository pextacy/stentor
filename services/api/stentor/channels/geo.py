"""Optional CAP area geometry: polygons, circles and geocodes (CAP 1.2 section 3.2.4)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

Point = tuple[float, float]  # (lat, lon), WGS 84


def _check_point(p: Point) -> Point:
    lat, lon = p
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"point {lat},{lon} is outside WGS 84 range")
    return (round(lat, 6), round(lon, 6))


class Circle(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=1000)


class Geocode(BaseModel):
    name: str = Field(min_length=1, max_length=40)  # e.g. SAME, FIPS6, UGC
    value: str = Field(min_length=1, max_length=40)


class CapArea(BaseModel):
    desc: str | None = Field(default=None, max_length=200)
    polygons: list[list[Point]] = []
    circles: list[Circle] = []
    geocodes: list[Geocode] = []

    @field_validator("polygons")
    @classmethod
    def _closed(cls, polys: list[list[Point]]) -> list[list[Point]]:
        """CAP needs at least four points with the first equal to the last. An open ring is
        closed for the operator; fewer than three distinct points is an error."""
        out = []
        for poly in polys:
            pts = [_check_point(tuple(p)) for p in poly]
            if pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(set(pts)) < 3:
                raise ValueError("a polygon needs at least three distinct points")
            out.append(pts)
        return out

    @model_validator(mode="after")
    def _limit(self) -> "CapArea":
        if sum(len(p) for p in self.polygons) > 500:
            raise ValueError("too many polygon points (max 500)")
        return self

    def empty(self) -> bool:
        return not (self.polygons or self.circles or self.geocodes)


def polygon_text(poly: list[Point]) -> str:
    return " ".join(f"{lat},{lon}" for lat, lon in poly)


def circle_text(c: Circle) -> str:
    return f"{c.lat},{c.lon} {c.radius_km}"
