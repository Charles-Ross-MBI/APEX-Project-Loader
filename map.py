"""
Utility functions for using Folium maps inside Streamlit apps.

This module provides a helper to add a compact geocoder search box
to a Folium map, styled with smaller width and font size.
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Search, Draw, Geocoder
import math


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
    """
    # Add geocoder control (collapsed, no marker on search result)
    Geocoder(collapsed=True, position=position, add_marker=False).add_to(fmap)

    # Inject CSS to style the geocoder input box
    fmap.get_root().html.add_child(folium.Element(f"""
    <style>
      .leaflet-control-geocoder-form input {{
          width: {width_px}px !important;
          font-size: {font_px}px !important;
      }}
    </style>
    """))



def set_bounds_point(points):
    """
    Compute a bounding box for:
      - A single point [lat, lon]
      - A list of points [[lat, lon], ...]
      - A list of point groups [[[lat, lon], ...], ...]

    Returns:
        [[min_lat, min_lon], [max_lat, max_lon]]
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
    """

    min_lat = float('inf')
    min_lon = float('inf')
    max_lat = float('-inf')
    max_lon = float('-inf')

    def process_point(pt):
        nonlocal min_lat, min_lon, max_lat, max_lon

        if (
            isinstance(pt, (list, tuple)) and
            len(pt) == 2
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
        ValueError if no valid coordinates are found.
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





def add_bottom_message(m, message: str):
    """
    Add a persistent bottom message bar to a Folium map.

    Parameters
    ----------
    m : folium.Map
        The map object to add the message to.
    message : str
        The text to display in the bottom message bar.
    """
    message_html = f"""
    <div style="
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background-color: rgba(0,0,0,0.7);
        color: white;
        padding: 8px 16px;
        border-radius: 6px;
        font-size: 14px;
        z-index:9999;">
        {message}
    </div>
    """
    m.get_root().html.add_child(folium.Element(message_html))






def set_zoom(bounds):
    """
    Compute an approximate zoom level from the bounds,
    using only the longitude span.
    
    Parameters:
      bounds: [[min_lat, min_lon], [max_lat, max_lon]]
    
    Returns:
      zoom: An approximate zoom level (integer)
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
    return the center point as [center_lat, center_lon].
    """

    if not bounds or len(bounds) != 2:
        raise ValueError("Bounds must be [[min_lat, min_lon], [max_lat, max_lon]].")

    min_lat, min_lon = bounds[0]
    max_lat, max_lon = bounds[1]

    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    return [center_lat, center_lon]

