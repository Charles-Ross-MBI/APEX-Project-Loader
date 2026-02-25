from math import floor, hypot  # hypot used by line center logic

from shapely.geometry import (
    Point,
    LineString,
    Polygon,
    MultiPoint,
    MultiLineString,
    MultiPolygon
)
from typing import List, Sequence, Literal
from shapely.geometry import Point, LineString, Polygon, mapping, shape
from shapely.ops import transform
import pyproj


from typing import List, Sequence, Literal
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import transform
import pyproj
from shapely.geometry.base import BaseGeometry

from typing import List, Sequence, Literal
from shapely.geometry import Point, LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
import pyproj


def create_buffers(
    geometry_list: List[Sequence],
    geom_type: Literal["Point", "LineString", "Polygon", "point", "line", "linestring", "polygon"],
    distance_m: float,
    *,
    crs_in: str = "EPSG:4326",
    crs_projected: str = "EPSG:3338",
    crs_out: str = "EPSG:4326",
    cap_style: Literal["round", "flat", "square"] = "round",
    join_style: Literal["round", "mitre", "miter", "bevel"] = "round",
    resolution: int = 16,
) -> List[List[List[float]]]:
    """
    Create buffers for input geometries and return list of buffer exterior rings in [lon, lat].

    Parameters
    ----------
    geometry_list : list
        List of geometries. Coordinates must be in [lon, lat] order for EPSG:4326 (or the CRS you pass).
        - Point:      [lon, lat] or [[lon, lat]]
        - LineString: [[lon, lat], [lon, lat], ...]
        - Polygon:    [[lon, lat], ..., [lon, lat]] (closed or open ring)
    geom_type : {"Point","LineString","Polygon"} (case-insensitive; "Line" also allowed)
        The geometry type of items in geometry_list.
    distance_m : float
        Buffer distance in meters (performed in crs_projected).
    crs_in, crs_projected, crs_out : str
        Input CRS, metric CRS for buffering, and output CRS (default 4326).
    cap_style : {"round","flat","square"}
        Line buffer cap style at segment ends (ignored for polygons/points).
    join_style : {"round","mitre","miter","bevel"}
        Line vertex join style (ignored for polygons/points). "miter" is accepted as alias of "mitre".
    resolution : int
        Number of segments to approximate a quarter circle in buffer.

    Returns
    -------
    List[List[List[float]]]
        For each input geometry, returns the exterior ring of its buffer polygon
        as a closed list of [lon, lat] coordinates.
    """

    # Shapely accepts integer codes for cap/join styles:
    # cap_style: round=1, flat=2, square=3
    # join_style: round=1, mitre=2, bevel=3
    cap_lookup = {"round": 1, "flat": 2, "square": 3}
    join_lookup = {"round": 1, "mitre": 2, "miter": 2, "bevel": 3}

    cap_key = cap_style.lower()
    join_key = join_style.lower()
    if cap_key not in cap_lookup:
        raise ValueError("cap_style must be 'round', 'flat', or 'square'")
    if join_key not in join_lookup:
        raise ValueError("join_style must be 'round', 'mitre'/'miter', or 'bevel'")

    # Configure transformers (always_xy=True enforces lon,lat axis order)
    to_proj = pyproj.Transformer.from_crs(crs_in, crs_projected, always_xy=True).transform
    to_out = pyproj.Transformer.from_crs(crs_projected, crs_out, always_xy=True).transform

    # Normalize geom_type
    gt = geom_type.lower()
    if gt in ("line", "linestring"):
        gt = "linestring"
    elif gt in ("point", "polygon"):
        pass
    else:
        raise ValueError("geom_type must be 'Point', 'LineString', or 'Polygon'")

    def _as_lonlat_tuples(seq: Sequence[Sequence[float]]):
        # Ensure an iterable of (lon, lat) tuples with numeric values
        return [(float(lon), float(lat)) for lon, lat in seq]

    def build_geom(item: Sequence) -> BaseGeometry:
        if gt == "point":
            # Accept [lon, lat] or [[lon, lat]] (take first)
            if isinstance(item[0], (int, float)):
                lon, lat = item  # type: ignore
            else:
                lon, lat = item[0]  # type: ignore
            return Point((float(lon), float(lat)))

        elif gt == "linestring":
            coords = _as_lonlat_tuples(item)  # type: ignore
            return LineString(coords)

        elif gt == "polygon":
            ring = list(item)  # type: ignore
            if len(ring) < 3:
                raise ValueError("Polygon ring must have at least 3 coordinate pairs")
            # Ensure closed ring
            if ring[0] != ring[-1]:
                ring = ring + [ring[0]]
            coords = _as_lonlat_tuples(ring)
            return Polygon(coords)

        # Unreachable
        raise ValueError("Unsupported geometry type")

    buffers_lonlat: List[List[List[float]]] = []

    for item in geometry_list:
        geom_in = build_geom(item)
        geom_proj = transform(to_proj, geom_in)

        buf_proj = geom_proj.buffer(
            distance_m,
            resolution=resolution,
            cap_style=cap_lookup[cap_key],
            join_style=join_lookup[join_key],
        )

        buf_out = transform(to_out, buf_proj)

        # Extract exterior ring only, keep [lon, lat] order
        ext_coords = [[float(x), float(y)] for (x, y) in buf_out.exterior.coords]

        # Ensure closed ring
        if ext_coords[0] != ext_coords[-1]:
            ext_coords.append(ext_coords[0])

        buffers_lonlat.append(ext_coords)

    return buffers_lonlat




class GeometryUtil:
    def __init__(self, epsg=None):
        """
        epsg: (Unused by centers) preserved for API compatibility.
        """
        self.fixed_epsg = epsg

    # -------------------------
    # Public: generic dispatch
    # -------------------------
    def center(self, geom, geom_type: str):
        """
        Compute a representative center.
        Returns (lon, lat).
        """
        gt = (geom_type or "").lower()
        if gt in ("point", "points"):
            return self.point_center(geom)
        if gt in ("line", "lines", "polyline", "polylines"):
            return self.line_center(geom)
        if gt in ("polygon", "polygons"):
            return self.polygon_center(geom)
        raise ValueError(f"Unsupported geom_type for center(): {geom_type}")

    # -------------------------
    # Public: centers
    # -------------------------
    def point_center(self, points):
        """
        Accepts point(s) in (lon, lat) and returns (lon, lat).
        """
        flat_points = self._flatten_points_like(points)
        if not flat_points:
            raise ValueError("No valid point data found.")

        if len(flat_points) == 1:
            lon, lat = flat_points[0]
            return (float(lon), float(lat))

        lons = [float(pt[0]) for pt in flat_points]
        lats = [float(pt[1]) for pt in flat_points]
        return (sum(lons) / len(lons), sum(lats) / len(lats))

    def line_center(self, line_geom):
        if self._is_shapely_multiline(line_geom):
            centers = [self._center_single_line(ls) for ls in line_geom.geoms]
            return self._average_centers(centers)
        if self._is_shapely_linestring(line_geom):
            return self._center_single_line(line_geom)

        # Coordinate-list cases
        if isinstance(line_geom, list) and len(line_geom) > 0 and isinstance(line_geom[0], list):
            # Multiple lines (e.g., multi-part) -> average centers
            if len(line_geom[0]) > 0 and isinstance(line_geom[0][0], (list, tuple)):
                centers = [self._center_single_line(poly) for poly in line_geom]
                return self._average_centers(centers)
            # Single line [(lon, lat), ...]
            if len(line_geom[0]) == 2:
                return self._center_single_line(line_geom)

        # Fallback
        return self._center_single_line(line_geom)

    def polygon_center(self, poly_geom):
        if self._is_shapely_multipolygon(poly_geom):
            centers = [self._center_single_polygon(pg) for pg in poly_geom.geoms]
            return self._average_centers(centers)
        if self._is_shapely_polygon(poly_geom):
            return self._center_single_polygon(poly_geom)

        # Coordinate-list cases
        if isinstance(poly_geom, list) and len(poly_geom) > 0 and isinstance(poly_geom[0], list):
            # Multiple polygons -> average centers
            if len(poly_geom[0]) > 0 and isinstance(poly_geom[0][0], (list, tuple)):
                centers = [self._center_single_polygon(pg) for pg in poly_geom]
                return self._average_centers(centers)
            # Single polygon ring [(lon, lat), ...]
            if len(poly_geom[0]) == 2:
                return self._center_single_polygon(poly_geom)

        # Fallback
        return self._center_single_polygon(poly_geom)

    # -------------------------
    # Internal helpers (centers)
    # -------------------------
    def _center_single_line(self, g):
        """
        Accepts LineString-like geometry and returns center point (lon, lat).
        """
        # Shapely LineString
        if self._is_shapely_linestring(g):
            mid = g.interpolate(g.length / 2.0)
            return (mid.x, mid.y)  # (lon, lat)

        # List-like coordinates
        coords = g
        if not isinstance(coords, (list, tuple)) or len(coords) == 0:
            raise ValueError("Invalid line geometry.")

        if len(coords) < 2:
            # Single coordinate
            lon, lat = coords[0]
            return (lon, lat)

        # Total length in lon-lat plane (euclidean on projected/plain degrees)
        from math import hypot

        total = 0.0
        for i in range(len(coords) - 1):
            a = coords[i]; b = coords[i + 1]
            total += hypot(b[0] - a[0], b[1] - a[1])  # use (lon, lat)

        target = total / 2.0
        d = 0.0
        for i in range(len(coords) - 1):
            a = coords[i]; b = coords[i + 1]
            seg = hypot(b[0] - a[0], b[1] - a[1])
            if d + seg >= target and seg > 0.0:
                t = (target - d) / seg
                lon = a[0] + t * (b[0] - a[0])
                lat = a[1] + t * (b[1] - a[1])
                return (lon, lat)
            d += seg

        lon, lat = coords[-1]
        return (lon, lat)

    def _center_single_polygon(self, g):
        """
        Accepts Polygon-like geometry and returns centroid (lon, lat).
        """
        # Shapely Polygon
        if self._is_shapely_polygon(g):
            c = g.centroid
            return (c.x, c.y)  # (lon, lat)

        # List-like polygon ring
        coords = g
        if len(coords) < 3:
            if len(coords) == 1:
                lon, lat = coords[0]
                return (lon, lat)
            if len(coords) == 2:
                (lon1, lat1), (lon2, lat2) = coords
                return ((lon1 + lon2) / 2.0, (lat1 + lat2) / 2.0)
            raise ValueError("Polygon must have at least 3 coordinates")

        # Ensure closed ring in (lon, lat)
        ring = coords if coords[0] == coords[-1] else coords + [coords[0]]
        xs = [p[0] for p in ring]  # lons
        ys = [p[1] for p in ring]  # lats

        # Shoelace for centroid
        A = 0.0; Cx = 0.0; Cy = 0.0
        for i in range(len(ring) - 1):
            cross = xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
            A += cross
            Cx += (xs[i] + xs[i + 1]) * cross
            Cy += (ys[i] + ys[i + 1]) * cross
        A *= 0.5

        if A == 0.0:
            # Degenerate polygon: average vertices (excluding duplicate last)
            lon_avg = sum(xs[:-1]) / (len(xs) - 1)
            lat_avg = sum(ys[:-1]) / (len(ys) - 1)
            return (lon_avg, lat_avg)

        Cx /= (6.0 * A)
        Cy /= (6.0 * A)
        return (Cx, Cy)

    def _average_centers(self, centers):
        xs = [c[0] for c in centers]
        ys = [c[1] for c in centers]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    # -------------------------
    # Internal helpers (flatten/shape)
    # -------------------------
    def _is_lonlat_pair(self, v):
        return isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)

    def _flatten_points_like(self, points_input):
        """
        Normalizes various point-like shapes into a flat list of (lon, lat).
        """
        flat = []
        if self._is_lonlat_pair(points_input):
            flat.append(points_input)
            return flat
        if isinstance(points_input, (list, tuple)):
            for item in points_input:
                if self._is_lonlat_pair(item):
                    flat.append(item)
                elif isinstance(item, (list, tuple)):
                    for pt in item:
                        if self._is_lonlat_pair(pt):
                            flat.append(pt)
        return flat

    def _flatten_lines_like(self, line_input):
        """
        Normalizes line-like inputs to a list of lines; each line is a list of (lon, lat).
        """
        if self._is_shapely_multiline(line_input):
            out = []
            for ls in line_input.geoms:
                out.append([(x, y) for (x, y) in ls.coords])  # keep (lon, lat)
            return out
        if self._is_shapely_linestring(line_input):
            coords = list(line_input.coords)
            return [[(x, y) for (x, y) in coords]]  # keep (lon, lat)
        if isinstance(line_input, (list, tuple)) and len(line_input) > 0 and self._is_lonlat_pair(line_input[0]):
            return [list(line_input)]
        if isinstance(line_input, (list, tuple)) and len(line_input) > 0 and isinstance(line_input[0], (list, tuple)):
            if len(line_input[0]) > 0 and isinstance(line_input[0][0], (list, tuple)):
                return [list(poly) for poly in line_input]
        return [list(line_input)]

    def _flatten_polygons_like(self, poly_input):
        """
        Normalizes polygon-like inputs to a list of rings; each ring is a list of (lon, lat).
        """
        if self._is_shapely_multipolygon(poly_input):
            out = []
            for pg in poly_input.geoms:
                out.append([(x, y) for (x, y) in pg.exterior.coords])  # keep (lon, lat)
            return out
        if self._is_shapely_polygon(poly_input):
            exterior = list(poly_input.exterior.coords)
            return [[(x, y) for (x, y) in exterior]]  # keep (lon, lat)
        if isinstance(poly_input, (list, tuple)) and len(poly_input) > 0 and self._is_lonlat_pair(poly_input[0]):
            return [list(poly_input)]
        if isinstance(poly_input, (list, tuple)) and len(poly_input) > 0 and isinstance(poly_input[0], (list, tuple)):
            if len(poly_input[0]) > 0 and isinstance(poly_input[0][0], (list, tuple)):
                return [list(pg) for pg in poly_input]
        return [list(poly_input)]

    def _ensure_closed_ring_latlon(self, ring):
        if len(ring) == 0:
            return ring
        return ring if ring[0] == ring[-1] else ring + [ring[0]]

    # -------------------------
    # Shapely type predicates (restored)
    # -------------------------
    def _is_shapely_linestring(self, obj):
        # Shapely LineString has 'coords' and geom_type 'LineString'
        return hasattr(obj, "coords") and getattr(obj, "geom_type", "") == "LineString"

    def _is_shapely_multiline(self, obj):
        # Shapely MultiLineString has geom_type 'MultiLineString' and 'geoms'
        return getattr(obj, "geom_type", "") == "MultiLineString" and hasattr(obj, "geoms")

    def _is_shapely_polygon(self, obj):
        # Shapely Polygon has 'exterior' and geom_type 'Polygon'
        return hasattr(obj, "exterior") and getattr(obj, "geom_type", "") == "Polygon"

    def _is_shapely_multipolygon(self, obj):
        # Shapely MultiPolygon has geom_type 'MultiPolygon' and 'geoms'
        return getattr(obj, "geom_type", "") == "MultiPolygon" and hasattr(obj, "geoms")
