
"""
===============================================================================
GEOSPATIAL UPLOAD TOOLS (STREAMLIT) — DRAW / MANUAL ENTRY / SHAPEFILE
===============================================================================

Purpose:
    Consolidates Streamlit geospatial upload utilities used to capture project
    geometry in multiple ways:

      1) Draw geometries on a map (points, routes, boundaries)
      2) Enter values (lat/lon point entry; milepoint entry placeholder)
      3) Upload zipped shapefiles (points, polylines, polygons)
      4) Review AASHTOWare-provided coordinates (point)

Key behaviors:
    - Canonical geometry keys:
        All tools write to the same session_state keys expected downstream:
          * st.session_state['selected_point']    -> list[[lat, lon], ...]
          * st.session_state['selected_route']    -> list[list[[lat, lon], ...], ...]
          * st.session_state['selected_boundary'] -> list[list[[lat, lon], ...], ...]

    - “LOAD vs CLEAR” pattern:
        Drawing/manual-entry tools buffer user interactions and only persist to
        the canonical keys when the user presses LOAD. CLEAR wipes selection and
        forces a rerun.

    - Shapefile upload behavior:
        Reads zipped shapefiles with GeoPandas, validates geometry types per mode,
        converts coordinates into app-standard [lat, lon], and persists to the
        canonical session keys.

Session-state dependencies (expected at runtime):
    - Draw / manual entry:
        * 'selected_point', 'selected_route', 'selected_boundary'
        * 'map_reset_counter', 'route_reset_counter' (used to force rerender)
        * 'manual_points_buffer' (manual entry staging)

    - Milepoint entry:
        * 'milepoint' (FeatureServer URL or service reference)

    - Shapefile uploads:
        * 'point_shapefile_uploaded', 'route_shapefile_uploaded',
          'boundary_shapefile_uploaded' flags

Notes:
    - This module is a direct consolidation of earlier feature modules.
      Function logic is preserved; only organization and documentation are applied.
    - Coordinate conventions:
        * ArcGIS/Folium typically use [lat, lon] for location inputs
        * GeoJSON drawn output is [lon, lat] and is converted as needed

===============================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================
import tempfile
import zipfile

import streamlit as st
from streamlit_folium import st_folium
import folium

# Draw tools
from folium.plugins import Draw, Geocoder

# Shapefile tools
import geopandas as gpd

# RO Helper
from util.read_only_util import ro_widget

# Map Tools
from util.map_util import (
    add_small_geocoder,
    set_bounds_point,
    set_bounds_route,
    set_bounds_boundary,
    set_zoom,
    add_bottom_message,
)

# Data helpers (milepoint entry)
from agol.agol_util import get_unique_field_values, get_route_segment




# =============================================================================
# SECTION 1: DRAW-ON-MAP UPLOAD TOOLS (POINT / ROUTE / BOUNDARY)
# =============================================================================
# These functions allow users to interactively draw features on a Folium map.
# The drawn features are captured from st_folium output, but are only persisted
# to session_state when the user clicks LOAD. CLEAR wipes existing selections.
# =============================================================================

def draw_point():
    """
    Interactive point drawing tool.

    UI behavior:
        - Displays a Folium map where users can drop one or more points.
        - Previously saved points (session_state['selected_point']) are rendered.
        - Drawn points are captured from st_folium output but are only saved to
          session_state on LOAD.

    Side effects:
        - Updates st.session_state['selected_point'] on LOAD.
        - Clears st.session_state['selected_point'] on CLEAR.
        - Uses st.session_state['map_reset_counter'] to force rerender on CLEAR.
    """

    if "map_reset_counter" not in st.session_state:
        st.session_state.map_reset_counter = 0

    """ Display a Folium map where the user can draw multiple points.
    Session state is ONLY updated when the user presses the LOAD button.
    """

    st.write("")
    st.markdown(
        """
###### Drop Points on a Map
""",
        unsafe_allow_html=True,
    )

    st.write(
        "Use the map to drop pins for your project. Select the pin icon on the left, "
        "then click on the map to place points. The points will only be saved when you press **LOAD**."
        " Hit the **CLEAR** button to clear any input points and add new ones"
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
            if st.button("LOAD", use_container_width=True, type = 'primary'):
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
""",
        unsafe_allow_html=True,
    )


def draw_line():
    """
    Interactive route drawing tool (polylines).

    UI behavior:
        - Displays a Folium map where users can draw one or more routes.
        - Previously saved routes (session_state['selected_route']) are rendered.
        - Drawn lines are captured from st_folium output but only saved on LOAD.

    Side effects:
        - Updates st.session_state['selected_route'] on LOAD.
        - Clears st.session_state['selected_route'] on CLEAR.
        - Uses st.session_state['route_reset_counter'] to force rerender on CLEAR.
    """

    """ Display a Folium map where the user can draw one or more routes (polylines).
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
    st.markdown(
        """
###### Draw Route on a Map
""",
        unsafe_allow_html=True,
    )
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
    output = st_folium(
        m,
        width=700,
        height=500,
        key=f"line_draw_map_{st.session_state.route_reset_counter}",
    )

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
            if st.button("LOAD", use_container_width=True, type = 'primary'):
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
""",
        unsafe_allow_html=True,
    )


def draw_boundary():
    """
    Interactive boundary drawing tool (polygons).

    UI behavior:
        - Displays a Folium map where users can draw one or more polygons.
        - Previously saved boundaries (session_state['selected_boundary']) are rendered.
        - Drawn polygons are captured from st_folium output but only saved on LOAD.

    Side effects:
        - Updates st.session_state['selected_boundary'] on LOAD.
        - Clears st.session_state['selected_boundary'] on CLEAR.
        - Uses st.session_state['route_reset_counter'] (existing pattern) for reset.
    """

    """ Display a Folium map where the user can draw one or more polygons.
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
    st.markdown(
        """
###### Draw Boundary on a Map
""",
        unsafe_allow_html=True,
    )
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
            if st.button("LOAD", use_container_width=True, type = 'primary'):
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
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# SECTION 2: MANUAL ENTRY UPLOAD TOOLS (LAT/LON, MILEPOINTS)
# =============================================================================
# These functions provide form-based alternatives to map drawing.
# NOTE: enter_milepoints() is currently a placeholder and depends on the presence
# of a milepoints layer reference in session_state.
# =============================================================================

def enter_latlng():
    """
    Manual point entry tool (lat/lon).

    UI behavior:
        - User enters Latitude and Longitude values.
        - ADD POINT appends to a buffer (manual_points_buffer).
        - LOAD copies buffered points into session_state['selected_point'].
        - CLEAR wipes both buffer and selected_point.

    Notes:
        - A small preview marker is shown (orange) for the current input.
        - Saved points are shown in green; buffered points in blue.
    """

    # -------------------------------------------------------------------------
    # Init state
    # -------------------------------------------------------------------------
    if "manual_points_buffer" not in st.session_state:
        st.session_state.manual_points_buffer = []
    if "map_reset_counter" not in st.session_state:
        st.session_state.map_reset_counter = 0

    st.write("")
    st.markdown(
        """
###### Enter Latitude & Longitude Coordinates
""",
        unsafe_allow_html=True,
    )
    st.write(
        "Enter coordinates and press **Add point**. Repeat as needed. "
        "Press **LOAD** to save your points. Press **CLEAR** to start over."
    )

    # -------------------------------------------------------------------------
    # Normalize helper
    # -------------------------------------------------------------------------
    def normalize_points(p):
        out = []

        def extract(item):
            if isinstance(item, (list, tuple)):
                if len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                    out.append([float(item[0]), float(item[1])])
                else:
                    for sub in item:
                        extract(sub)

        extract(p)
        return out

    existing_points = normalize_points(st.session_state.get("selected_point"))

    # Default input from last existing point if existing
    if existing_points:
        default_lat, default_lon = existing_points[-1]
    else:
        default_lat, default_lon = 0.0, 0.0

    # -------------------------------------------------------------------------
    # Input fields
    # -------------------------------------------------------------------------
    cols = st.columns(2)
    with cols[0]:
        lat = st.number_input("Latitude", value=float(default_lat), format="%.6f")
    with cols[1]:
        lon = st.number_input("Longitude", value=float(default_lon), format="%.6f")

    # -------------------------------------------------------------------------
    # ADD POINT (full width below inputs)
    # -------------------------------------------------------------------------
    if st.button("ADD POINT", use_container_width=True):
        if not -90 <= lat <= 90:
            st.error("Latitude must be between -90 and 90.")
        elif not -180 <= lon <= 180:
            st.error("Longitude must be between -180 and 180.")
        else:
            pt = [round(float(lat), 6), round(float(lon), 6)]
            st.session_state.manual_points_buffer.append(pt)
            st.rerun()

    # -------------------------------------------------------------------------
    # Build map
    # -------------------------------------------------------------------------
    m = folium.Map(location=[64.0, -152.0], zoom_start=4)
    saved_fg = folium.FeatureGroup(name="Saved Points").add_to(m)
    buffer_fg = folium.FeatureGroup(name="Buffered Points").add_to(m)

    # Saved = green
    for la, lo in existing_points:
        folium.Marker(
            [la, lo],
            icon=folium.Icon(color="green"),
            tooltip=f"Saved: {la}, {lo}"
        ).add_to(saved_fg)

    # Buffered = blue
    for la, lo in st.session_state.manual_points_buffer:
        folium.Marker(
            [la, lo],
            icon=folium.Icon(color="blue"),
            tooltip=f"Buffered: {la}, {lo}"
        ).add_to(buffer_fg)

    # Preview = orange
    preview = [round(lat, 6), round(lon, 6)]
    if preview not in st.session_state.manual_points_buffer and (lat != 0.0 or lon != 0.0):
        folium.CircleMarker(
            [lat, lon],
            radius=5,
            color="orange",
            fill=True,
            fill_opacity=0.7,
            tooltip=f"Preview: {preview}"
        ).add_to(m)

    # Fit map to content
    all_pts = existing_points + st.session_state.manual_points_buffer
    if all_pts:
        min_lat = min(p[0] for p in all_pts)
        max_lat = max(p[0] for p in all_pts)
        min_lon = min(p[1] for p in all_pts)
        max_lon = max(p[1] for p in all_pts)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    add_small_geocoder(m)
    st_folium(
        m,
        width=700,
        height=500,
        key=f"latlng_map_{st.session_state.map_reset_counter}",
    )

    # -------------------------------------------------------------------------
    # LOAD and CLEAR at bottom (like draw_point)
    # -------------------------------------------------------------------------
    bottom = st.container()
    with bottom:
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("LOAD", use_container_width=True, type = 'primary'):
                if st.session_state.manual_points_buffer:
                    st.session_state["selected_point"] = list(st.session_state.manual_points_buffer)
                else:
                    st.info("No points to load.")
        with c2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state.manual_points_buffer = []
                st.session_state["selected_point"] = []
                st.session_state.map_reset_counter += 1
                st.rerun()

    # Same centering style
    st.markdown(
        """
""",
        unsafe_allow_html=True,
    )





def enter_milepoints():
    """
    Select a route and choose starting and ending milepoints to generate a route
    segment.

    Behaviors:
      - No map is rendered until Route Name, From MP, and To MP are selected.
      - 'To Milepoint' does not appear until 'From Milepoint' is selected.
      - Any change to Route Name / From MP / To MP invalidates downstream content by:
            st.session_state['selected_route'] = None
        (does NOT full-reset widgets like CLEAR does).
    """

    st.write("")
    st.markdown(
        "###### Generate Route Segment by Route Name & Milepoints",
        unsafe_allow_html=True,
    )

    st.write(
        "Select a route, then choose a starting and ending milepoint. "
        "Once all fields are selected, a preview of the route segment will appear. "
        "Press **LOAD** to save the geometry or **CLEAR** to reset."
    )

    # ---------------------------------------------------------
    # Session state initialization
    # ---------------------------------------------------------
    st.session_state.setdefault("milepoints_geometry_buffer", [])
    st.session_state.setdefault("milepoints_map_reset", 0)
    st.session_state.setdefault("milepoints_widget_reset", 0)

    st.session_state.setdefault("mp_route_name", None)
    st.session_state.setdefault("mp_from_mp", None)
    st.session_state.setdefault("mp_to_mp", None)

    # Ensure selected_route key exists; user wants it set to None to invalidate
    st.session_state.setdefault("selected_route", None)

    milepoints = st.session_state["milepoints"]
    reset_token = st.session_state.milepoints_widget_reset

    # ---------------------------------------------------------
    # Small helper: invalidate downstream content without full clear
    # ---------------------------------------------------------
    def _invalidate_selected_route():
        """
        Invalidate downstream content by clearing selected_route only.
        Also clears any in-progress preview buffer/map so stale visuals don't remain.
        """
        st.session_state["selected_route"] = None
        st.session_state.milepoints_geometry_buffer = []
        st.session_state.milepoints_map_reset += 1

    # ---------------------------------------------------------
    # Grab List of Route Names
    # ---------------------------------------------------------
    route_names = get_unique_field_values(
        url=milepoints,
        layer=0,
        field="ROUTE_NAME",
        sort_type="alpha",
        sort_order="asc",
    )

    # ---------------------------------------------------------
    # Route dropdown (keyed)
    # ---------------------------------------------------------
    def _on_route_change():
        """
        When route changes:
          - reset MPs
          - invalidate downstream content (selected_route=None)
          - clear preview buffer & bump map reset token
        """
        st.session_state.mp_from_mp = None
        st.session_state.mp_to_mp = None
        _invalidate_selected_route()

    route_name = st.selectbox(
        "Route Name",
        route_names,
        index=None,
        placeholder="Select a route",
        key=f"route_name_{reset_token}",
        on_change=_on_route_change,
    )
    st.session_state.mp_route_name = route_name

    # Gate: no MP widgets/map until route selected
    if route_name is None:
        st.info("Select a route to enable milepoints selection.")
        return

    # ---------------------------------------------------------
    # Milepoints values based on route
    # ---------------------------------------------------------
    safe_route = route_name.replace("'", "''")

    from_milepoint_values = get_unique_field_values(
        url=milepoints,
        layer=0,
        field="FROM_MPT",
        where=f"ROUTE_NAME='{safe_route}'",
        sort_type="numeric",
        sort_order="asc",
    )

    all_to_milepoint_values = get_unique_field_values(
        url=milepoints,
        layer=0,
        field="TO_MPT",
        where=f"ROUTE_NAME='{safe_route}'",
        sort_type="numeric",
        sort_order="asc",
    )

    # ---------------------------------------------------------
    # Milepoints dropdowns
    # ---------------------------------------------------------
    def _on_from_change():
        """
        When FROM changes:
          - reset TO
          - invalidate selected_route
        """
        st.session_state.mp_to_mp = None
        _invalidate_selected_route()

    def _on_to_change():
        """
        When TO changes:
          - invalidate selected_route
        """
        _invalidate_selected_route()

    col1, col2 = st.columns(2)

    with col1:
        from_mp = st.selectbox(
            "From Milepoint",
            from_milepoint_values,
            index=None,
            placeholder="Select Start MP",
            key=f"from_mp_{reset_token}",
            on_change=_on_from_change,
        )

    st.session_state.mp_from_mp = from_mp

    # NEW: hide To MP until From MP is selected
    if from_mp is None:
        st.info("Select a **From Milepoint** to enable **To Milepoint**.")
        return

    # Filter TO_MPT so it must be > FROM_MPT
    to_milepoint_values = [mp for mp in all_to_milepoint_values if mp > from_mp]

    with col2:
        to_mp = st.selectbox(
            "To Milepoint",
            to_milepoint_values,
            index=None,
            placeholder="Select End MP",
            key=f"to_mp_{reset_token}",
            on_change=_on_to_change,
        )

    st.session_state.mp_to_mp = to_mp

    # Gate: no map until all fields complete
    if to_mp is None:
        st.info("Select a **To Milepoint** to show the map preview.")
        return

    st.write("")
    
    # ---------------------------------------------------------
    # Get geometry path from AGOL
    # ---------------------------------------------------------
    geometry_path = get_route_segment(route_name, from_mp, to_mp) or []
    st.session_state.milepoints_geometry_buffer = geometry_path


    # ---------------------------------------------------------
    # Build Folium map (ONLY now)
    # ---------------------------------------------------------
    import folium
    from streamlit_folium import st_folium

    m = folium.Map(location=[64.0, -152.0], zoom_start=4)
    fg = folium.FeatureGroup(name="Milepoint Geometry").add_to(m)

    if geometry_path:
        folium.PolyLine(
            geometry_path,
            color="#3388ff",
            weight=8,
            opacity=1
        ).add_to(fg)

        lats = [p[0] for p in geometry_path]
        lons = [p[1] for p in geometry_path]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    else:
        st.warning("No route segment geometry returned for the selected milepoints.")

    add_small_geocoder(m)

    st_folium(
        m,
        width=700,
        height=500,
        key=f"milepoints_map_{st.session_state.milepoints_map_reset}",
    )

    # ---------------------------------------------------------
    # LOAD + CLEAR buttons
    # ---------------------------------------------------------
    def _clear_milepoints_tool_state():
        """
        Full clear: preview + saved geometry + all widget selections.
        """
        st.session_state.milepoints_geometry_buffer = []
        st.session_state["selected_route"] = None

        st.session_state.mp_route_name = None
        st.session_state.mp_from_mp = None
        st.session_state.mp_to_mp = None

        st.session_state.milepoints_widget_reset += 1
        st.session_state.milepoints_map_reset += 1

    bottom = st.container()
    with bottom:
        c1, c2 = st.columns([1, 1])

        # LOAD
        with c1:
            if st.button("LOAD", use_container_width=True, type="primary"):
                if st.session_state.milepoints_geometry_buffer:
                    st.session_state["selected_route"] = [
                        list(st.session_state.milepoints_geometry_buffer)
                    ]
                else:
                    st.info("No geometry to load.")

        # CLEAR
        with c2:
            if st.button("CLEAR", use_container_width=True):
                _clear_milepoints_tool_state()
                st.rerun()

    st.markdown("", unsafe_allow_html=True)





# =============================================================================
# SECTION 3: SHAPEFILE UPLOAD TOOLS (ZIP)
# =============================================================================
# These functions accept zipped shapefiles and read them using GeoPandas.
# Each upload mode validates expected geometry types and persists into the
# canonical session_state geometry keys.
# =============================================================================

def point_shapefile():
    """
    Upload and review a zipped point shapefile.

    Behavior:
        - Accepts a .zip containing required shapefile components (.shp, .shx,
          .dbf, .prj).
        - Reads features with GeoPandas.
        - Validates that only Point geometries are present.
        - Converts coordinates to [[lat, lon], ...] and writes to:
            * st.session_state.selected_point
            * st.session_state.point_shapefile_uploaded

    Review:
        - If a shapefile was uploaded previously, renders a Folium map showing
          all stored points.
    """
    st.write("")
    st.markdown(
        """
###### Upload a Point Shapefile (ZIP)
""",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Upload a zipped point shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"],
    )

    # --- If a new file is uploaded, process and store it ---
    if uploaded:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = f"{tmpdir}/shapefile.zip"
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            gdf = gpd.read_file(tmpdir)

            # Validate geometry type
            geom_types = set(gdf.geom_type.unique())
            if not geom_types.issubset({"Point"}):
                st.warning(f"Uploaded shapefile contains non-point geometries: {geom_types}.")
                st.session_state.point_shapefile_uploaded = False
            else:
                all_points = []
                for geom in gdf.geometry:
                    coords = geom.coords[0]
                    lat, lon = coords[1], coords[0]
                    all_points.append([round(lat, 6), round(lon, 6)])

                # Store all points
                st.session_state.selected_point = all_points
                st.session_state.point_shapefile_uploaded = True

    # --- If a point shapefile was uploaded earlier, display it ---
    if st.session_state.get("point_shapefile_uploaded") and st.session_state.get("selected_point"):
        st.write("")
        st.markdown(
            """
###### Review Mapped Point
""",
            unsafe_allow_html=True,
        )
        points = st.session_state.selected_point

        # Center map on first point
        first_lat, first_lon = points[0]
        m = folium.Map(location=[first_lat, first_lon], zoom_start=12)

        # Add all points as markers
        for lat, lon in points:
            folium.Marker(
                [lat, lon],
                icon=folium.Icon(color="blue"),
                tooltip="Uploaded Point",
            ).add_to(m)

        add_small_geocoder(m)
        st_folium(m, width=700, height=500)


def polyline_shapefile():
    """
    Upload and review a zipped polyline shapefile.

    Behavior:
        - Accepts a .zip with LineString / MultiLineString geometries.
        - Flattens MultiLineString into individual LineString parts.
        - Converts coordinates to [lat, lon] ordering and writes to:
            * st.session_state.selected_route (list of polylines)
            * st.session_state.route_shapefile_uploaded

    Review:
        - Renders a Folium map drawing all stored routes.
    """
    st.write("")
    st.markdown(
        """
###### Upload a PolyLine Shapefile (ZIP)
""",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Upload a zipped polyline shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"],
    )

    # --- If a new file is uploaded, process and store it ---
    if uploaded:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = f"{tmpdir}/shapefile.zip"

            # Save uploaded zip
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())

            # Extract contents
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            # Read shapefile
            gdf = gpd.read_file(tmpdir)

            # Validate geometry type
            geom_types = set(gdf.geom_type.unique())
            if not geom_types.issubset({"LineString", "MultiLineString"}):
                st.warning(f"Uploaded shapefile contains non-line geometries: {geom_types}.")
                st.session_state.route_shapefile_uploaded = False
            else:
                all_lines = []
                for geom in gdf.geometry:
                    if geom.geom_type == "LineString":
                        lines = [geom]
                    else:
                        # MultiLineString
                        lines = list(geom.geoms)

                    for line in lines:
                        coords = list(line.coords)
                        formatted = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
                        all_lines.append(formatted)

                # Store all polylines
                st.session_state.selected_route = all_lines
                st.session_state.route_shapefile_uploaded = True

    # --- If a polyline shapefile was uploaded earlier, display it ---
    if st.session_state.get("route_shapefile_uploaded") and st.session_state.get("selected_route"):
        st.write("")
        st.markdown(
            """
###### Review Mapped Route
""",
            unsafe_allow_html=True,
        )
        routes = st.session_state["selected_route"]

        # Flatten all coordinates for bounds
        all_coords = [pt for line in routes for pt in line]
        bounds = set_bounds_route(all_coords)

        # Center map on first point of first line
        m = folium.Map(
            location=[all_coords[0][0], all_coords[0][1]],
            zoom_start=set_zoom(bounds),
        )

        # Draw all polylines
        for coords in routes:
            folium.PolyLine(coords, color="#3388ff", weight=8, opacity=1).add_to(m)

        add_small_geocoder(m)
        m.fit_bounds(set_bounds_route(bounds))
        st_folium(m, width=700, height=500)


def polygon_shapefile():
    """
    Upload and review a zipped polygon shapefile.

    Behavior:
        - Accepts a .zip with Polygon / MultiPolygon geometries.
        - Flattens MultiPolygon into individual Polygon parts.
        - Uses exterior ring coordinates and converts to [lat, lon] ordering.
        - Writes to:
            * st.session_state.selected_boundary (list of polygons)
            * st.session_state.boundary_shapefile_uploaded

    Review:
        - Renders a Folium map drawing all stored polygons.
    """
    st.write("")
    st.markdown(
        """
###### Upload a Polygon Shapefile (ZIP)
""",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Upload a zipped polygon shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"],
    )

    # --- If a new file is uploaded, process and store it ---
    if uploaded:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = f"{tmpdir}/shapefile.zip"

            # Save uploaded zip
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())

            # Extract contents
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            # Read shapefile
            gdf = gpd.read_file(tmpdir)

            # Validate geometry type (allow Polygon and MultiPolygon)
            geom_types = set(gdf.geom_type.unique())
            if not geom_types.issubset({"Polygon", "MultiPolygon"}):
                st.warning(f"Uploaded shapefile contains non-polygon geometries: {geom_types}.")
                st.session_state.boundary_shapefile_uploaded = False
            else:
                all_polygons = []
                for geom in gdf.geometry:
                    if geom.geom_type == "Polygon":
                        polys = [geom]
                    else:
                        # MultiPolygon
                        polys = list(geom.geoms)

                    for poly in polys:
                        coords = list(poly.exterior.coords)
                        formatted = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
                        all_polygons.append(formatted)

                # Store all polygons in session_state
                st.session_state.selected_boundary = all_polygons
                st.session_state.boundary_shapefile_uploaded = True

    # --- If a polygon shapefile was uploaded earlier, display it ---
    if st.session_state.get("boundary_shapefile_uploaded") and st.session_state.get("selected_boundary"):
        st.write("")
        st.markdown(
            """
###### Review Mapped Boundary
""",
            unsafe_allow_html=True,
        )
        polygons = st.session_state["selected_boundary"]

        # Flatten all coordinates to compute bounds
        all_coords = [pt for poly in polygons for pt in poly]
        bounds = set_bounds_route(all_coords)

        # Center map on first coordinate of first polygon
        m = folium.Map(
            location=[all_coords[0][0], all_coords[0][1]],
            zoom_start=set_zoom(bounds),
        )

        # Draw all polygons
        for coords in polygons:
            folium.Polygon(
                coords,
                color="#3388ff",
                weight=4,
                fill=True,
                fill_opacity=0.3,
            ).add_to(m)

        add_small_geocoder(m)
        m.fit_bounds(set_bounds_route(bounds))
        st_folium(m, width=700, height=500)


# =============================================================================
# SECTION 4: AASHTOWARE COORDINATES REVIEW (POINT)
# =============================================================================
# This helper displays and confirms AASHTOWare-provided coordinates. It also
# writes a canonical selected_point into session_state for downstream flows.
# =============================================================================

def aashtoware_point(lat: float, lon: float):
    """
    Display AASHTOWare-provided coordinates and persist them as a point selection.

    Behavior:
        - Shows numeric inputs for latitude and longitude (pre-populated)
        - Renders a Folium map centered at the provided coordinates
        - Writes session_state['selected_point'] = [[lat, lon]] (rounded)

    Side effects:
        - Updates st.session_state['selected_point'] when lat/lon are valid.
        - On conversion errors, sets st.session_state['selected_point'] = None.
    """
    st.write("")
    st.markdown(
        """
###### AASHTOWare Coordinates
""",
        unsafe_allow_html=True
    )
    st.write(
        "The coordinates below reflect the project’s location in the AASHTOWare database. "
        "If they are correct, you may continue. If not, either correct the point in AASHTOWare or please select another upload option."
    )

    # Two columns for lat and lon inputs
    cols = st.columns(2)
    with cols[0]:
        ro_widget(
            key="awp_lat",
            label="Latitude",
            value=lat,
        )
    with cols[1]:
        ro_widget(
            key="awp_lng",
            label="Longitude",
            value=lon
        )

    # Create map centered on the coordinates
    m = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker(
        [lat, lon],
        icon=folium.Icon(color="blue"),
        tooltip="Uploaded Point"
    ).add_to(m)
    add_small_geocoder(m)
    st_folium(m, width=700, height=500)

    # ✅ Update session_state if valid point
    if lat and lon:
        try:
            st.session_state["selected_point"] = [[round(float(lat), 6), round(float(lon), 6)]]
        except Exception:
            st.session_state["selected_point"] = None



def aashtoware_path(mp: float, ep: float):
    pass