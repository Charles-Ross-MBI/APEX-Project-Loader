"""
Streamlit functions for drawing points and lines on a Folium map.

Users can interactively draw geometries, which are then stored
in Streamlit session state and displayed with success messages.
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw, Geocoder
from map import add_small_geocoder, set_bounds_point, set_bounds_route, set_bounds_boundary, set_zoom



def map_toolbar(top: int = 150, right: int = 40, 
                load_key: str = "load", clear_key: str = "clear"):
    """
    Renders a floating toolbar with LOAD and CLEAR buttons over a folium map.
    Returns: (load_clicked, clear_clicked)
    
    Parameters:
        top  - vertical offset (px) from top of viewport
        right - horizontal offset (px) from right of viewport
        load_key - unique Streamlit key for LOAD button
        clear_key - unique Streamlit key for CLEAR button
    """

    import streamlit as st

    # Inject CSS
    st.markdown(
        f"""
        <style>
          .map-toolbar-fixed-{load_key} {{
            position: fixed;
            top: {top}px;
            right: {right}px;
            z-index: 9999;
            background: #fff;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-shadow: 0 1px 5px rgba(0,0,0,0.65);
            padding: 6px;
          }}
          .map-toolbar-fixed-{load_key} [data-testid="stButton"] button {{
            font-size: 12px;
            padding: 4px 10px;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Render toolbar wrapper
    st.markdown(f'<div class="map-toolbar-fixed-{load_key}">', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        load_clicked = st.button("LOAD", key=f"btn_{load_key}")

    with col2:
        clear_clicked = st.button("CLEAR", key=f"btn_{clear_key}")

    st.markdown("</div>", unsafe_allow_html=True)

    return load_clicked, clear_clicked



def draw_point():
    
    if "map_reset_counter" not in st.session_state: 
        st.session_state.map_reset_counter = 0


    """
    Display a Folium map where the user can draw multiple points.
    Session state is ONLY updated when the user presses the LOAD button.
    """

    st.write("")
    st.markdown("<h5>Drop Points on a Map</h5>", unsafe_allow_html=True)
    st.write(
        "Use the map to drop pins for your project. Select the pin icon on the left, "
        "then click on the map to place points. The points will only be saved when you press **LOAD**."
        "  Hit the **CLEAR** button to clear any input points and add new ones"
    )

    # Create map centered on Alaska
    m = folium.Map(location=[64.0000, -152.0000], zoom_start=4)

    # FeatureGroup for drawn items
    drawn_items = folium.FeatureGroup(name="drawn_items").add_to(m)

    # Show previously saved points
    if st.session_state.get("selected_point"):
        for lat, lon in st.session_state["selected_point"]:
            folium.Marker(location=[lat, lon]).add_to(drawn_items)
        
        bounds = set_bounds_point(st.session_state["selected_point"])
        m.fit_bounds(bounds)
    

    # Draw control
    draw = Draw(
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "rectangle": False,
            "circlemarker": False,
            "marker": True,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)

    # Add geocoder
    add_small_geocoder(m)

   
    # Render map
    output = st_folium(m, width=700, height=500, key="point_draw_map")

    # Extract ALL drawn points (but DO NOT save yet)
    latest_points = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            if f.get("geometry", {}).get("type") == "Point":
                lon, lat = f["geometry"]["coordinates"]
                latest_points.append([round(lat, 6), round(lon, 6)])

    
    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("LOAD", use_container_width=True):
                if latest_points:
                    st.session_state["selected_point"] = latest_points

        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_point"] = []
                st.session_state.map_reset_counter += 1
                st.rerun()

    # Make the container only 50% width and centered
    st.markdown(
        """
        <style>
            .stContainer {
                width: 50% !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )







def draw_line():
    """
    Display a Folium map where the user can draw one or more routes (polylines).

    - Map centered on Alaska.
    - Only polyline drawing tool enabled.
    - Captures ALL drawn polylines and saves to session state on LOAD.
    - Previously saved polylines are re-added and remain EDITABLE after rerender.
    - CLEAR wipes saved polylines and reruns.
    """

    # Ensure a reset counter exists (same pattern as your other tools)
    if "route_reset_counter" not in st.session_state:
        st.session_state.route_reset_counter = 0

    st.write("")
    st.markdown("<h5>Draw Route on a Map</h5>", unsafe_allow_html=True)
    st.write(
        "Use the map to sketch your project route. Select the line tool on the left, "
        "then click on the map to trace your path. You can draw as many lines as you need. "
        "Your routes are saved only when you press **LOAD**. Press **CLEAR** to remove all saved routes."
    )


    # Create map centered on Alaska
    m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)

    # FeatureGroup for drawn items
    drawn_items = folium.FeatureGroup(name="drawn_items").add_to(m)

    # Restore previously saved routes (each route is a list of [lat, lon] points)
    if st.session_state.get("selected_route"):
        for line in st.session_state["selected_route"]:
            folium.PolyLine(locations=line).add_to(drawn_items)
        st.markdown(st.session_state["selected_route"])
        bounds = set_bounds_route(st.session_state["selected_route"])
        m.fit_bounds(bounds)

    # Draw control (polyline only)
    draw = Draw(
        draw_options={
            "polyline": True,
            "polygon": False,
            "circle": False,
            "rectangle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)

    # Add geocoder
    add_small_geocoder(m)

    # Render map (use reset counter in key to force rerender after CLEAR)
    output = st_folium(m, width=700, height=500, key=f"line_draw_map_{st.session_state.route_reset_counter}")

    # Extract ALL drawn lines (but DO NOT save yet)
    latest_routes = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            geom = f.get("geometry", {})
            gtype = geom.get("type")

            if gtype == "LineString":
                # GeoJSON: list of [lon, lat]
                coords = geom.get("coordinates", [])
                line_latlon = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
                if line_latlon:
                    latest_routes.append(line_latlon)

            elif gtype == "MultiLineString":
                # GeoJSON: list of LineStrings; each is list of [lon, lat]
                for line in geom.get("coordinates", []):
                    line_latlon = [[round(lat, 6), round(lon, 6)] for lon, lat in line]
                    if line_latlon:
                        latest_routes.append(line_latlon)

    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("LOAD", use_container_width=True):
                if latest_routes:
                    st.session_state["selected_route"] = latest_routes

        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_route"] = []
                st.session_state.map_reset_counter += 1
                st.rerun()

    # Make the container only 50% width and centered
    st.markdown(
        """
        <style>
            .stContainer {
                width: 50% !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )






def draw_boundary():
    """
    Display a Folium map where the user can draw one or more polygons.

    - Map centered on Alaska.
    - Only polygon drawing tool enabled.
    - Captures ALL drawn polygons and saves to session state on LOAD.
    - Previously saved polygons are re-added and remain EDITABLE after rerender.
    - CLEAR wipes saved polygons.
    """

    # Ensure a reset counter exists (mirrors draw_point)
    if "route_reset_counter" not in st.session_state:
        st.session_state.route_reset_counter = 0

    st.write("")
    st.markdown("<h5>Draw Boundary on a Map</h5>", unsafe_allow_html=True)
    st.write(
        "Use the map to outline your project boundary. Select the polygon tool on the left, "
        "then click around the map to define your boundaries. You can draw multiple boundaries on the map. "
        "Your polygons are saved only when you press **LOAD**. Press **CLEAR** to remove all saved polygons."
    )


    # Create map centered on Alaska
    m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)

    # FeatureGroup for drawn items
    drawn_items = folium.FeatureGroup(name="drawn_items").add_to(m)

    # Restore previously saved polygons (each polygon is a list of [lat, lon] points)
    if st.session_state.get("selected_boundary"):
        for poly in st.session_state["selected_boundary"]:
            folium.Polygon(locations=poly).add_to(drawn_items)

        bounds = set_bounds_boundary(st.session_state["selected_boundary"])
        m.fit_bounds(bounds)

    # Draw control (polygon only)
    draw = Draw(
        draw_options={
            "polyline": False,
            "polygon": True,
            "circle": False,
            "rectangle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)

    # Add geocoder control
    add_small_geocoder(m)

    # Render map in Streamlit
    output = st_folium(m, width=700, height=500, key="boundary_draw_map")

    # Extract ALL drawn polygons (but DO NOT save yet)
    latest_boundaries = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            geom = f.get("geometry", {})
            gtype = geom.get("type")
            if gtype == "Polygon":
                # GeoJSON polygon: coordinates[0] is outer ring -> list of [lon, lat]
                outer = geom["coordinates"][0]
                poly_latlon = [[round(lat, 6), round(lon, 6)] for lon, lat in outer]
                latest_boundaries.append(poly_latlon)

            elif gtype == "MultiPolygon":
                # Each polygon: first ring is outer -> list of [lon, lat]
                for rings in geom["coordinates"]:
                    outer = rings[0]
                    poly_latlon = [[round(lat, 6), round(lon, 6)] for lon, lat in outer]
                    latest_boundaries.append(poly_latlon)

    
    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("LOAD", use_container_width=True):
                if latest_boundaries:
                    st.session_state["selected_boundary"] = latest_boundaries

        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_boundary"] = []
                st.session_state.map_reset_counter += 1
                st.rerun()

    # Make the container only 50% width and centered
    st.markdown(
        """
        <style>
            .stContainer {
                width: 50% !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

