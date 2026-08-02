from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np


def point_in_polygon(
    point: tuple[float, float],
    polygon: tuple[tuple[float, float], ...],
) -> bool:
    """Ray casting algorithm. Boundary points count as inside."""
    if len(polygon) < 3:
        raise ValueError(f"Polygon must have at least 3 vertices, got {len(polygon)}")
    x, y = point
    n = len(polygon)
    inside = False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]

        # Check if point is on edge
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if abs(cross) < 1e-9:
            # Colinear - check if within bounding box
            if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return True

        # Ray casting
        if ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1) + x1
        ):
            inside = not inside

    return inside


@dataclass(frozen=True)
class ROI:
    name: str
    points: tuple[tuple[float, float], ...]
    color: tuple[int, int, int] = (0, 255, 0)

    def __post_init__(self):
        if not self.name:
            raise ValueError("ROI name must not be empty")
        if len(self.points) < 3:
            raise ValueError(
                f"ROI must have at least 3 vertices, got {len(self.points)}"
            )
        for c in self.color:
            if not 0 <= c <= 255:
                raise ValueError(f"invalid color value {c}, must be 0-255")

    def contains(self, point: tuple[float, float]) -> bool:
        return point_in_polygon(point, self.points)
