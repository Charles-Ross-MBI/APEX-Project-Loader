
"""
===============================================================================
AGOL UTILITIES (STREAMLIT) — AUTH, QUERY, AND APPLYEDITS HELPERS
===============================================================================

Purpose:
    Centralizes ArcGIS Online (AGOL) REST API helpers used by the Streamlit app:
      - Token generation (username/password stored in st.session_state)
      - Common query helpers (query_record, select_record, get_multiple_fields,
        get_unique_field_values)
      - Delete helpers (delete_project)
      - Geometry-intersection query wrapper (AGOLQueryIntersect)
      - Feature upload wrapper using applyEdits (AGOLDataLoader)

Key behaviors:
    - Authentication:
        * get_agol_token() requests an AGOL token via generateToken endpoint
        * Uses st.session_state['AGOL_USERNAME'] and ['AGOL_PASSWORD']
    - Querying:
        * SQL-like where queries against /query endpoints
        * Optional geometry return + output spatial reference set to WKID 4326
    - Payload uploads:
        * AGOLDataLoader.add_features() sends applyEdits 'adds' as JSON
        * Parses addResults, aggregates failures, and returns success/message/globalids
    - Geometry intersections:
        * AGOLQueryIntersect supports a single geometry OR a list of geometries
        * Swaps [lat, lon] -> [lon, lat] to match ArcGIS x/y conventions
        * Executes multiple queries and merges unique results

Session-state dependencies (expected at runtime):
    - Credentials (required for all authenticated operations):
        * 'AGOL_USERNAME'
        * 'AGOL_PASSWORD'

Notes:
    - This module performs network requests via requests (HTTP).
    - Errors are surfaced as exceptions in most helpers; some functions return
      False/None to allow callers to implement best-effort cleanup.
    - Spatial reference is consistently treated as WGS84 (WKID 4326).

===============================================================================
"""

import json
import requests
import math
import streamlit as st
import logging
from shapely.geometry import LineString
from shapely.ops import unary_union, linemerge


# =============================================================================
# IDENTIFIER HELPERS
# =============================================================================
# format_guid():
#   - Normalizes GlobalID/GUID formatting to the ArcGIS curly-brace convention
#   - Accepts either a string or a single-element list of strings
# =============================================================================
def format_guid(value) -> str:
    """
    Ensures a GUID/GlobalID value is in the correct ArcGIS format.

    Accepted input:
        - str: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" (with or without braces)
        - list[str]: single-element list returned by some ArcGIS responses

    Returns:
        str | None:
            - A formatted string like "{xxxxxxxx-...}" when valid
            - None when value is empty/invalid
    """
    # If it's a list, take the first element
    if isinstance(value, list):
        if not value:  # empty list
            return None
        value = value[0]

    if not value or not isinstance(value, str):
        return None

    clean_value = value.strip().lstrip("{").rstrip("}")
    parts = clean_value.split("-")
    if len(parts) != 5 or not all(parts):
        return None

    return f"{{{clean_value}}}"


# =============================================================================
# AUTHENTICATION
# =============================================================================
# get_agol_token():
#   - Requests a short-lived token from AGOL using stored credentials
#   - Required by all subsequent query/edit operations
# =============================================================================
def get_agol_token() -> str:
    """
    Generates an authentication token for ArcGIS Online using a username and password.

    Session-state requirements:
        - st.session_state['AGOL_USERNAME']
        - st.session_state['AGOL_PASSWORD']

    Returns:
        str: A valid authentication token used to make authorized API requests.

    Raises:
        ValueError: If authentication fails or token missing from response.
        ConnectionError: If requests cannot reach the AGOL endpoint.
    """
    # ArcGIS Online token generation URL
    url = "https://www.arcgis.com/sharing/rest/generateToken"

    # Payload required for authentication request
    data = {
        "username": st.session_state['AGOL_USERNAME'],
        "password": st.session_state['AGOL_PASSWORD'],
        "referer": "https://www.arcgis.com",  # Required reference for token generation
        "f": "json"  # Request response format
    }

    try:
        # Send authentication request
        response = requests.post(url, data=data)

        # Validate HTTP response status
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        # Parse JSON response
        token_data = response.json()

        # Extract token if authentication is successful
        if "token" in token_data:
            return token_data["token"]
        elif "error" in token_data:
            raise ValueError(f"Authentication failed: {token_data['error']['message']}")
        else:
            raise ValueError("Unexpected response format: Token not found.")

    except requests.exceptions.RequestException as e:
        # Handle network-related errors
        raise ConnectionError(f"Failed to connect to ArcGIS Online: {e}")


# =============================================================================
# QUERY HELPERS (GENERIC)
# =============================================================================
# query_record():
#   - Executes a "where" query against an ArcGIS REST layer /query endpoint
#   - Handles URL normalization to avoid double-appending the layer
# =============================================================================
def query_record(url: str, layer: int, where: str, fields="*", return_geometry=False):
    """
    Executes an SQL-style query against an ArcGIS REST API layer and returns matching records.

    Parameters:
        url: str
            FeatureServer base URL (may or may not already include a layer segment).
        layer: int
            Layer index when url is a FeatureServer root.
        where: str
            SQL-like filter clause (e.g., "GlobalID='...'" or "1=1").
        fields: str
            outFields string. "*" requests all fields.
        return_geometry: bool
            Whether to return geometry in results.

    Returns:
        list: List of 'features' from the ArcGIS REST response.
    """
    token = get_agol_token()
    if not token:
        raise ValueError("Authentication failed: Invalid token.")

    # Normalize URL so we don't double-append the layer
    url = url.rstrip("/")

    # If the URL already ends with the layer number, don't add it again
    if url.split("/")[-1].isdigit():
        query_url = f"{url}/query"
    else:
        query_url = f"{url}/{layer}/query"

    params = {
        "where": where,
        "outFields": fields,
        "returnGeometry": str(return_geometry).lower(),
        "outSR": 4326,
        "f": "json",
        "token": token
    }

    response = requests.get(query_url, params=params)
    if response.status_code != 200:
        raise Exception(
            f"Request failed with status code {response.status_code}: {response.text}"
        )

    data = response.json()
    if "error" in data:
        raise Exception(
            f"API Error: {data['error']['message']} - {data['error'].get('details', [])}"
        )

    return data.get("features", [])





import math
import requests
import streamlit as st
from shapely.geometry import LineString
from shapely.ops import unary_union, linemerge


def get_route_segment(
    route_name: str,
    from_mp: float,
    to_mp: float,
    *,
    simplify: bool = True,
    # Adaptive tolerance policy (in meters, converted to degrees internally)
    tolerance_frac: float = 0.001,   # 0.1% of route length
    min_tolerance_m: float = 5.0,    # clamp low end
    max_tolerance_m: float = 25.0,   # clamp high end
    preserve_topology: bool = True,
    # Guardrails: prevent oversimplification
    max_point_reduction: float = 0.90,  # don't remove >90% of vertices
    min_points: int = 50               # but also don't reduce below this
):
    """
    Queries the Pavement Condition Tenth Mile dataset for a route + milepost range,
    merges all geometry paths into a single unified line, optionally simplifies it
    while staying strictly in EPSG:4326, and returns a folium-ready list of
    [lat, lon] coordinates.
    """

    # ---------------------------------------------------------
    # Helper functions (all 4326, no reprojection)
    # ---------------------------------------------------------
    def _normalize_to_single_line(g):
        """
        Returns a single LineString:
        - If LineString: return as-is
        - If MultiLineString: return the longest
        - If GeometryCollection: collect lines and return the longest after merge
        """
        if g is None or g.is_empty:
            return None

        if g.geom_type == "LineString":
            return g

        if g.geom_type == "MultiLineString":
            parts = list(g.geoms)
            return max(parts, key=lambda x: x.length) if parts else None

        # GeometryCollection or others
        if hasattr(g, "geoms"):
            line_parts = []
            for sub in g.geoms:
                if sub.geom_type == "LineString":
                    line_parts.append(sub)
                elif sub.geom_type == "MultiLineString":
                    line_parts.extend(list(sub.geoms))

            if not line_parts:
                return None

            merged_lines = linemerge(unary_union(line_parts))
            if merged_lines.geom_type == "LineString":
                return merged_lines
            if merged_lines.geom_type == "MultiLineString":
                parts = list(merged_lines.geoms)
                return max(parts, key=lambda x: x.length) if parts else None

        return None

    def _mean_lat(line):
        coords = list(line.coords)
        if not coords:
            return 0.0
        return sum(lat for lon, lat in coords) / len(coords)

    def _meters_per_degree(lat_deg):
        """
        Approx meters per degree at given latitude.
        (Good enough for tolerance sizing; keeps CRS in 4326.)
        """
        lat_rad = math.radians(lat_deg)
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * math.cos(lat_rad)
        # Avoid zero near poles
        m_per_deg_lon = max(m_per_deg_lon, 1e-6)
        return m_per_deg_lat, m_per_deg_lon

    def _approx_length_m(line):
        """
        Approximate geodesic length in meters using a local equirectangular approximation.
        Uses per-segment scaling based on mean latitude.
        """
        coords = list(line.coords)
        if len(coords) < 2:
            return 0.0

        lat0 = _mean_lat(line)
        m_per_deg_lat, m_per_deg_lon = _meters_per_degree(lat0)

        total = 0.0
        (x0, y0) = coords[0]
        for (x1, y1) in coords[1:]:
            dx_m = (x1 - x0) * m_per_deg_lon
            dy_m = (y1 - y0) * m_per_deg_lat
            total += math.hypot(dx_m, dy_m)
            x0, y0 = x1, y1
        return total

    def _adaptive_tolerance_deg(line):
        """
        Determine tolerance in degrees by:
        1) approximate length in meters
        2) tolerance_m = clamp(length_m * tolerance_frac, min_tolerance_m, max_tolerance_m)
        3) convert meters to degrees using local meters/degree
        """
        length_m = _approx_length_m(line)
        tol_m = length_m * float(tolerance_frac)

        tol_m = max(float(min_tolerance_m), min(float(max_tolerance_m), tol_m))

        lat0 = _mean_lat(line)
        m_per_deg_lat, m_per_deg_lon = _meters_per_degree(lat0)

        # Convert meters -> degrees (use the "stricter" conversion so we don't oversimplify)
        tol_deg_lat = tol_m / m_per_deg_lat
        tol_deg_lon = tol_m / m_per_deg_lon

        # Use the smaller degree tolerance to be conservative
        return min(tol_deg_lat, tol_deg_lon), tol_m, length_m

    def _simplify_with_guardrails(line):
        """
        Simplify with adaptive tolerance but ensure we don't nuke the shape:
        - preserve topology
        - limit vertex reduction
        - keep at least min_points (when possible)
        """
        if line is None or line.is_empty:
            return line

        orig_coords = list(line.coords)
        if len(orig_coords) < 3:
            return line

        tol_deg, tol_m, length_m = _adaptive_tolerance_deg(line)

        simplified = line.simplify(tol_deg, preserve_topology=preserve_topology)

        # If simplification yields something unusable, revert
        if simplified.is_empty or simplified.geom_type != "LineString":
            return line

        simp_coords = list(simplified.coords)
        if len(simp_coords) < 2:
            return line

        # Guardrail 1: don't reduce below min_points unless original is already small
        if len(orig_coords) >= min_points and len(simp_coords) < min_points:
            # Ease off: reduce tolerance until we hit min_points or give up
            # Do a small backoff loop without being too expensive
            backoff = 0.5
            for _ in range(6):
                tol_deg *= backoff
                simplified2 = line.simplify(tol_deg, preserve_topology=preserve_topology)
                if simplified2.geom_type == "LineString":
                    simp2_coords = list(simplified2.coords)
                    if len(simp2_coords) >= min_points:
                        return simplified2
            return line

        # Guardrail 2: don't remove "too many" vertices
        removed_frac = 1.0 - (len(simp_coords) / max(1, len(orig_coords)))
        if removed_frac > max_point_reduction:
            # Ease off tolerance similarly
            backoff = 0.5
            for _ in range(6):
                tol_deg *= backoff
                simplified2 = line.simplify(tol_deg, preserve_topology=preserve_topology)
                if simplified2.geom_type == "LineString":
                    simp2_coords = list(simplified2.coords)
                    removed_frac2 = 1.0 - (len(simp2_coords) / max(1, len(orig_coords)))
                    if removed_frac2 <= max_point_reduction:
                        return simplified2
            return line

        return simplified

    # ---------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------
    token = get_agol_token()
    if not token:
        raise ValueError("Authentication failed: Invalid token.")

    # ---------------------------------------------------------
    # Build query URL
    # ---------------------------------------------------------
    url = st.session_state["mileposts"] + "/0/query"

    where = (
        f"ROUTE_NAME = '{route_name}' "
        f"AND FROM_MPT >= {from_mp} "
        f"AND TO_MPT <= {to_mp}"
    )

    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
        "token": token
    }

    # ---------------------------------------------------------
    # Execute query
    # ---------------------------------------------------------
    response = requests.get(url, params=params)
    data = response.json()

    if "error" in data:
        raise Exception(
            f"API Error: {data['error']['message']} - {data['error'].get('details', [])}"
        )

    features = data.get("features", [])
    if not features:
        return []

    # ---------------------------------------------------------
    # Convert all geometry paths into Shapely LineStrings (still 4326)
    # ---------------------------------------------------------
    lines = []
    for f in features:
        geom = f.get("geometry", {}) or {}
        for path in geom.get("paths", []) or []:
            if len(path) >= 2:
                # ArcGIS path coords are [x, y] == [lon, lat]
                line = LineString([(lon, lat) for lon, lat in path])
                if not line.is_empty and line.length > 0:
                    lines.append(line)

    if not lines:
        return []

    # ---------------------------------------------------------
    # Merge overlapping / reversed / crossing segments
    # ---------------------------------------------------------
    merged = linemerge(unary_union(lines))

    # ---------------------------------------------------------
    # Normalize to a single representative LineString
    # ---------------------------------------------------------
    route_line = _normalize_to_single_line(merged)
    if route_line is None or route_line.is_empty:
        return []

    # ---------------------------------------------------------
    # Simplify (adaptive tolerance) while staying in EPSG:4326
    # ---------------------------------------------------------
    if simplify:
        route_line = _simplify_with_guardrails(route_line)

    # ---------------------------------------------------------
    # Convert to Folium format [lat, lon]
    # ---------------------------------------------------------
    coords = list(route_line.coords)
    if not coords:
        return []

    unified_path = [[lat, lon] for lon, lat in coords]
    return unified_path








# =============================================================================
# QUERY HELPERS (FIELD VALUE UTILS)
# =============================================================================
# get_unique_field_values():
#   - Requests distinct values for a field using returnDistinctValues=true
#   - Optionally sorts values alphabetically or numerically
# =============================================================================
def get_unique_field_values(
    url: str,
    layer: str,
    field: str,
    where: str = "1=1",
    sort_type: str = None,  # "alpha" or "numeric"
    sort_order: str = "asc"  # "asc" or "desc"
) -> list:
    """
    Queries an ArcGIS REST API layer to retrieve all unique values from a specified field,
    with optional sorting.

    Parameters:
        url: str
            Base URL of the ArcGIS REST API service.
        layer: str
            Layer ID or name to query.
        field: str
            Field name to retrieve distinct values from.
        where: str
            SQL-style filter expression. Defaults to "1=1".
        sort_type: str | None
            "alpha" for alphabetical or "numeric" for numerical sorting.
        sort_order: str
            "asc" or "desc" (default "asc").

    Returns:
        list: Unique values, optionally sorted.

    Raises:
        ValueError: If authentication fails or field does not exist.
        Exception: If request fails or the API returns an error.
    """
    try:
        # Authenticate and get API token (ensure agol_username and agol_password are defined)
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # Construct query parameters
        params = {
            "where": where,
            "outFields": field,
            "returnDistinctValues": "true",  # ensures unique values
            "returnGeometry": "false",  # no geometry needed
            "f": "json",
            "token": token
        }

        # Formulate the query URL and execute the request
        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        # Validate that requested field exists
        available_fields = {field_info["name"] for field_info in data.get("fields", [])}
        if field not in available_fields:
            raise ValueError(f"Field '{field}' does not exist. Available fields: {available_fields}")

        # Extract unique values
        unique_values = []
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            if field in attributes and attributes[field] not in unique_values:
                unique_values.append(attributes[field])

        # Apply sorting if requested
        if sort_type:
            reverse = sort_order.lower() == "desc"
            if sort_type.lower() == "alpha":
                unique_values.sort(key=lambda x: str(x).lower(), reverse=reverse)
            elif sort_type.lower() == "numeric":
                try:
                    unique_values.sort(key=lambda x: float(x), reverse=reverse)
                except ValueError:
                    raise ValueError("Numeric sorting failed: field contains non-numeric values.")

        return unique_values

    except requests.exceptions.RequestException as req_error:
        raise Exception(f"Network error occurred: {req_error}")
    except ValueError as val_error:
        raise ValueError(val_error)
    except Exception as gen_error:
        raise Exception(gen_error)


# =============================================================================
# QUERY HELPERS (BULK FIELD RETRIEVAL)
# =============================================================================
# get_multiple_fields():
#   - Retrieves a set of attributes for all features in a layer
#   - Returns a list of dicts (attribute name -> value)
# =============================================================================
def get_multiple_fields(url: str, layer: int = 0, fields: list = None) -> list:
    """
    Queries an ArcGIS REST API table layer to retrieve records with specified fields.

    Parameters:
        url: str
            Base URL of the ArcGIS REST API service.
        layer: int
            Layer ID to query (default 0).
        fields: list[str] | None
            Field names to request. When None, requests "*".

    Returns:
        list[dict]: Attribute dictionaries for each returned feature.
    """
    try:
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # If no fields provided, request all
        out_fields = ",".join(fields) if fields else "*"
        params = {
            "where": "1=1",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
            "token": token
        }

        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        results = []
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            # Directly use the returned attribute names as dictionary keys
            results.append({k: v for k, v in attributes.items()})

        return results

    except Exception as e:
        raise Exception(f"Error retrieving project records: {e}")


# =============================================================================
# QUERY HELPERS (SINGLE RECORD)
# =============================================================================
# select_record():
#   - Convenience wrapper for retrieving a single record by ID field/value
# =============================================================================
def select_record(url: str, layer: int, id_field: str, id_value: str, fields="*", return_geometry=False):
    """
    Queries an ArcGIS REST API table layer to retrieve a single record by ID field.

    Parameters:
        url: str
            Base URL of the ArcGIS REST API service.
        layer: int
            Layer ID to query.
        id_field: str
            Field name to filter by (e.g., 'GlobalID', 'ProposalId').
        id_value: str
            Value to match in the ID field.
        fields: str
            outFields string ("*" for all fields).
        return_geometry: bool
            Whether to include geometry in response.

    Returns:
        list: List of matching feature dictionaries (ArcGIS REST 'features').
    """
    try:
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        params = {
            "where": f"{id_field}='{id_value}'",
            "outFields": fields,
            "returnGeometry": str(return_geometry).lower(),
            "outSR": 4326,
            "f": "json",
            "token": token
        }

        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        return data.get("features", [])

    except Exception as e:
        raise Exception(f"Error retrieving project record: {e}")


# =============================================================================
# DELETE HELPERS
# =============================================================================
# delete_project():
#   - Calls deleteFeatures endpoint with a GlobalID where clause
#   - Used as a best-effort cleanup step when a multi-step upload fails
# =============================================================================
def delete_project(url: str, layer: int, globalid: str) -> bool:
    """
    Delete a project from an ArcGIS Feature Service using its GlobalID.

    This function calls the ArcGIS REST API `deleteFeatures` endpoint to remove
    a feature from the specified layer. It uses a `where` clause to match the
    provided GlobalID.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    try:
        # Retrieve authentication token
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # Parameters for the deleteFeatures request
        params = {
            "where": f"GlobalID='{globalid}'",  # Filter by GlobalID
            "f": "json",  # Response format
            "token": token  # Authentication token
        }

        # Construct deleteFeatures endpoint URL
        delete_url = f"{url}/{layer}/deleteFeatures"

        # Send POST request to ArcGIS REST API
        response = requests.post(delete_url, data=params)
        result = response.json()

        # Check response for deleteResults
        if "deleteResults" in result:
            success = all(r.get("success", False) for r in result["deleteResults"])
            return True
        else:
            print("Unexpected response:", result)
            return False

    except Exception as e:
        # Catch any errors (network, JSON parsing, etc.)
        print(f"Error deleting project: {e}")
        return False


# =============================================================================
# SPATIAL INTERSECT QUERY WRAPPER
# =============================================================================
# AGOLQueryIntersect:
#   - Builds an intersects query against a layer, given point/line/polygon input
#   - Supports running against multiple input geometries and merging results
# =============================================================================
class AGOLQueryIntersect:
    def __init__(self, url, layer, geometry, fields="*", return_geometry=False,
                 list_values=None, string_values=None):
        self.url = url
        self.layer = layer

        # NEW: allow single geometry OR list of geometries
        if isinstance(geometry, list) and len(geometry) > 0 and all(isinstance(g, list) for g in geometry):
            # geometry is a list of geometries
            self.geometry = [self._swap_coords(g) for g in geometry]
        else:
            # geometry is a single geometry
            self.geometry = [self._swap_coords(geometry)]

        self.fields = fields
        self.return_geometry = return_geometry
        self.list_values_field = list_values
        self.string_values_field = string_values
        self.token = self._authenticate()

        # NEW: run query for each geometry and merge results
        self.results = self._execute_query_multiple()

        # If list_values is provided, store unique values in a list
        self.list_values = []
        if self.list_values_field:
            self.list_values = self._extract_unique_values(self.list_values_field)

        # If string_values is provided, store unique values in a comma-separated string
        self.string_values = ""
        if self.string_values_field:
            unique_list = self._extract_unique_values(self.string_values_field)
            self.string_values = ",".join(map(str, unique_list))

    def _authenticate(self):
        """Authenticate with AGOL and return a valid token."""
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")
        return token

    def _swap_coords(self, geometry):
        """Swap coordinates from [lat, lon] to [lon, lat] if needed."""
        if isinstance(geometry, list):
            # Point
            if len(geometry) == 2 and all(isinstance(coord, (int, float)) for coord in geometry):
                return [geometry[1], geometry[0]]  # swap
            # Line or polygon
            elif all(isinstance(coord, list) and len(coord) == 2 for coord in geometry):
                return [[pt[1], pt[0]] for pt in geometry]  # swap each pair
        return geometry

    def _build_geometry(self, geometry):
        """
        Convert input geometry list into ArcGIS JSON geometry dict and geometryType.

        Supported:
            - Point: [lon, lat] (after swap)
            - Line : [[lon, lat], ...] (treated as polyline unless closed polygon)
            - Polygon: [[lon, lat], ...] closed or auto-closed

        Returns:
            (geometry_dict, geometry_type_str)
        """
        if not isinstance(geometry, list):
            raise ValueError("Invalid geometry: Geometry must be a list.")

        # POINT
        if (
            len(geometry) == 2
            and all(isinstance(coord, (int, float)) for coord in geometry)
        ):
            geometry_dict = {
                "x": geometry[0],
                "y": geometry[1],
                "spatialReference": {"wkid": 4326}
            }
            geometry_type_str = "esriGeometryPoint"
            return geometry_dict, geometry_type_str

        # LINE OR POLYGON
        if all(
            isinstance(coord, list)
            and len(coord) == 2
            and all(isinstance(val, (int, float)) for val in coord)
            for coord in geometry
        ):
            # If only 2 points → definitely a line
            if len(geometry) == 2:
                geometry_dict = {
                    "paths": [geometry],
                    "spatialReference": {"wkid": 4326}
                }
                geometry_type_str = "esriGeometryPolyline"
                return geometry_dict, geometry_type_str

            # POLYGON CHECK
            first = geometry[0]
            last = geometry[-1]

            # If user did NOT close the polygon, close it
            if first != last:
                ring = geometry + [first]
            else:
                ring = geometry

            # A polygon must have at least 4 points (3 unique + closure)
            if len(ring) >= 4:
                geometry_dict = {
                    "rings": [ring],
                    "spatialReference": {"wkid": 4326}
                }
                geometry_type_str = "esriGeometryPolygon"
                return geometry_dict, geometry_type_str

            # Fallback to polyline
            geometry_dict = {
                "paths": [geometry],
                "spatialReference": {"wkid": 4326}
            }
            geometry_type_str = "esriGeometryPolyline"
            return geometry_dict, geometry_type_str

    def _execute_query(self, geometry):
        geometry_dict, geometry_type_str = self._build_geometry(geometry)

        params = {
            "geometry": json.dumps(geometry_dict),
            "geometryType": geometry_type_str,
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "where": "1=1",
            "outFields": self.fields,
            "returnGeometry": self.return_geometry,
            "outSR": 4326,
            "f": "json",
            "token": self.token
        }

        query_url = f"{self.url}/{self.layer}/query"
        response = requests.get(query_url, params=params)
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        results = []
        requested_fields = [f.strip() for f in self.fields.split(",") if f.strip()]
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            filtered_attrs = {f: attributes.get(f) for f in requested_fields} if self.fields != "*" else attributes
            feature_package = {"attributes": filtered_attrs}
            if self.return_geometry:
                feature_package["geometry"] = feature.get("geometry", {})
            results.append(feature_package)

        return results

    # NEW: run query for each geometry and merge unique results
    def _execute_query_multiple(self):
        combined = []
        seen = set()
        for geom in self.geometry:
            result = self._execute_query(geom)
            for item in result:
                key = json.dumps(item["attributes"], sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    combined.append(item)
        return combined

    def _extract_unique_values(self, field_name):
        """Return a unique list of values for the specified field. Blank if no results."""
        if not self.results:
            return []  # no features returned

        available_fields = {f for feature in self.results for f in feature["attributes"].keys()}
        if field_name not in available_fields:
            return []  # gracefully return blank list if field not found

        values = [
            feature["attributes"].get(field_name)
            for feature in self.results
            if feature["attributes"].get(field_name) is not None
        ]
        return list(set(values))


# =============================================================================
# APPLYEDITS UPLOADER
# =============================================================================
# AGOLDataLoader:
#   - Wraps applyEdits adds for a specific service layer
#   - Returns a consistent {success, message, globalids} structure to callers
# =============================================================================
class AGOLDataLoader:
    def __init__(self, url: str, layer: int):
        """
        Initialize the loader with AGOL service URL and layer ID.

        Notes:
            - Token is retrieved via _authenticate().
            - Logger is configured at INFO level for visibility in app logs.
        """
        self.url = url.rstrip("/")
        self.layer = layer
        self.token = self._authenticate()
        self.success = False
        self.message = None
        self.globalids = []

        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("AGOLDataLoader")

    def _authenticate(self):
        """Authenticate with AGOL and return a valid token."""
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")
        return token

    def add_features(self, payload: dict):
        """
        Add features to the AGOL feature layer using applyEdits.

        Behavior:
            - POSTs to /applyEdits with adds payload JSON
            - Parses addResults for success/failure
            - Aggregates error messages when failures occur
            - Returns a consistent result dictionary

        Returns:
            dict: { "success": bool, "message": str, "globalids": list }
        """
        endpoint = f"{self.url}/{self.layer}/applyEdits"
        self.logger.info("Starting add_features process...")

        try:
            # Use data= and json.dumps for adds
            resp = requests.post(
                endpoint,
                data={
                    "f": "json",
                    "token": self.token,
                    "adds": json.dumps(payload["adds"])
                }
            )

            self.logger.info("Raw response text: %s", resp.text)
            result = resp.json()

            if "addResults" in result:
                add_results = result["addResults"]
                failures = [r for r in add_results if not r.get("success")]

                if failures:
                    self.success = False
                    error_messages = []
                    for r in failures:
                        err = r.get("error")
                        if err:
                            error_messages.append(
                                f"Code {err.get('code')}: {err.get('description')}"
                            )
                    self.message = (
                        f"Failed to add {len(failures)} feature(s). "
                        f"Errors: {', '.join(error_messages)}"
                    )
                    self.logger.error(self.message)
                else:
                    self.success = True
                    self.message = "All features added successfully."
                    self.globalids = [
                        r.get("globalId") for r in add_results if r.get("success")
                    ]
                    self.logger.info(self.message)

            else:
                self.success = False
                self.message = f"Unexpected response: {result}"
                self.logger.error(self.message)

        except Exception as e:
            self.success = False
            self.message = f"Error during add_features: {str(e)}"
            self.logger.exception(self.message)

        return {
            "success": self.success,
            "message": self.message,
            "globalids": self.globalids
        }
