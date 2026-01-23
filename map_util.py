
"""
===============================================================================
MAP UTILITIES (STREAMLIT + FOLIUM) — BOUNDS, CENTERING, UI HELPERS
===============================================================================

Purpose:
    Utility helpers for rendering Folium maps inside Streamlit and for computing
    map view parameters (bounds, center, and approximate zoom). These helpers
    are used across multiple geospatial workflows to keep map behavior consistent.

Key behaviors:
    - UI controls:
        * add_small_geocoder(): adds a compact, collapsed geocoder search box.
        * add_bottom_message(): adds a persistent message bar at the bottom.
    - View calculations:
        * set_bounds_point(): bounds for points (supports nested input shapes).
        * set_bounds_route(): bounds for routes/polylines (recursive walker).
        * set_bounds_boundary(): bounds for polygons (supports multiple shapes).
        * set_center(): center point from bounds.
        * set_zoom(): rough zoom estimation based on longitude span.

Input conventions:
    - Coordinates throughout this module are treated as [lat, lon] ordering,
      unless otherwise noted. Output bounds are always:
        [[min_lat, min_lon], [max_lat, max_lon]]

Notes:
    - These helpers are intentionally defensive: they skip invalid points and
      raise ValueError if no valid coordinates are found.
    - Zoom calculation is approximate and uses only longitude span to avoid
      overfitting and expensive computations.

===============================================================================
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Search, Draw, Geocoder
import math


# =============================================================================
# UI ENHANCEMENTS (FOLIUM CONTROLS / OVERLAYS)
# =============================================================================
# These helpers inject Folium controls and HTML/CSS overlays to improve the user
# experience in Streamlit-hosted maps.
# =============================================================================

def add_small_geocoder(fmap, position: str = "topright", width_px: int = 120, font_px: int = 12):
    """
    Add a small, collapsed geocoder search box to a Folium map.

    Parameters
    ----------
    fmap : folium.Map
        The Folium map object to modify.
    position : str, default "topright"
        Where the geocoder control appears on the map.
    width_px : int, default 120
        Width of the input box in pixels.
    font_px : int, default 12
        Font size of the input text in pixels.

    Notes:
        - This is a UI affordance: it helps users pan/zoom to known places
          without adding permanent markers.
        - Styling is applied via injected CSS at the map HTML root.
    """
    # Add geocoder control (collapsed, no marker on search result)
    Geocoder(collapsed=True, position=position, add_marker=False).add_to(fmap)

    # Inject CSS to style the geocoder input box
    fmap.get_root().html.add_child(folium.Element(f"""
    """))


def add_bottom_message(m, message: str):
    """
    Add a persistent bottom message bar to a Folium map.

    Parameters
    ----------
    m : folium.Map
        The map object to add the message to.
    message : str
        The text to display in the bottom message bar.

    Why:
        This pattern is useful for showing user guidance or status messages
        directly on the map canvas without requiring extra Streamlit layout.
    """
    message_html = f"""
    {message}
    """
    m.get_root().html.add_child(folium.Element(message_html))


# =============================================================================
# BOUNDS CALCULATION HELPERS
# =============================================================================
# These helpers compute [[min_lat, min_lon], [max_lat, max_lon]] for different
# geometry shapes. They are designed to tolerate nested input structures.
# =============================================================================

def set_bounds_point(points):
    """
    Compute a bounding box for:
      - A single point [lat, lon]
      - A list of points [[lat, lon], ...]
      - A list of point groups [[[lat, lon], ...], ...]

    Returns:
        [[min_lat, min_lon], [max_lat, max_lon]]

    Raises:
        ValueError: if input is empty or contains no valid coordinates.

    Notes:
        - This function validates numeric types and basic lat/lon ranges.
        - Invalid entries are skipped rather than failing the whole operation.
    """
    min_lat = float('inf')
    min_lon = float('inf')
    max_lat = float('-inf')
    max_lon = float('-inf')

    def process_point(pt):
        nonlocal min_lat, min_lon, max_lat, max_lon
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
            return

        lat, lon = pt

        # Validate numeric
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            return

        # Validate ranges
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

    def process_group(group):
        for pt in group:
            process_point(pt)

    # --- Determine input type ---
    if not points:
        raise ValueError("Empty point input.")

    # Case 1: Single point
    if isinstance(points, (list, tuple)) and len(points) == 2 and \
            all(isinstance(x, (int, float)) for x in points):
        process_point(points)

    # Case 2: Flat list of points
    elif all(isinstance(x, (list, tuple)) and len(x) == 2 for x in points):
        process_group(points)

    # Case 3: List of point groups
    else:
        for group in points:
            if isinstance(group, (list, tuple)):
                process_group(group)

    # --- Validate ---
    if min_lat == float('inf'):
        raise ValueError("No valid coordinate data found.")

    return [[min_lat, min_lon], [max_lat, max_lon]]


def set_bounds_route(route):
    """
    Compute a bounding box for:
      - A single route (list of [lat, lon] pairs)
      - A list of routes
      - Any nested structure containing coordinate pairs

    Returns:
        [[min_lat, min_lon], [max_lat, max_lon]]

    Raises:
        ValueError: if route is empty or no valid coordinate data is found.

    Notes:
        - Uses a recursive walker to support arbitrary nesting depth.
        - Treats any 2-length numeric list/tuple as a coordinate pair.
    """
    min_lat = float('inf')
    min_lon = float('inf')
    max_lat = float('-inf')
    max_lon = float('-inf')

    def process_point(pt):
        nonlocal min_lat, min_lon, max_lat, max_lon
        if (
            isinstance(pt, (list, tuple)) and len(pt) == 2
        ):
            try:
                lat = float(pt[0])
                lon = float(pt[1])
            except (TypeError, ValueError):
                return
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)

    def walk(obj):
        """Recursively walk any nested structure."""
        if isinstance(obj, (list, tuple)):
            # If it's a coordinate pair, process it
            if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                process_point(obj)
            else:
                # Otherwise, recurse into children
                for item in obj:
                    walk(item)

    if not route:
        raise ValueError("Empty route input.")

    walk(route)

    if min_lat == float('inf'):
        raise ValueError("No valid coordinate data found.")

    return [[min_lat, min_lon], [max_lat, max_lon]]


def set_bounds_boundary(boundary):
    """
    Compute a bounding box for:
      - A single polygon (list of rings)
      - A list of polygons
      - A flat list of [lat, lon] coordinate pairs

    Returns:
        [[min_lat, min_lon], [max_lat, max_lon]]

    Raises:
        ValueError: if input is empty or no valid coordinates are found.

    Notes:
        - This function assumes coordinate order is [lat, lon].
        - It supports multiple polygons and rings (outer/inner).
    """
    min_lat = float('inf')
    min_lon = float('inf')
    max_lat = float('-inf')
    max_lon = float('-inf')

    def process_point(pt):
        nonlocal min_lat, min_lon, max_lat, max_lon
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
            return

        lat, lon = pt  # <-- FIXED: your data is [lat, lon]

        # Validate numeric
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            return

        # Update bounds
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

    def process_polygon(poly):
        # poly = [ring1, ring2, ...]
        for ring in poly:
            if isinstance(ring, (list, tuple)):
                for pt in ring:
                    process_point(pt)

    # --- Determine input type ---
    if not boundary:
        raise ValueError("Empty polygon input.")

    # Case 1: Flat list of coordinate pairs
    if all(isinstance(x, (list, tuple)) and len(x) == 2 for x in boundary):
        for pt in boundary:
            process_point(pt)

    # Case 2: Single polygon (list of rings)
    elif all(isinstance(ring, (list, tuple)) for ring in boundary) and \
            any(isinstance(ring[0], (list, tuple)) for ring in boundary):
        process_polygon(boundary)

    # Case 3: List of polygons
    else:
        for poly in boundary:
            if isinstance(poly, (list, tuple)):
                process_polygon(poly)

    # --- Validate ---
    if min_lat == float('inf'):
        raise ValueError("No valid coordinate data found.")

    return [[min_lat, min_lon], [max_lat, max_lon]]


# =============================================================================
# VIEW HELPERS (CENTER + ZOOM)
# =============================================================================
# These helpers compute a usable map center and a rough zoom level from bounds.
# They are intentionally simple and predictable for consistent UX.
# =============================================================================

def set_zoom(bounds):
    """
    Compute an approximate zoom level from the bounds, using only the longitude span.

    Parameters:
        bounds: [[min_lat, min_lon], [max_lat, max_lon]]

    Returns:
        zoom: An approximate zoom level (integer)

    Notes:
        - Uses a log-based estimate: log2(360 / delta_lon), then adjusts down.
        - If delta_lon is 0, returns 0 to avoid division by zero.
    """
    min_lat, min_lon = bounds[0]
    max_lat, max_lon = bounds[1]
    delta_lon = abs(max_lon - min_lon)
    if delta_lon == 0:
        return 0  # Avoid division by zero; return a default zoom.
    zoom = math.log(360 / delta_lon, 2)
    zoom = zoom-1
    return int(zoom)


def set_center(bounds):
    """
    Given bounds in the format:
        [[min_lat, min_lon], [max_lat, max_lon]]

    Return the center point as:
        [center_lat, center_lon]

    Raises:
        ValueError: if bounds is not in the expected format.
    """
    if not bounds or len(bounds) != 2:
        raise ValueError("Bounds must be [[min_lat, min_lon], [max_lat, max_lon]].")
    min_lat, min_lon = bounds[0]
    max_lat, max_lon = bounds[1]
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    return [center_lat, center_lon]
