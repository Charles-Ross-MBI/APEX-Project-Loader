"""
Streamlit functions for drawing points and lines on a Folium map.

Users can interactively draw geometries, which are then stored
in Streamlit session state and displayed with success messages.
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw, Geocoder
from map import add_small_geocoder, set_bounds_route, set_zoom




def draw_point():
    """
    Display a Folium map where the user can draw a point.

    - Map centered on Alaska.
    - Only marker drawing tool enabled.
    - Captures last drawn point and saves to session state.
    - Previously saved point remains EDITABLE after rerender and matches Draw's default icon.
    """

    st.write("")
    st.markdown("<h5>Drop Point on a Map</h5>", unsafe_allow_html=True)
    st.write( "Use the map to drop a pin for your project location. Select the pin icon on the left, " "then click on the map to place it. You can zoom or search for a location using the " "search bar in the top-right corner.  If you need to override a previously saved point, drop the new point onto the map and the old one will be overwritten"  )

    # Create map centered on Alaska
    m = folium.Map(location=[64.0000, -152.0000], zoom_start=4)

    # FeatureGroup for drawn items
    drawn_items = folium.FeatureGroup(name="drawn_items").add_to(m)

    # ✅ Add stored point with the DEFAULT Leaflet icon (no custom icon specified)
    if st.session_state.get("selected_point"):
        lat, lon = st.session_state["selected_point"]
        folium.Marker(location=[lat, lon]).add_to(drawn_items)
        m.fit_bounds([[lat, lon]])

    # Add Draw control (no feature_group argument in folium>=0.17)
    draw = Draw(
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "rectangle": False,
            "circlemarker": False,
            "marker": True,
        },
        edit_options={
            "edit": True,
            "remove": True,
        }
    )
    draw.add_to(m)

    # Add geocoder control
    add_small_geocoder(m)

    # Render map in Streamlit
    output = st_folium(m, width=700, height=500, key="point_draw_map")

    # If a point was drawn or edited, save coordinates
    if output and "all_drawings" in output and output["all_drawings"]:
        points = [f for f in output["all_drawings"] if f.get("geometry", {}).get("type") == "Point"]
        if points:
            lon, lat = points[-1]["geometry"]["coordinates"]  # [lon, lat]
            st.session_state["selected_point"] = [round(lat, 6), round(lon, 6)]




def draw_line():
    """
    Display a Folium map where the user can draw a line.

    - Map centered on Alaska.
    - Only polyline drawing tool enabled.
    - Captures last drawn line and saves to session state.
    - Previously saved line remains EDITABLE after rerender and uses Draw's default style.
    """

    st.write("")
    st.markdown("<h5>Draw Route on a Map</h5>", unsafe_allow_html=True)
    st.write(
        "Use the map to draw your project route. Select the line tool on the left, "
        "then click along the map to trace the route. You can zoom or search for a location "
        "using the search bar in the top-right corner.  If you need to create a new route, draw the new route on the map and it will overwrite the old one."
    )


    # Create map centered on Alaska
    m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)

    # FeatureGroup for drawn items
    drawn_items = folium.FeatureGroup(name="drawn_items").add_to(m)

    # Restore previously saved route if present
    if st.session_state.get("selected_route"):
        route = st.session_state["selected_route"]
        bounds = set_bounds_route(route)
        folium.PolyLine(route).add_to(drawn_items)

        # --- swap (lat, lng) -> (lng, lat) before applying fit_bounds ---
        if m and bounds and len(bounds) == 2:
            m.zoom_start = set_zoom(bounds)
            # bounds expected shape: [[lat_min, lng_min], [lat_max, lng_max]]
            swapped_bounds = [
                [bounds[0][1], bounds[0][0]],  # [lng_min, lat_min]
                [bounds[1][1], bounds[1][0]]   # [lng_max, lat_max]
            ]
            m.fit_bounds(swapped_bounds)  # no explicit style -> default Draw style

    # Add Draw control (no feature_group argument in folium>=0.17)
    draw = Draw(
        draw_options={
            "polyline": True,     # allow drawing lines
            "polygon": False,
            "circle": False,
            "rectangle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={
            "edit": True,
            "remove": True,
        }
    )
    draw.add_to(m)

    # Add geocoder control
    add_small_geocoder(m)

    # Render map in Streamlit
    output = st_folium(m, width=700, height=500, key="line_draw_map")

    # If a line was drawn, save coordinates
    if output and "all_drawings" in output and output["all_drawings"]:
        # Find the last LineString feature returned
        lines = [f for f in output["all_drawings"] if f.get("geometry", {}).get("type") == "LineString"]
        if lines:
            coords = lines[-1]["geometry"]["coordinates"]  # list of [lon, lat]
            # ✅ Reformat to [lat, lon] pairs, rounded
            formatted = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
            st.session_state["selected_route"] = formatted

