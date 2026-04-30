from __future__ import annotations

from PySide6.QtCore import QPointF


class CurvePoint:
    """曲线上的单个点"""

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class CurveOverlayItem:
    """曲线覆盖层数据"""

    def __init__(self, color: str = "#0078D4", point_shape: str = "circle"):
        self.points: list = []
        self.color = color
        self.name = "曲线"
        self.point_shape = point_shape

    def add_point(self, x: float, y: float) -> None:
        self.points.append((x, y))

    def clear_points(self) -> None:
        self.points.clear()

    def get_points(self):
        return self.points


class MaskOverlay:
    """蒙版覆盖层"""

    def __init__(self):
        self.enabled = False
        self.include_mode = False
        self.polygons = []

    def reset(self) -> None:
        self.enabled = False
        self.polygons.clear()

    def add_polygon(self, polygon) -> None:
        self.polygons.append(polygon)
        self.enabled = True

    def is_point_inside(self, x: float, y: float) -> bool:
        if not self.enabled or not self.polygons:
            return True

        inside = False
        for polygon in self.polygons:
            if self._point_in_polygon(x, y, polygon):
                inside = True
                break
        return inside if self.include_mode else not inside

    def get_polygon_at_point(self, x: float, y: float) -> int:
        if not self.enabled or not self.polygons:
            return -1

        for idx, polygon in enumerate(self.polygons):
            if self._point_in_polygon(x, y, polygon):
                return idx
        return -1

    def remove_polygon_at_point(self, x: float, y: float, radius: float) -> bool:
        if not self.enabled or not self.polygons:
            return False

        for idx, polygon in enumerate(self.polygons):
            if self._polygon_circle_intersect(polygon, x, y, radius):
                del self.polygons[idx]
                return True
        return False

    def _polygon_circle_intersect(self, polygon, cx: float, cy: float, r: float) -> bool:
        for px, py in polygon:
            dx = px - cx
            dy = py - cy
            if dx * dx + dy * dy <= r * r:
                return True

        if self._point_in_polygon(cx, cy, polygon):
            return True

        n = len(polygon)
        for i in range(n):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % n]
            if self._circle_segment_intersect(cx, cy, r, p1, p2):
                return True

        return False

    def _circle_segment_intersect(self, cx: float, cy: float, r: float, p1: tuple, p2: tuple) -> bool:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]

        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            return False

        fx = p1[0] - cx
        fy = p1[1] - cy

        t = max(0, min(1, -(fx * dx + fy * dy) / len_sq))

        nearest_x = p1[0] + t * dx
        nearest_y = p1[1] + t * dy

        dx_n = nearest_x - cx
        dy_n = nearest_y - cy
        dist_sq = dx_n * dx_n + dy_n * dy_n

        return dist_sq <= r * r

    def _point_in_polygon(self, x: float, y: float, polygon) -> bool:
        n = len(polygon)
        if n < 3:
            return False
        inside = False
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside


class CalibrationOverlay:
    """校准点覆盖层"""

    def __init__(self):
        self.x_start = None
        self.x_end = None
        self.y_start = None
        self.y_end = None
        self.x_range = (0.0, 1.0)
        self.y_range = (0.0, 1.0)
        self.coord_type = "linear"

    def reset(self) -> None:
        self.x_start = None
        self.x_end = None
        self.y_start = None
        self.y_end = None
        self.coord_type = "linear"
        self.x_range = (0.0, 1.0)
        self.y_range = (0.0, 1.0)

    def is_complete(self) -> bool:
        if self.coord_type == "polar":
            return self.x_start is not None and self.x_end is not None
        return (
            self.x_start is not None
            and self.x_end is not None
            and self.y_start is not None
            and self.y_end is not None
        )

    def next_point_type(self) -> str:
        if self.coord_type == "polar":
            if self.x_start is None:
                return "origin"
            if self.x_end is None:
                return "angle_radius_point"
            return "complete"
        if self.x_start is None:
            return "x_start"
        if self.x_end is None:
            return "x_end"
        if self.y_start is None:
            return "y_start"
        if self.y_end is None:
            return "y_end"
        return "complete"

    def get_current_point(self) -> QPointF:
        if self.coord_type == "polar":
            if self.x_start is None:
                return self.x_start
            if self.x_end is None:
                return self.x_end
        else:
            if self.x_start is None:
                return self.x_start
            if self.x_end is None:
                return self.x_end
            if self.y_start is None:
                return self.y_start
            if self.y_end is None:
                return self.y_end
        return None

    def set_current_point(self, pos: QPointF):
        if self.coord_type == "polar":
            if self.x_start is None:
                self.x_start = pos
            elif self.x_end is None:
                self.x_end = pos
        else:
            if self.x_start is None:
                self.x_start = pos
            elif self.x_end is None:
                self.x_end = pos
            elif self.y_start is None:
                self.y_start = pos
            elif self.y_end is None:
                self.y_end = pos

    def nudge_current_point(self, dx: float, dy: float):
        if self.coord_type == "polar":
            if self.x_start is None:
                pass
            elif self.x_end is None:
                self.x_start = QPointF(self.x_start.x() + dx, self.x_start.y() + dy)
            else:
                self.x_end = QPointF(self.x_end.x() + dx, self.x_end.y() + dy)
        else:
            if self.x_start is None:
                pass
            elif self.x_end is None:
                self.x_start = QPointF(self.x_start.x() + dx, self.x_start.y() + dy)
            elif self.y_start is None:
                self.x_end = QPointF(self.x_end.x() + dx, self.x_end.y() + dy)
            elif self.y_end is None:
                self.y_start = QPointF(self.y_start.x() + dx, self.y_start.y() + dy)
            else:
                self.y_end = QPointF(self.y_end.x() + dx, self.y_end.y() + dy)
