# =============================================================================
# GeometryOps: Centers & AGOL-Ready Buffers (Single Unioned Buffer)
# =============================================================================
# - Inputs: [lat, lon] for list-based geometries; Shapely geometries also allowed.
# - Centers: returned as (lon, lat) EXACTLY as originally specified.
# - Buffers: returned as a single Esri JSON polygon:
#       {"rings": [[[x,y],...], ...], "spatialReference": {"wkid": <wkid>}}
#   where x=lon, y=lat and wkid defaults to 4326.
# - Buffer distances are in METERS; buffering is performed in a projected CRS
#   (auto-selected UTM per input centroid, or a fixed EPSG if provided).
# - External imports (Shapely, PyProj) must be present as shown above.
# =============================================================================

# =============================================================================
# REQUIRED IMPORTS FOR GeometryOps CLASS
# =============================================================================
from math import floor, hypot

from shapely.geometry import (
    Point,
    LineString,
    Polygon,
    MultiPoint,
    MultiLineString,
    MultiPolygon
)

from pyproj import CRS, Transformer

class GeometryUtil:
    def __init__(self, epsg=None):
        """
        epsg: Optional projected EPSG to use for buffering. If None, a local UTM is chosen per input.
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

    def buffer(self, geom, geom_type: str, distance_m: float, *, quad_segs: int = 8, wkid: int = 4326):
        """
        Generate a single unioned buffer for all input geometries, as Esri JSON Polygon:
            {"rings": [...], "spatialReference": {"wkid": wkid}}
        """
        gt = (geom_type or "").lower()
        if gt in ("point", "points"):
            return self.point_buffer(geom, distance_m, quad_segs=quad_segs, wkid=wkid)
        if gt in ("line", "lines", "polyline", "polylines"):
            return self.line_buffer(geom, distance_m, quad_segs=quad_segs, wkid=wkid)
        if gt in ("polygon", "polygons"):
            return self.polygon_buffer(geom, distance_m, quad_segs=quad_segs, wkid=wkid)
        raise ValueError(f"Unsupported geom_type for buffer(): {geom_type}")

    # -------------------------
    # Public: centers (unchanged contract -> (lon, lat))
    # -------------------------
    def point_center(self, points):
        flat_points = self._flatten_points_like(points)
        if not flat_points:
            raise ValueError("No valid point data found.")

        if len(flat_points) == 1:
            lat, lon = flat_points[0]
            return (float(lon), float(lat))

        lats = [float(pt[0]) for pt in flat_points]
        lons = [float(pt[1]) for pt in flat_points]
        return (sum(lons) / len(lons), sum(lats) / len(lats))

    def line_center(self, line_geom):
        if self._is_shapely_multiline(line_geom):
            centers = [self._center_single_line(ls) for ls in line_geom.geoms]
            return self._average_centers(centers)
        if self._is_shapely_linestring(line_geom):
            return self._center_single_line(line_geom)

        if isinstance(line_geom, list) and len(line_geom) > 0 and isinstance(line_geom[0], list):
            if len(line_geom[0]) > 0 and isinstance(line_geom[0][0], (list, tuple)):
                centers = [self._center_single_line(poly) for poly in line_geom]
                return self._average_centers(centers)
            if len(line_geom[0]) == 2:
                return self._center_single_line(line_geom)

        return self._center_single_line(line_geom)

    def polygon_center(self, poly_geom):
        if self._is_shapely_multipolygon(poly_geom):
            centers = [self._center_single_polygon(pg) for pg in poly_geom.geoms]
            return self._average_centers(centers)
        if self._is_shapely_polygon(poly_geom):
            return self._center_single_polygon(poly_geom)

        if isinstance(poly_geom, list) and len(poly_geom) > 0 and isinstance(poly_geom[0], list):
            if len(poly_geom[0]) > 0 and isinstance(poly_geom[0][0], (list, tuple)):
                centers = [self._center_single_polygon(pg) for pg in poly_geom]
                return self._average_centers(centers)
            if len(poly_geom[0]) == 2:
                return self._center_single_polygon(poly_geom)

        return self._center_single_polygon(poly_geom)

    # -------------------------
    # Public: buffers (AGOL Esri JSON polygon geometry; ALWAYS ONE UNIONED BUFFER)
    # -------------------------
    def point_buffer(self, points, distance_m: float, *, quad_segs: int = 8, wkid: int = 4326):
        pts = self._flatten_points_like(points)
        if not pts:
            raise ValueError("No valid point data found.")

        ref_lat = sum(p[0] for p in pts) / len(pts)
        ref_lon = sum(p[1] for p in pts) / len(pts)
        fwd, inv = self._build_projectors((ref_lon, ref_lat))

        # MultiPoint -> buffer once; this yields a single (possibly multipart) polygon
        mp = MultiPoint([Point(*fwd(lon, lat)) for (lat, lon) in pts])
        buf = mp.buffer(distance_m, resolution=quad_segs)
        return self._shapely_polygon_to_esri_json(buf, inv, wkid)

    def line_buffer(self, line_geom, distance_m: float, *, quad_segs: int = 8, wkid: int = 4326):
        polylines = self._flatten_lines_like(line_geom)
        if not polylines:
            raise ValueError("No valid line data found.")

        all_pts = [pt for pl in polylines for pt in pl]
        ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
        ref_lon = sum(p[1] for p in all_pts) / len(all_pts)
        fwd, inv = self._build_projectors((ref_lon, ref_lat))

        # MultiLineString -> single buffer
        lines_xy = [LineString(self._to_xy(pl, fwd)) for pl in polylines]
        geom = MultiLineString(lines_xy) if len(lines_xy) > 1 else lines_xy[0]
        buf = geom.buffer(distance_m, resolution=quad_segs)
        return self._shapely_polygon_to_esri_json(buf, inv, wkid)

    def polygon_buffer(self, poly_geom, distance_m: float, *, quad_segs: int = 8, wkid: int = 4326):
        polygons = self._flatten_polygons_like(poly_geom)
        if not polygons:
            raise ValueError("No valid polygon data found.")

        polygons = [self._ensure_closed_ring_latlon(pg) for pg in polygons]

        all_pts = [pt for pg in polygons for pt in pg]
        ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
        ref_lon = sum(p[1] for p in all_pts) / len(all_pts)
        fwd, inv = self._build_projectors((ref_lon, ref_lat))

        # MultiPolygon -> single buffer
        polys_xy = []
        for pg in polygons:
            ring_xy = self._to_xy(pg, fwd)
            if ring_xy[0] != ring_xy[-1]:
                ring_xy = ring_xy + [ring_xy[0]]
            polys_xy.append(Polygon(ring_xy))

        geom = MultiPolygon(polys_xy) if len(polys_xy) > 1 else polys_xy[0]
        buf = geom.buffer(distance_m, resolution=quad_segs)
        return self._shapely_polygon_to_esri_json(buf, inv, wkid)

    # -------------------------
    # Internal helpers (centers)
    # -------------------------
    def _center_single_line(self, g):
        if self._is_shapely_linestring(g):
            mid = g.interpolate(g.length / 2.0)
            return (mid.x, mid.y)

        coords = g
        if not isinstance(coords, (list, tuple)) or len(coords) == 0:
            raise ValueError("Invalid line geometry.")

        if len(coords) < 2:
            lat, lon = coords[0]
            return (lon, lat)

        total = 0.0
        for i in range(len(coords) - 1):
            a = coords[i]; b = coords[i + 1]
            total += hypot(b[0] - a[0], b[1] - a[1])

        target = total / 2.0
        d = 0.0
        for i in range(len(coords) - 1):
            a = coords[i]; b = coords[i + 1]
            seg = hypot(b[0] - a[0], b[1] - a[1])
            if d + seg >= target and seg > 0.0:
                t = (target - d) / seg
                lat = a[0] + t * (b[0] - a[0])
                lon = a[1] + t * (b[1] - a[1])
                return (lon, lat)
            d += seg

        lat, lon = coords[-1]
        return (lon, lat)

    def _center_single_polygon(self, g):
        if self._is_shapely_polygon(g):
            c = g.centroid
            return (c.x, c.y)

        coords = g
        if len(coords) < 3:
            if len(coords) == 1:
                lat, lon = coords[0]
                return (lon, lat)
            if len(coords) == 2:
                (lat1, lon1), (lat2, lon2) = coords
                return ((lon1 + lon2) / 2.0, (lat1 + lat2) / 2.0)
            raise ValueError("Polygon must have at least 3 coordinates")

        ring = coords if coords[0] == coords[-1] else coords + [coords[0]]
        xs = [p[1] for p in ring]  # lon
        ys = [p[0] for p in ring]  # lat

        A = 0.0; Cx = 0.0; Cy = 0.0
        for i in range(len(ring) - 1):
            cross = xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
            A += cross
            Cx += (xs[i] + xs[i + 1]) * cross
            Cy += (ys[i] + ys[i + 1]) * cross
        A *= 0.5

        if A == 0.0:
            lon_avg = sum(xs[:-1]) / (len(xs) - 1)
            lat_avg = sum(ys[:-1]) / (len(ys) - 1)
            return (lon_avg, lat_avg)

        Cx /= (6.0 * A)
        Cy /= (6.0 * A)
        return (Cx, Cy)

    def _average_centers(self, centers):
        """
        Average a list of (lon, lat) pairs into a single (lon, lat) center.
        """
        if not centers:
            raise ValueError("No centers provided.")
        xs = [c[0] for c in centers]
        ys = [c[1] for c in centers]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    # -------------------------
    # Internal helpers (projection)
    # -------------------------
    def _utm_epsg_for_lonlat(self, lon: float, lat: float) -> int:
        zone = int(floor((lon + 180.0) / 6.0) + 1)
        return (32600 if lat >= 0 else 32700) + zone

    def _build_projectors(self, reference_lonlat):
        lon0, lat0 = reference_lonlat
        epsg = self.fixed_epsg if self.fixed_epsg is not None else self._utm_epsg_for_lonlat(lon0, lat0)
        crs_src = CRS.from_epsg(4326)
        crs_dst = CRS.from_epsg(epsg)
        fwd_raw = Transformer.from_crs(crs_src, crs_dst, always_xy=True).transform
        inv_raw = Transformer.from_crs(crs_dst, crs_src, always_xy=True).transform
        return (lambda lon, lat: fwd_raw(lon, lat)), (lambda x, y: inv_raw(x, y))

    def _to_xy(self, latlon_list, fwd):
        return [fwd(lon, lat) for (lat, lon) in latlon_list]

    # -------------------------
    # Internal helpers (Esri JSON conversion)
    # -------------------------
    def _shapely_polygon_to_esri_json(self, geom, inv, wkid: int) -> dict:
        """
        Convert Shapely Polygon/MultiPolygon/GeometryCollection (projected) -> Esri JSON Polygon.
        Output:
            {"rings": [ [[x,y],...], ... ], "spatialReference": {"wkid": wkid}}
        Notes:
          - x=lon, y=lat (when wkid=4326).
          - Multipart areas are represented as multiple rings in a single Polygon geometry.
          - Holes are included as rings; ArcGIS determines interior rings automatically.
        """
        rings: list[list[list[float]]] = []

        def ring_to_lonlat(ring):
            coords = list(ring.coords)
            out = []
            for (x, y) in coords:
                lon, lat = inv(x, y)
                out.append([float(lon), float(lat)])
            return out

        gtype = getattr(geom, "geom_type", "")

        if gtype == "Polygon":
            rings.append(ring_to_lonlat(geom.exterior))
            for hole in geom.interiors:
                rings.append(ring_to_lonlat(hole))
        elif gtype == "MultiPolygon":
            for poly in geom.geoms:
                rings.append(ring_to_lonlat(poly.exterior))
                for hole in poly.interiors:
                    rings.append(ring_to_lonlat(hole))
        elif gtype == "GeometryCollection":
            for g in geom.geoms:
                gt = getattr(g, "geom_type", "")
                if gt == "Polygon":
                    rings.append(ring_to_lonlat(g.exterior))
                    for hole in g.interiors:
                        rings.append(ring_to_lonlat(hole))
                elif gt == "MultiPolygon":
                    for poly in g.geoms:
                        rings.append(ring_to_lonlat(poly.exterior))
                        for hole in poly.interiors:
                            rings.append(ring_to_lonlat(hole))
        else:
            if hasattr(geom, "exterior"):
                rings.append(ring_to_lonlat(geom.exterior))

        return {"rings": rings, "spatialReference": {"wkid": int(wkid)}}

    # -------------------------
    # Internal helpers (flatten/shape & shapely duck typing)
    # -------------------------
    def _is_latlon_pair(self, v):
        return isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)

    def _flatten_points_like(self, points_input):
        flat = []
        if self._is_latlon_pair(points_input):
            flat.append(points_input)
            return flat
        if isinstance(points_input, (list, tuple)):
            for item in points_input:
                if self._is_latlon_pair(item):
                    flat.append(item)
                elif isinstance(item, (list, tuple)):
                    for pt in item:
                        if self._is_latlon_pair(pt):
                            flat.append(pt)
        return flat

    def _flatten_lines_like(self, line_input):
        if self._is_shapely_multiline(line_input):
            out = []
            for ls in line_input.geoms:
                out.append([(y, x) for (x, y) in ls.coords])
            return out
        if self._is_shapely_linestring(line_input):
            coords = list(line_input.coords)  # (x=lon, y=lat)
            return [[(y, x) for (x, y) in coords]]
        if isinstance(line_input, (list, tuple)) and len(line_input) > 0 and self._is_latlon_pair(line_input[0]):
            return [list(line_input)]
        if isinstance(line_input, (list, tuple)) and len(line_input) > 0 and isinstance(line_input[0], (list, tuple)):
            if len(line_input[0]) > 0 and isinstance(line_input[0][0], (list, tuple)):
                return [list(poly) for poly in line_input]
        return [list(line_input)]

    def _flatten_polygons_like(self, poly_input):
        if self._is_shapely_multipolygon(poly_input):
            out = []
            for pg in poly_input.gems:
                out.append([(y, x) for (x, y) in pg.exterior.coords])
            return out
        if self._is_shapely_polygon(poly_input):
            exterior = list(poly_input.exterior.coords)
            return [[(y, x) for (x, y) in exterior]]
        if isinstance(poly_input, (list, tuple)) and len(poly_input) > 0 and self._is_latlon_pair(poly_input[0]):
            return [list(poly_input)]
        if isinstance(poly_input, (list, tuple)) and len(poly_input) > 0 and isinstance(poly_input[0], (list, tuple)):
            if len(poly_input[0]) > 0 and isinstance(poly_input[0][0], (list, tuple)):
                return [list(pg) for pg in poly_input]
        return [list(poly_input)]

    def _ensure_closed_ring_latlon(self, ring):
        if len(ring) == 0:
            return ring
        return ring if ring[0] == ring[-1] else ring + [ring[0]]

    def _is_shapely_linestring(self, obj):
        return hasattr(obj, "coords") and getattr(obj, "geom_type", "") == "LineString"

    def _is_shapely_multiline(self, obj):
        return getattr(obj, "geom_type", "") == "MultiLineString" and hasattr(obj, "geoms")

    def _is_shapely_polygon(self, obj):
        return hasattr(obj, "exterior") and getattr(obj, "geom_type", "") == "Polygon"

    def _is_shapely_multipolygon(self, obj):
        return getattr(obj, "geom_type", "") == "MultiPolygon" and hasattr(obj, "geoms")