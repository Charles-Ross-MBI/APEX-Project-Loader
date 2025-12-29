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



def set_bounds_route(route):
    """
    Given a polyline geometry (a list of points in (lon, lat) order),
    compute the overall bounding box.

    Example input:
        [
            (-149.86787829444404, 61.19528554460584),
            (-149.86785784353071, 61.19902318902203),
            (-149.86785784353071, 61.203020631107904),
            ...
        ]
    
    Returns:
        A list in the format [[min_lat, min_lon], [max_lat, max_lon]].
        
    Raises:
        ValueError: If no valid coordinate data is found.
    """
    min_lat = float('inf')
    min_lon = float('inf')
    max_lat = float('-inf')
    max_lon = float('-inf')

    # Iterate directly over the list of (lon, lat) tuples
    for point in route:
        if isinstance(point, (list, tuple)) and len(point) == 2:
            lon, lat = point
        else:
            continue  # skip invalid entries

        # Update bounds
        if lat < min_lat:
            min_lat = lat
        if lat > max_lat:
            max_lat = lat
        if lon < min_lon:
            min_lon = lon
        if lon > max_lon:
            max_lon = lon

    # Validate that we found valid coordinates
    if min_lat == float('inf') or min_lon == float('inf') or \
       max_lat == float('-inf') or max_lon == float('-inf'):
        raise ValueError("No valid coordinate data found in the provided polyline.")

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
    return int(zoom)
