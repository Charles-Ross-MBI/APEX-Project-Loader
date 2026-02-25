
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
import math

import streamlit as st
from streamlit_folium import st_folium
import folium
from shapely.geometry import LineString, Point

# Draw tools
from folium.plugins import Draw, Geocoder

# Shapefile tools
import geopandas as gpd

# RO Helper
from util.read_only_util import ro_widget
from util.input_util import fmt_string

# Map Tools
from util.map_util import (
    add_small_geocoder,
    set_bounds_point,
    set_bounds_route,
    set_bounds_boundary,
    set_zoom,
    geometry_to_folium
)

# Data helpers (milepoint entry)
from agol.agol_util import (
    get_unique_field_values, 
    query_routes_within_buffer)

# Data Helpers Create Buffer
from util.geospatial_util import create_buffers





# =============================================================================
# SECTION 1: DRAW-ON-MAP UPLOAD TOOLS (POINT / ROUTE / BOUNDARY)
# =============================================================================
# These functions allow users to interactively draw features on a Folium map.
# The drawn features are captured from st_folium output, but are only persisted
# to session_state when the user clicks LOAD. CLEAR wipes existing selections.
# =============================================================================

def draw_point(container):
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

    st.markdown("<h5>DROP POINT(S) ON MAP</h4>", unsafe_allow_html=True)
    st.caption(
        "Use the map to drop pins for your project. Select the pin icon on the left, "
        "then click on the map to place points. The points will only be saved when you press **LOAD**."
        " Hit the **CLEAR** button to clear any input points and add new ones"
    )

    # Create map centered on Alaska
    m = folium.Map(location=[64.0000, -152.0000], zoom_start=4)

    # Show previously saved points
    if st.session_state.get("footprint_submitted") and st.session_state.get("selected_point"):
        layer = geometry_to_folium(
            st.session_state['selected_point'],
            icon=folium.Icon(color="blue"),
            feature_type = 'point'
        )
        layer.add_to(m)

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
    map_key = f"point_draw_map_{st.session_state.get('map_reset_counter', 0)}"

    # ⛔️ Prevent reruns on pan/zoom:
    # Only return drawings; exclude bounds/zoom/center so panning/zooming doesn't trigger a rerun.
    # (You can include "last_clicked" if needed without re-enabling pan/zoom triggers.)
    output = st_folium(
        m,
        use_container_width=True,
        height=500,
        key=map_key,
        returned_objects=["all_drawings"],  # <--- this prevents pan/zoom-triggered reruns
    )

    # Extract ALL drawn points (but DO NOT save yet)
    latest_points = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            if f.get("geometry", {}).get("type") == "Point":
                lon, lat = f["geometry"]["coordinates"]
                latest_points.append([round(lon, 6), round(lat, 6)])

    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("LOAD", use_container_width=True, type='primary'):
                if latest_points:
                    st.session_state["selected_point"] = latest_points
        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_point"] = None
                st.session_state.map_reset_counter += 1
                st.rerun()



def draw_line(container):
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

    # Ensure a reset counter exists (consistent key)
    if "route_reset_counter" not in st.session_state:
        st.session_state.route_reset_counter = 0

    st.markdown("<h5>DRAW ROUTE(S) ON MAP</h4>", unsafe_allow_html=True)
    st.caption(
        "Use the map to sketch your project route. Select the line tool on the left, "
        "then click on the map to trace your path. You can draw as many lines as you need. "
        "Your routes are saved only when you press **LOAD**. Press **CLEAR** to remove all saved routes."
    )

    # Create map centered on Alaska
    m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)

    # Restore previously saved routes (each route is a list of [lon, lat] points)
    if st.session_state.get("footprint_submitted") and st.session_state.get("selected_route"):
        layer = geometry_to_folium(
            st.session_state['selected_route'],
            weight=4,
            feature_type = 'line'
        )
        layer.add_to(m)

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
    map_key = f"line_draw_map_{st.session_state.get('route_reset_counter', 0)}"

    # Prevent reruns on pan/zoom: only return drawings; exclude bounds/zoom/center
    output = st_folium(
        m,
        use_container_width=True,
        height=500,
        key=map_key,
        returned_objects=["all_drawings"],  # <-- pan/zoom won't trigger reruns
    )

    # Extract ALL drawn lines (but DO NOT save yet)
    latest_routes = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            geom = f.get("geometry", {})
            gtype = geom.get("type")
            if gtype == "LineString":
                # GeoJSON coordinates are [lon, lat]; keep storage as [lon, lat]
                coords = geom.get("coordinates", [])
                line_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in coords]
                if line_lonlat:
                    latest_routes.append(line_lonlat)
            elif gtype == "MultiLineString":
                # GeoJSON: list of LineStrings; each is list of [lon, lat]
                for line in geom.get("coordinates", []):
                    line_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in line]
                    if line_lonlat:
                        latest_routes.append(line_lonlat)

    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("LOAD", use_container_width=True, type='primary'):
                if latest_routes:
                    st.session_state["selected_route"] = latest_routes
        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_route"] = None
                st.session_state.route_reset_counter += 1
                st.rerun()



def draw_boundary(container):
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

    # Ensure a reset counter exists (mirrors other tools)
    if "route_reset_counter" not in st.session_state:
        st.session_state.route_reset_counter = 0

    st.markdown("<h5>DROP BOUNDARY(IES) ON MAP</h4>", unsafe_allow_html=True)
    st.caption(
        "Use the map to outline your project boundary. Select the polygon tool on the left, "
        "then click around the map to define your boundaries. You can draw multiple boundaries on the map. "
        "Your polygons are saved only when you press **LOAD**. Press **CLEAR** to remove all saved polygons."
    )

    # Create map centered on Alaska
    m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)

    # Restore previously saved polygons (each polygon is a list of [lon, lat] points)
    if st.session_state.get("footprint_submitted") and st.session_state.get("selected_boundary"):
        layer = geometry_to_folium(
            st.session_state['selected_boundary'],
            weight=4,
            fill=True,
            feature_type = 'polygon'
        )
        layer.add_to(m)

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
    # Use the reset counter in the key to force rerender after CLEAR
    map_key = f"polygon_draw_map_{st.session_state.get('route_reset_counter', 0)}"

    # Prevent reruns on pan/zoom:
    # Only return drawings; exclude bounds/zoom/center so panning/zooming doesn't trigger a rerun.
    output = st_folium(
        m,
        use_container_width=True,
        height=500,
        key=map_key,
        returned_objects=["all_drawings"],  # <-- stops reruns on pan/zoom while keeping drawing events
    )

    # Extract ALL drawn polygons (but DO NOT save yet)
    latest_boundaries = []
    if output and "all_drawings" in output and output["all_drawings"]:
        for f in output["all_drawings"]:
            geom = f.get("geometry", {})
            gtype = geom.get("type")
            if gtype == "Polygon":
                # GeoJSON polygon: coordinates[0] is outer ring -> list of [lon, lat]
                outer = geom.get("coordinates", [[]])[0]
                poly_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in outer]
                if poly_lonlat:
                    latest_boundaries.append(poly_lonlat)
            elif gtype == "MultiPolygon":
                # Each polygon: first ring is outer -> list of [lon, lat]
                for rings in geom.get("coordinates", []):
                    if rings and rings[0]:
                        outer = rings[0]
                        poly_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in outer]
                        if poly_lonlat:
                            latest_boundaries.append(poly_lonlat)

    # 50% width container for buttons
    button_container = st.container()
    with button_container:
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("LOAD", use_container_width=True, type='primary'):
                if latest_boundaries:
                    st.session_state["selected_boundary"] = latest_boundaries
        with col2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state["selected_boundary"] = None
                st.session_state.route_reset_counter += 1
                st.rerun()




# =============================================================================
# SECTION 2: MANUAL ENTRY UPLOAD TOOLS (LAT/LON, MILEPOINTS)
# =============================================================================
# These functions provide form-based alternatives to map drawing.
# NOTE: enter_milepoints() is currently a placeholder and depends on the presence
# of a milepoints layer reference in session_state.
# =============================================================================

def enter_latlng(container):
    """
    Manual point entry tool (lat/lon).

    Storage format:
        - Points are stored as [lon, lat]
        - Folium markers are displayed as [lat, lon]

    Behavior:
        - ADD POINT saves to manual_points_buffer as [lon, lat]
        - LOAD saves buffer into selected_point as [lon, lat]
        - CLEAR wipes everything
    """

    # -------------------------------------------------------------------------
    # Init state
    # -------------------------------------------------------------------------
    if "manual_points_buffer" not in st.session_state:
        st.session_state.manual_points_buffer = []
    if "map_reset_counter" not in st.session_state:
        st.session_state.map_reset_counter = 0

    st.markdown("###### Enter Latitude & Longitude Coordinates", unsafe_allow_html=True)
    st.caption(
        "Enter coordinates and press **Add point**. Repeat as needed. "
        "Press **LOAD** to save your points. Press **CLEAR** to start over."
    )

    # -------------------------------------------------------------------------
    # Existing saved points (ALWAYS [lon, lat])
    # -------------------------------------------------------------------------
    existing_points = st.session_state.get("selected_point") or []

    # Default inputs based on last saved point (convert [lon, lat] -> lat, lon)
    if existing_points:
        last_lon, last_lat = existing_points[-1]
        default_lat, default_lon = last_lat, last_lon
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
    # ADD POINT
    # -------------------------------------------------------------------------
    if st.button("ADD POINT", use_container_width=True):
        if not -90 <= lat <= 90:
            st.error("Latitude must be between -90 and 90.")
        elif not -180 <= lon <= 180:
            st.error("Longitude must be between -180 and 180.")
        else:
            # STORE AS [lon, lat]
            st.session_state.manual_points_buffer.append(
                [round(float(lon), 6), round(float(lat), 6)]
            )
            st.rerun()

    # -------------------------------------------------------------------------
    # Build map
    # -------------------------------------------------------------------------
    m = folium.Map(location=[64.0, -152.0], zoom_start=4)
    saved_fg = folium.FeatureGroup(name="Saved Points").add_to(m)
    buffer_fg = folium.FeatureGroup(name="Buffered Points").add_to(m)

    # -------------------------------------------------------------------------
    # Display saved points (green)
    # stored is [lon, lat] -> [lat, lon]
    # -------------------------------------------------------------------------
    for lo, la in existing_points:
        folium.Marker(
            [la, lo],
            icon=folium.Icon(color="green")
        ).add_to(saved_fg)

    # -------------------------------------------------------------------------
    # Display buffered points (blue)
    # stored is [lon, lat] -> [lat, lon]
    # -------------------------------------------------------------------------
    for lo, la in st.session_state.manual_points_buffer:
        folium.Marker(
            [la, lo],
            icon=folium.Icon(color="blue")
        ).add_to(buffer_fg)

    # -------------------------------------------------------------------------
    # Preview marker (not stored yet)
    # -------------------------------------------------------------------------
    preview_lonlat = [round(lon, 6), round(lat, 6)]
    if preview_lonlat not in st.session_state.manual_points_buffer and (lat != 0.0 or lon != 0.0):
        folium.CircleMarker(
            [lat, lon],   # Folium wants [lat, lon]
            radius=5,
            color="orange",
            fill=True,
            fill_opacity=0.7
        ).add_to(m)

    # -------------------------------------------------------------------------
    # Fit to bounds (storage is [lon, lat])
    # -------------------------------------------------------------------------
    all_pts = existing_points + st.session_state.manual_points_buffer
    if all_pts:
        min_lon = min(p[0] for p in all_pts)
        max_lon = max(p[0] for p in all_pts)
        min_lat = min(p[1] for p in all_pts)
        max_lat = max(p[1] for p in all_pts)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    add_small_geocoder(m)
    st_folium(
        m,
        use_container_width=True,
        height=500,
        key=f"latlng_map_{st.session_state.map_reset_counter}",
    )

    # -------------------------------------------------------------------------
    # LOAD and CLEAR
    # -------------------------------------------------------------------------
    bottom = st.container()
    with bottom:
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("LOAD", use_container_width=True, type='primary'):
                if st.session_state.manual_points_buffer:
                    # Save buffer as [lon, lat]
                    st.session_state["selected_point"] = list(st.session_state.manual_points_buffer)
                else:
                    st.info("No points to load.")
        with c2:
            if st.button("CLEAR", use_container_width=True):
                st.session_state.manual_points_buffer = []
                st.session_state["selected_point"] = None
                st.session_state.map_reset_counter += 1
                st.rerun()

    st.markdown("", unsafe_allow_html=True)




# =============================================================================
# SECTION 3: SHAPEFILE UPLOAD TOOLS (ZIP)
# =============================================================================
# These functions accept zipped shapefiles and read them using GeoPandas.
# Each upload mode validates expected geometry types and persists into the
# canonical session_state geometry keys.
# =============================================================================

def point_shapefile(container):
    """
    Upload and review a zipped point shapefile.

    Behavior:
        - Accepts a .zip containing required shapefile components (.shp, .shx, .dbf, .prj).
        - Reads features with GeoPandas.
        - Validates that only Point geometries are present.
        - Stores coordinates as [[lon, lat], ...] in:
            * st.session_state.selected_point
            * st.session_state.point_shapefile_uploaded = True

    Review:
        - If a shapefile was uploaded previously, renders a Folium map by passing the
          stored points through geometry_to_folium (as an ArcGIS-style Multipoint).
    """
    st.markdown("<h5>UPLOAD A POINT SHAPEFILE (ZIP)</h4>", unsafe_allow_html=True)
    st.caption(
        "Upload a zipped point shapefile (.zip) containing all required components "
        "(.shp, .shx, .dbf, and .prj). The file must contain Point geometry."
    )

    uploaded = st.file_uploader(
        "Upload shapefile containing all required files (.shp, .shx, .dbf, .prj).",
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

            # Reproject to WGS84 if possible (so we can safely store lon/lat)
            try:
                if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(4326)
            except Exception:
                # If CRS handling fails, proceed; coordinates assumed already lon/lat
                pass

            # Validate geometry type is strictly Point
            geom_types = set(gdf.geom_type.unique())
            if not geom_types.issubset({"Point"}):
                st.warning(f"Uploaded shapefile contains non-point geometries: {geom_types}.")
                st.session_state.point_shapefile_uploaded = False
            else:
                # Store ALL points as [lon, lat]
                all_points = []
                for geom in gdf.geometry:
                    # shapely Point -> (x, y) == (lon, lat)
                    x, y = float(geom.x), float(geom.y)
                    all_points.append([round(x, 6), round(y, 6)])

                st.session_state.selected_point = all_points
                st.session_state.point_shapefile_uploaded = True

    # --- If a point shapefile was uploaded earlier, display it via geometry_to_folium ---
    if st.session_state.get("point_shapefile_uploaded") and st.session_state.get("selected_point"):
        st.write("")
        st.markdown("###### Review Mapped Point(s)", unsafe_allow_html=True)

        points_lonlat = st.session_state.selected_point  # [[lon, lat], ...]

        # Build the Folium map, centered roughly on the first point
        if points_lonlat:
            first_lon, first_lat = points_lonlat[0]
            m = folium.Map(location=[first_lat, first_lon], zoom_start=11)
        else:
            m = folium.Map(location=[64.0, -152.0], zoom_start=4)

        # 🔹 Display using geometry_to_folium as ArcGIS-style Multipoint
        #     {"points": [[lon, lat], ...]} guarantees markers (not a polyline)
        try:
            multipoint_geom = {"points": points_lonlat}
            layer = geometry_to_folium(
                multipoint_geom, 
                icon=folium.Icon(color="blue"),
                feature_type = 'point')
            layer.add_to(m)
        except Exception as e:
            st.error(f"Failed to render uploaded points: {e}")
            return

        # Fit bounds to all points (stored in [lon, lat]; Folium expects [lat, lon])
        if points_lonlat:
            min_lon = min(p[0] for p in points_lonlat)
            max_lon = max(p[0] for p in points_lonlat)
            min_lat = min(p[1] for p in points_lonlat)
            max_lat = max(p[1] for p in points_lonlat)
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        add_small_geocoder(m)

        # Render the map as display-only (no reruns on pan/zoom)
        st_folium(
            m,
            use_container_width=True,
            height=500,
            returned_objects=[],  # don't send bounds/zoom/center back; avoids reruns on pan/zoom
        )


def polyline_shapefile(container):
    """
    Upload and review a zipped polyline shapefile.

    Behavior:
        - Accepts a .zip with LineString / MultiLineString geometries (including Z/M variants).
        - Flattens MultiLineString into individual LineString parts.
        - Stores coordinates in [lon, lat] ordering:
            * st.session_state.selected_route (list of polylines, each a list of [lon, lat])
            * st.session_state.route_shapefile_uploaded = True

    Review:
        - Renders a Folium map drawing all stored routes by passing them through
          geometry_to_folium using the ArcGIS-style {"paths": [...]} form.
    """
    st.markdown("<h5>UPLOAD A POLYLINE SHAPEFILE (ZIP)</h4>", unsafe_allow_html=True)

    st.caption(
        "Upload a zipped polyline shapefile (.zip) containing all required components "
        "(.shp, .shx, .dbf, and .prj). The file should represent one or more routes."
    )

    uploaded = st.file_uploader(
        "Upload shapefile containing all required files (.shp, .shx, .dbf, .prj).",
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

            # Reproject to WGS84 if needed (so we can safely store lon/lat)
            try:
                if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(4326)
            except Exception:
                # If CRS handling fails, proceed; assume coordinates are already lon/lat
                pass

            # ---- FIX: Accept LineString/MultiLineString, including Z/M variants ----
            # Normalize geometry types to their base (strip " Z", " M", etc.)
            geom_types_raw = set(gdf.geom_type.unique())
            geom_types = {str(t).split()[0] for t in geom_types_raw}  # e.g., "LineString Z" -> "LineString"

            valid_line_types = {"LineString", "MultiLineString"}
            if not geom_types.issubset(valid_line_types):
                st.warning(f"Uploaded shapefile contains non-line geometries: {geom_types_raw}.")
                st.session_state.route_shapefile_uploaded = False
            else:
                all_lines = []
                for geom in gdf.geometry:
                    # Normalize to a list of LineString parts
                    if geom.geom_type.startswith("MultiLineString"):
                        parts = list(geom.geoms)
                    else:
                        parts = [geom]

                    # Each part -> list of [lon, lat] (ignore Z/M if present)
                    for line in parts:
                        # shapely coords can be (x,y) or (x,y,z); use only x,y
                        line_lonlat = []
                        for c in line.coords:
                            x = float(c[0])
                            y = float(c[1])
                            line_lonlat.append([round(x, 6), round(y, 6)])
                        if line_lonlat:
                            all_lines.append(line_lonlat)

                # Store all polylines (each as list of [lon, lat])
                st.session_state.selected_route = all_lines
                st.session_state.route_shapefile_uploaded = True

    # --- If a polyline shapefile was uploaded earlier, display it ---
    if st.session_state.get("route_shapefile_uploaded") and st.session_state.get("selected_route"):
        st.write("")
        st.markdown("###### Review Mapped Route(s)", unsafe_allow_html=True)

        routes = st.session_state["selected_route"]  # list[list[[lon, lat], ...]]

        # Build map
        if routes and routes[0] and routes[0][0]:
            first_lon, first_lat = routes[0][0]
            m = folium.Map(location=[first_lat, first_lon], zoom_start=8)
        else:
            m = folium.Map(location=[64.0, -152.0], zoom_start=4)

        # Display via geometry_to_folium using ArcGIS-style {"paths": [...]}
        try:
            paths_geom = {"paths": routes}  # [lon, lat] arrays; geometry_to_folium swaps as needed for Folium
            layer = geometry_to_folium(
                paths_geom, 
                color="#3388ff", 
                weight=8, 
                opacity=1.0,
                feature_type = 'line')
            layer.add_to(m)
        except Exception as e:
            st.error(f"Failed to render uploaded polylines: {e}")
            return

        # Compute bounds over all vertices (stored as [lon, lat]) and fit map
        if routes:
            all_pts = [pt for line in routes for pt in line]  # flatten
            min_lon = min(p[0] for p in all_pts)
            max_lon = max(p[0] for p in all_pts)
            min_lat = min(p[1] for p in all_pts)
            max_lat = max(p[1] for p in all_pts)
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        add_small_geocoder(m)

        # Display-only review map: don't return bounds/zoom/center so pan/zoom doesn't rerun
        st_folium(
            m,
            use_container_width=True,
            height=500,
            returned_objects=[],  # prevents reruns on pan/zoom
        )


def polygon_shapefile(container):
    """
    Upload and review a zipped polygon shapefile.

    Behavior:
        - Accepts a .zip with Polygon / MultiPolygon geometries (including Z/M variants).
        - Flattens MultiPolygon into individual Polygon parts.
        - Stores ONLY exterior ring coordinates in [lon, lat] order:
            * st.session_state.selected_boundary (list of polygons, each a list[[lon, lat], ...])
            * st.session_state.boundary_shapefile_uploaded = True

    Review:
        - Renders a Folium map drawing all stored polygons by passing each through
          geometry_to_folium using the ArcGIS-style {"rings": [...]} form.
    """
    st.markdown("<h5>UPLOAD A POLYGON SHAPEFILE (ZIP)</h4>", unsafe_allow_html=True)

    st.caption(
        "Upload a zipped polygon shapefile (.zip) containing all required components "
        "(.shp, .shx, .dbf, and .prj). The file should represent the project boundary(ies)."
    )

    uploaded = st.file_uploader(
        "Upload shapefile containing all required files (.shp, .shx, .dbf, .prj).",
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

            # Reproject to WGS84 if needed (so we can safely store lon/lat)
            try:
                if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(4326)
            except Exception:
                # If CRS handling fails, proceed; assume coordinates are already lon/lat
                pass

            # ---- Validate geometry types (accept Polygon/MultiPolygon & Z/M variants) ----
            geom_types_raw = set(gdf.geom_type.unique())
            geom_types = {str(t).split()[0] for t in geom_types_raw}  # "Polygon Z" -> "Polygon"
            valid_poly_types = {"Polygon", "MultiPolygon"}

            if not geom_types.issubset(valid_poly_types):
                st.warning(f"Uploaded shapefile contains non-polygon geometries: {geom_types_raw}.")
                st.session_state.boundary_shapefile_uploaded = False
            else:
                all_polygons = []
                for geom in gdf.geometry:
                    # Normalize to list of Polygon parts
                    parts = list(geom.geoms) if geom.geom_type.startswith("MultiPolygon") else [geom]

                    for poly in parts:
                        # Use EXTERIOR ring only; coords may be (x,y) or (x,y,z) -> store [lon, lat]
                        ext = poly.exterior
                        if ext is None:
                            continue
                        ring_lonlat = []
                        for c in ext.coords:
                            x = float(c[0])
                            y = float(c[1])
                            ring_lonlat.append([round(x, 6), round(y, 6)])
                        if ring_lonlat:
                            all_polygons.append(ring_lonlat)

                # Store all polygons in session_state (each polygon is a list of [lon, lat])
                st.session_state.selected_boundary = all_polygons
                st.session_state.boundary_shapefile_uploaded = True

    # --- If a polygon shapefile was uploaded earlier, display it via geometry_to_folium ---
    if st.session_state.get("boundary_shapefile_uploaded") and st.session_state.get("selected_boundary"):
        st.write("")
        st.markdown("###### Review Mapped Boundary(ies)", unsafe_allow_html=True)

        polygons = st.session_state["selected_boundary"]  # list of polygons; each polygon is [[lon, lat], ...]

        # Build map (center on first polygon's first vertex if available)
        if polygons and polygons[0]:
            first_lon, first_lat = polygons[0][0]
            m = folium.Map(location=[first_lat, first_lon], zoom_start=9)
        else:
            m = folium.Map(location=[64.0, -152.0], zoom_start=4)

        # 🔹 Display polygons using geometry_to_folium
        # We’ll add one layer per polygon using ArcGIS-style {"rings": [ring]}
        try:
            fg = folium.FeatureGroup(name="Uploaded Polygons").add_to(m)
            for ring_lonlat in polygons:
                # Ensure ring is closed for proper polygon rendering (geometry_to_folium will also ensure closure)
                if ring_lonlat and ring_lonlat[0] != ring_lonlat[-1]:
                    ring_lonlat = ring_lonlat + [ring_lonlat[0]]
                gj_poly = {"rings": [ring_lonlat]}  # [lon, lat] as required for GeoJSON/ArcGIS
                layer = geometry_to_folium(
                    gj_poly,
                    color="#3388ff",
                    weight=4, 
                    fill=True, 
                    fill_opacity=0.3,
                    feature_type = 'polygon')
                layer.add_to(fg)
        except Exception as e:
            st.error(f"Failed to render uploaded polygons: {e}")
            return

        # Fit bounds from stored [lon, lat] coordinates
        if polygons:
            all_pts = [pt for poly in polygons for pt in poly]
            min_lon = min(p[0] for p in all_pts)
            max_lon = max(p[0] for p in all_pts)
            min_lat = min(p[1] for p in all_pts)
            max_lat = max(p[1] for p in all_pts)
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        add_small_geocoder(m)

        # Display-only review map: don't return bounds/zoom/center so pan/zoom doesn't rerun
        st_folium(
            m,
            use_container_width=True,
            height=500,
            returned_objects=[],  # prevents reruns on pan/zoom
        )


# =============================================================================
# SECTION 4: AASHTOWARE COORDINATES REVIEW (POINT)
# =============================================================================
# This helper displays and confirms AASHTOWare-provided coordinates. It also
# writes a canonical selected_point into session_state for downstream flows.
# =============================================================================
def aashtoware_point(points: dict, container):
    """
    Display AASHTOWare-provided midpoint(s) using geometry_to_folium.
    - Data is already in correct lon/lat format inside the package.
    - Always render midpoints using geometry_to_folium(feature_type='point')
    - Always store midpoints as [[lon, lat]] in session_state when there is exactly ONE.
    """

    target = container if container is not None else st
    with target:
        st.markdown("<h5>AASHTOWARE COORDINATES</h5>", unsafe_allow_html=True)
        st.caption(
            "The coordinates below reflect the project's midpoint(s) from AASHTOWare. "
            "If they are correct, continue. Otherwise update AASHTOWare or select another upload option."
        )

        # ---------------------------------------------------------
        # NO NORMALIZATION. PULL MIDPOINTS EXACTLY AS PROVIDED.
        # ---------------------------------------------------------
        mid_raw = points.get("Midpoint")

        # Always treat as list for mapping
        if isinstance(mid_raw, list):
            midpoints = mid_raw
        elif isinstance(mid_raw, dict):
            midpoints = [mid_raw]
        else:
            midpoints = []

        # Convert from dicts into canonical [[lon, lat]]
        midpoints_lonlat = [
            [mp["lon"], mp["lat"]]
            for mp in midpoints
            if isinstance(mp, dict) and "lon" in mp and "lat" in mp
        ]

        # ---------------------------------------------------------
        # UI SUMMARY
        # ---------------------------------------------------------
        if len(midpoints_lonlat) == 1:
            lon, lat = midpoints_lonlat[0]
            cols = st.columns(2)
            with cols[0]:
                ro_widget(key="awp_mid_lat", label="Latitude", value=lat)
            with cols[1]:
                ro_widget(key="awp_mid_lon", label="Longitude", value=lon)
        else:
            if midpoints_lonlat:
                rows = [
                    {"Type": f"Midpoint #{i}", "Latitude": lat, "Longitude": lon}
                    for i, (lon, lat) in enumerate(midpoints_lonlat, start=1)
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("No valid AASHTOWare midpoint found.")

        # ---------------------------------------------------------
        # MAP (geometry_to_folium ONLY)
        # ---------------------------------------------------------
        if midpoints_lonlat:
            first_latlon = [midpoints_lonlat[0][1], midpoints_lonlat[0][0]]
        else:
            first_latlon = [0.0, 0.0]

        m = folium.Map(location=first_latlon, zoom_start=12)

        for coords in midpoints_lonlat:
            geometry_to_folium(
                geom=[coords],                   # EXACT [lon, lat]
                feature_type="point",
                icon=folium.Icon(color="blue")
            ).add_to(m)

        if midpoints_lonlat:
            m.fit_bounds(set_bounds_point(midpoints_lonlat))

        st_folium(m, use_container_width=True, height=500)

        # ---------------------------------------------------------
        # SESSION — ALWAYS STORE IN LON/LAT
        # ---------------------------------------------------------
        if len(midpoints_lonlat) == 1:
            st.session_state["selected_point"] = [midpoints_lonlat[0]]
        else:
            st.session_state["selected_point"] = None




def aashtoware_path(awp: dict, container) -> None:
    """
    Place AASHTOWare BOP/EOP (and optional Midpoint) markers on a draw-enabled map.

    Input package (trusted as-is, no normalization):
      awp = {
        'BOP':      {'lat': <float>, 'lon': <float>} | [{'lat': <float>, 'lon': <float>}, ...],
        'EOP':      {'lat': <float>, 'lon': <float>} | [{'lat': <float>, 'lon': <float>}, ...],
        'Midpoint': {'lat': <float>, 'lon': <float>} | [{'lat': <float>, 'lon': <float>}, ...]  # optional
      }

    Behavior:
      - Renders ALL BOP (green), EOP (red), and Midpoint (blue) points via geometry_to_folium(feature_type='point').
      - Stores canonical lists in session_state (always [lon, lat]).
      - Draw-enabled map (polyline only); LOAD/CLEAR logic preserved.

    On LOAD:
      st.session_state["selected_route"] = [
          [[lon, lat], [lon, lat], ...],   # polyline 1
          ...
      ]
      And persists:
        - st.session_state["awp_bops_lonlat"] = [[lon, lat], ...]
        - st.session_state["awp_eops_lonlat"] = [[lon, lat], ...]
        - st.session_state["awp_midpoints_lonlat"] = [[lon, lat], ...]  # if present
        - st.session_state["awp_bop_eop_pairs"] = [{"bop":[lon,lat], "eop":[lon,lat]}, ...]

      Back-compat (exactly one bop and one eop):
        - st.session_state['project_bop'] = [lon, lat]
        - st.session_state['project_eop'] = [lon, lat]

    On CLEAR:
      st.session_state["selected_route"] = None
      st.session_state.route_reset_counter += 1
      st.rerun()
    """
    target = container if container is not None else st
    with target:
        st.markdown("<h5>AASHTOWARE COORDINATES</h5>", unsafe_allow_html=True)
        st.caption(
            "These coordinates reflect the project's begin (BOP), end (EOP), "
            "and optional midpoint from AASHTOWare. Draw the project route on the map below, then click LOAD."
        )

        # -----------------------------
        # Extract BOP/EOP/Midpoint as-is
        # -----------------------------
        def _as_list(obj):
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                return [obj]
            return []

        bops_in  = _as_list(awp.get('BOP'))
        eops_in  = _as_list(awp.get('EOP'))
        mids_in  = _as_list(awp.get('Midpoint'))

        # Canonical [lon, lat] (NO conversion/rounding; trust package)
        bops_lonlat = [[b['lon'], b['lat']] for b in bops_in if isinstance(b, dict) and 'lon' in b and 'lat' in b]
        eops_lonlat = [[e['lon'], e['lat']] for e in eops_in if isinstance(e, dict) and 'lon' in e and 'lat' in e]
        mids_lonlat = [[m['lon'], m['lat']] for m in mids_in if isinstance(m, dict) and 'lon' in m and 'lat' in m]

        # Pair list (zip to shortest)
        n_pairs = min(len(bops_lonlat), len(eops_lonlat))
        bop_eop_pairs = [{"bop": bops_lonlat[i], "eop": eops_lonlat[i]} for i in range(n_pairs)]

        # ---- Read-only summary ----
        single_pair = len(bops_lonlat) == 1 and len(eops_lonlat) == 1
        if single_pair:
            bop_lon, bop_lat = bops_lonlat[0]
            eop_lon, eop_lat = eops_lonlat[0]

            cols = st.columns(2)
            with cols[0]:
                ro_widget(key="awp_bop_lat", label="BOP Latitude", value=bop_lat)
            with cols[1]:
                ro_widget(key="awp_bop_lon", label="BOP Longitude", value=bop_lon)

            cols2 = st.columns(2)
            with cols2[0]:
                ro_widget(key="awp_eop_lat", label="EOP Latitude", value=eop_lat)
            with cols2[1]:
                ro_widget(key="awp_eop_lon", label="EOP Longitude", value=eop_lon)

            if mids_lonlat:
                mid_lon, mid_lat = mids_lonlat[0]
                st.caption(f"Midpoint: lat {mid_lat}, lon {mid_lon}")
        else:
            rows = []
            for idx, (lon, lat) in enumerate(bops_lonlat, start=1):
                rows.append({"Type": f"BOP #{idx}", "Latitude": lat, "Longitude": lon})
            for idx, (lon, lat) in enumerate(eops_lonlat, start=1):
                rows.append({"Type": f"EOP #{idx}", "Latitude": lat, "Longitude": lon})
            for idx, (lon, lat) in enumerate(mids_lonlat, start=1):
                rows.append({"Type": f"Midpoint #{idx}", "Latitude": lat, "Longitude": lon})
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)

        # Ensure reset counter exists
        st.session_state.setdefault("route_reset_counter", 0)

        # ---- Map with markers (geometry_to_folium ONLY) ----
        # Center = first available point → [lat, lon]
        if bops_lonlat:
            start_center = [bops_lonlat[0][1], bops_lonlat[0][0]]
        elif eops_lonlat:
            start_center = [eops_lonlat[0][1], eops_lonlat[0][0]]
        elif mids_lonlat:
            start_center = [mids_lonlat[0][1], mids_lonlat[0][0]]
        else:
            start_center = [0.0, 0.0]

        m = folium.Map(location=start_center, zoom_start=10)

        # Add ALL points via geometry_to_folium
        for coords in bops_lonlat:
            geometry_to_folium(
                geom=[coords],                  # canonical [lon, lat]
                feature_type='point',
                icon=folium.Icon(color="green")
            ).add_to(m)

        for coords in eops_lonlat:
            geometry_to_folium(
                geom=[coords],
                feature_type='point',
                icon=folium.Icon(color="red")
            ).add_to(m)

        for coords in mids_lonlat:
            geometry_to_folium(
                geom=[coords],
                feature_type='point',
                icon=folium.Icon(color="blue")
            ).add_to(m)

        # Fit bounds using canonical [lon, lat] lists
        all_lonlat = bops_lonlat + eops_lonlat + mids_lonlat
        if all_lonlat:
            m.fit_bounds(set_bounds_point(all_lonlat))

        # Enable drawing of polyline only
        Draw(
            export=False,
            position="topleft",
            draw_options={
                "polyline": True,
                "polygon": False,
                "rectangle": False,
                "circle": False,
                "circlemarker": False,
                "marker": False,
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(m)

        # Render and capture drawings
        output = st_folium(
            m,
            use_container_width=True,
            height=520,
            returned_objects=["all_drawings"]
        )

        # Extract all drawn lines (GeoJSON uses [lon, lat]); round only for drawn data
        latest_routes = []
        if output and "all_drawings" in output and output["all_drawings"]:
            for f in output["all_drawings"]:
                geom = f.get("geometry", {}) if isinstance(f, dict) else {}
                gtype = geom.get("type")

                if gtype == "LineString":
                    coords = geom.get("coordinates", []) or []
                    line_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in coords]
                    if line_lonlat:
                        latest_routes.append(line_lonlat)

                elif gtype == "MultiLineString":
                    for line in geom.get("coordinates", []) or []:
                        line_lonlat = [[round(lon, 6), round(lat, 6)] for lon, lat in line]
                        if line_lonlat:
                            latest_routes.append(line_lonlat)

        # ---- Persist AWP lists (canonical [lon, lat]) ----
        st.session_state["awp_bops_lonlat"] = bops_lonlat
        st.session_state["awp_eops_lonlat"] = eops_lonlat
        st.session_state["awp_midpoints_lonlat"] = mids_lonlat
        st.session_state["awp_bop_eop_pairs"] = bop_eop_pairs

        # Back-compat for single pair
        if len(bops_lonlat) == 1 and len(eops_lonlat) == 1:
            st.session_state['project_bop'] = bops_lonlat[0]
            st.session_state['project_eop'] = eops_lonlat[0]
        else:
            st.session_state.pop('project_bop', None)
            st.session_state.pop('project_eop', None)

        # ---- Buttons ----
        with st.container():
            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button("LOAD", use_container_width=True, type="primary"):
                    st.session_state["selected_route"] = latest_routes if latest_routes else None

            with col2:
                if st.button("CLEAR", use_container_width=True):
                    st.session_state["selected_route"] = None
                    st.session_state.route_reset_counter += 1
                    st.rerun()




def impact_area(container):
    """
    Display project geometries on a Folium map and allow the user to apply
    a buffer (meters) to create the Traffic Impact Area.

    Behavior:
    - Automatically computes buffers on first render (or when geometry changes) using the default/current distance.
    - Recomputes buffers when the distance input changes (on_change).

    NOTE:
    - Stored geometries in session are assumed to be in [lon, lat] order (WGS84).
    - All map drawing now uses geometry_to_folium, which expects [lon, lat] and handles styling + lat/lon conversion internally.
    """

    st.markdown("<h5>SET THE TRAFFIC IMPACT AREA</h5>", unsafe_allow_html=True)
    st.caption(
        "Examine the project geometry and refine the buffer distance as needed. "
        "Adjust the distance until the displayed buffer forms a realistic and appropriate impact area for the project."
    )

    with container:
        geoms = st.session_state.get("project_geom")

        if not geoms or not isinstance(geoms, (list, tuple)):
            st.warning("No project geometry found.")
            m = folium.Map(location=[63.5, -149.0], zoom_start=5)
            st_folium(m, use_container_width=True, height=500)
            return

        # Stored data is already [lon, lat]; keep as-is.
        # Normalize single point -> list of one point (NO ORDER SWAP)
        if (
            isinstance(geoms, (list, tuple))
            and len(geoms) == 2
            and all(isinstance(v, (int, float)) for v in geoms)
        ):
            geoms = [geoms]

        # --- Session defaults / scaffolding
        st.session_state.setdefault("tie_data", {})
        prev_params = st.session_state["tie_data"].get("impact_buffer_params", {})
        default_distance = float(prev_params.get("distance_m", 100.0))
        st.session_state.setdefault("impact_buffer_distance_m", default_distance)

        # --- Geometry fingerprint to detect changes (point/line/polygon)
        def _geom_fingerprint(g):
            try:
                norm = []
                for item in g:
                    if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                        # point [lon, lat]
                        norm.append((float(item[0]), float(item[1])))
                    elif (
                        isinstance(item, (list, tuple))
                        and item
                        and isinstance(item[0], (list, tuple))
                        and len(item[0]) == 2
                        and all(isinstance(v, (int, float)) for v in item[0])
                    ):
                        # line or polygon as [[lon, lat], ...]
                        norm.append(tuple((float(p[0]), float(p[1])) for p in item))
                    else:
                        norm.append(("UNK",))
                return hash(tuple(norm))
            except Exception:
                return None

        current_geom_fp = _geom_fingerprint(geoms)
        prev_geom_fp = st.session_state["tie_data"].get("impact_geom_fp")

        # --- Single place to compute buffers and write to session
        def _compute_and_save_buffers(distance_m: float):
            # Split geoms by kind — inputs are [lon, lat]
            points, lines, polys = [], [], []
            for item in geoms:
                if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                    # point [lon, lat]
                    points.append([float(item[0]), float(item[1])])
                elif (
                    isinstance(item, (list, tuple))
                    and item
                    and isinstance(item[0], (list, tuple))
                    and len(item[0]) == 2
                    and all(isinstance(v, (int, float)) for v in item[0])
                ):
                    coords = [[float(p[0]), float(p[1])] for p in item]  # [[lon, lat], ...]
                    is_closed = len(coords) >= 4 and coords[0] == coords[-1]
                    if is_closed:
                        polys.append(coords)
                    else:
                        lines.append(coords)

            buffers = []
            if distance_m > 0:
                # create_buffers is expected to accept [lon, lat] and return [lon, lat]
                if points:
                    buffers += create_buffers(geometry_list=points, geom_type="point",   distance_m=distance_m)
                if lines:
                    buffers += create_buffers(geometry_list=lines,  geom_type="line",    distance_m=distance_m)
                if polys:
                    buffers += create_buffers(geometry_list=polys,  geom_type="polygon", distance_m=distance_m)

            st.session_state["tie_data"]["impact_buffers"] = buffers
            st.session_state["tie_data"]["impact_buffer_params"] = {"distance_m": distance_m}
            st.session_state["tie_data"]["impact_geom_fp"] = current_geom_fp
            
            #Store Impacted Area Geometry
            st.session_state["selected_impact_area"] = buffers

        # --- Callback for the number_input (user interaction)
        def _on_distance_change():
            distance_m = float(st.session_state["impact_buffer_distance_m"])
            _compute_and_save_buffers(distance_m)

        # --- Distance input (this will NOT auto-trigger on first render)
        st.number_input(
            "Impact Area Dist (meters)",
            min_value=0.0,
            max_value=50000.0,
            step=50.0,
            key="impact_buffer_distance_m",
            on_change=_on_distance_change,
            help="Adjust the distance to refine the impact area around the project geometry.",
        )

        # --- Ensure buffers exist on first render or when geometry changed
        current_distance = float(st.session_state["impact_buffer_distance_m"])
        saved = st.session_state["tie_data"].get("impact_buffer_params", {})
        saved_distance = float(saved.get("distance_m", float("nan")))
        buffers_missing = "impact_buffers" not in st.session_state["tie_data"]
        geom_changed = (prev_geom_fp is None) or (prev_geom_fp != current_geom_fp)
        distance_mismatch = (saved_distance != saved_distance) or (abs(saved_distance - current_distance) > 1e-9)  # NaN-safe or drift

        if buffers_missing or geom_changed or distance_mismatch:
            _compute_and_save_buffers(current_distance)

        # ---------------------------
        # Map setup & drawing
        # ---------------------------
        m = folium.Map(location=[63.5, -149.0], zoom_start=5)
        all_lats, all_lons = [], []

        # Optional bound utilities
        set_bounds_point = None
        set_bounds_line = None
        set_bounds_polygon = None
        try:
            from util.geometry_util import set_bounds_point as _sbp
            set_bounds_point = _sbp
        except Exception:
            pass
        try:
            from util.geometry_util import set_bounds_line as _sbl
            set_bounds_line = _sbl
        except Exception:
            pass
        try:
            from util.geometry_util import set_bounds_polygon as _sbpoly
            set_bounds_polygon = _sbpoly
        except Exception:
            pass

        # Bounds helper for [lon, lat] sequences
        def _extend_global_bounds_from_lonlat(seq_lonlat):
            for lon, lat in seq_lonlat:
                all_lats.append(float(lat))
                all_lons.append(float(lon))

        # ---------------------------
        # Draw original geometry using geometry_to_folium
        # ---------------------------
        try:
            for item in geoms:
                # POINT: [lon, lat]
                if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                    lon, lat = float(item[0]), float(item[1])
                    # Use geometry_to_folium (expects [lon, lat]) — pass as single-element list
                    layer = geometry_to_folium(
                        [[lon, lat]],
                        tooltip="Project Point",
                        icon=folium.Icon(color="blue"),
                        feature_type = 'point'
                    )
                    layer.add_to(m)

                    # Bounds: helpers expect [lat, lon]; convert or fallback
                    if set_bounds_point:
                        try:
                            b = set_bounds_point([[lat, lon]])
                            _extend_global_bounds_from_lonlat([[b[0][1], b[0][0]], [b[1][1], b[1][0]]])  # convert back to lonlat for accumulation
                        except Exception:
                            _extend_global_bounds_from_lonlat([[lon, lat]])
                    else:
                        _extend_global_bounds_from_lonlat([[lon, lat]])

                # LINE or POLYGON: [[lon, lat], ...]
                elif (
                    isinstance(item, (list, tuple))
                    and item
                    and isinstance(item[0], (list, tuple))
                    and len(item[0]) == 2
                    and all(isinstance(v, (int, float)) for v in item[0])
                ):
                    coords_lonlat = [[float(p[0]), float(p[1])] for p in item]
                    is_closed = len(coords_lonlat) >= 4 and coords_lonlat[0] == coords_lonlat[-1]

                    if is_closed:
                        # Polygon styling via geometry_to_folium (GeoJSON)
                        layer = geometry_to_folium(
                            coords_lonlat,
                            color="orange",
                            weight=3,
                            fill=True,
                            fill_opacity=0.30,
                            feature_type = 'polygon'
                        )
                        layer.add_to(m)

                        # Bounds
                        if set_bounds_polygon:
                            try:
                                # helpers expect [lat, lon]
                                coords_latlon = [[c[1], c[0]] for c in coords_lonlat]
                                b = set_bounds_polygon(coords_latlon)
                                _extend_global_bounds_from_lonlat([[b[0][1], b[0][0]], [b[1][1], b[1][0]]])
                            except Exception:
                                _extend_global_bounds_from_lonlat(coords_lonlat)
                        else:
                            _extend_global_bounds_from_lonlat(coords_lonlat)
                    else:
                        # Polyline styling via geometry_to_folium
                        layer = geometry_to_folium(
                            coords_lonlat,
                            color="blue",
                            weight=4,
                            opacity=1.0,
                            feature_type = 'line'
                        )
                        layer.add_to(m)

                        # Bounds
                        if set_bounds_line:
                            try:
                                coords_latlon = [[c[1], c[0]] for c in coords_lonlat]
                                b = set_bounds_line(coords_latlon)
                                _extend_global_bounds_from_lonlat([[b[0][1], b[0][0]], [b[1][1], b[1][0]]])
                            except Exception:
                                _extend_global_bounds_from_lonlat(coords_lonlat)
                        else:
                            _extend_global_bounds_from_lonlat(coords_lonlat)
                else:
                    st.warning("Skipped an unrecognized geometry item.")
        except Exception as e:
            st.error(f"Unable to draw geometry: {e}")
            m = folium.Map(location=[63.5, -149.0], zoom_start=5)

        # ---------------------------
        # Draw buffers (already [lon, lat]) using geometry_to_folium
        # ---------------------------
        buffers = st.session_state.get("tie_data", {}).get("impact_buffers", []) or []
        for ring_lonlat in buffers:
            try:
                layer = geometry_to_folium(
                    ring_lonlat,
                    color="#e64a19",
                    weight=2,
                    fill=True,
                    fill_color="#ff7043",
                    fill_opacity=0.35,
                    feature_type = 'polygon'
                )
                layer.add_to(m)

                # Bounds for buffers
                if set_bounds_polygon:
                    try:
                        ring_latlon = [[c[1], c[0]] for c in ring_lonlat]
                        b = set_bounds_polygon(ring_latlon)
                        _extend_global_bounds_from_lonlat([[b[0][1], b[0][0]], [b[1][1], b[1][0]]])
                    except Exception:
                        _extend_global_bounds_from_lonlat(ring_lonlat)
                else:
                    _extend_global_bounds_from_lonlat(ring_lonlat)
            except Exception as e:
                st.warning(f"Skipped drawing a buffer ring due to error: {e}")

        # Fit bounds
        if all_lats and all_lons:
            bounds = [[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]]
            m.fit_bounds(bounds)

        st_folium(m, use_container_width=True, height=500)



def select_impacted_route(container):
    """
    Select the impacted route by clicking near it.

    Guarantees:
    - ALL geometries handled internally as [lon, lat].
    - ALL geometry displayed on the map uses geometry_to_folium.
    - Map always fits to the impact area (buffers) extent.
    - Saves selection to st.session_state["tie_data"]:
        - selected_route_id
        - selected_route_name
        - selected_route_geom  (raw lon/lat list, NOT GeoJSON)
    """
    import math

    # ---------------------------
    # REQUIRED HELPER 1 — Bounds
    # ---------------------------
    def _compute_bounds_from_rings(rings_latlon):
        """Return (min_lat, min_lon, max_lat, max_lon) for a list of rings in [lat, lon]."""
        min_lat = min_lon = float("inf")
        max_lat = max_lon = float("-inf")
        for ring in rings_latlon or []:
            for lat, lon in ring:
                latf, lonf = float(lat), float(lon)
                min_lat = min(min_lat, latf)
                min_lon = min(min_lon, lonf)
                max_lat = max(max_lat, latf)
                max_lon = max(max_lon, lonf)
        return (min_lat, min_lon, max_lat, max_lon)

    # -------------------------------------------------------------
    # REQUIRED HELPER 2 — Click‑to‑line distance (always lon/lat)
    # -------------------------------------------------------------
    def _line_distance_meters(click_lonlat, line_lonlat):
        """
        Distance from click to a polyline. Uses Shapely+PyProj if available (meters),
        otherwise an equirectangular approximation in meters. All geometry is [lon, lat].
        """
        try:
            from shapely.geometry import LineString, Point
            from shapely.ops import transform as shp_transform
            try:
                from pyproj import Transformer
                _to_merc = Transformer.from_crs(4326, 3857, always_xy=True).transform
            except Exception:
                _to_merc = None
        except Exception:
            LineString = None
            Point = None
            _to_merc = None

        lon, lat = click_lonlat

        if LineString and Point and _to_merc:
            ln_m = shp_transform(_to_merc, LineString(line_lonlat))
            pt_m = shp_transform(_to_merc, Point(lon, lat))
            return pt_m.distance(ln_m)

        # fallback
        deg_to_m_lat = 111_320.0
        deg_to_m_lon = 111_320.0 * math.cos(math.radians(lat))

        def _segdist(p, a, b):
            (x, y) = p
            (x1, y1) = a
            (x2, y2) = b
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                return math.hypot((x - x1) * deg_to_m_lon, (y - y1) * deg_to_m_lat)
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx*dx + dy*dy)))
            px = x1 + t * dx
            py = y1 + t * dy
            return math.hypot((x - px) * deg_to_m_lon, (y - py) * deg_to_m_lat)

        p = (lon, lat)
        best = float("inf")
        for i in range(len(line_lonlat) - 1):
            best = min(best, _segdist(p, line_lonlat[i], line_lonlat[i+1]))
        return best

    # ---------------------------
    # UI AND MAIN LOGIC
    # ---------------------------
    st.markdown("<h5>SELECT THE IMPACTED ROUTE</h4>", unsafe_allow_html=True)
    st.caption(
        "Using the impact area buffer, the app finds candidate routes. "
        "Click near a route on the map to select it and highlight in red. "
        "The map stays zoomed to the buffer extent."
    )

    with container:
        tie_data = st.session_state.setdefault("tie_data", {})
        buffers = tie_data.get("impact_buffers") or []   # list of rings, each [[lon,lat], ...]

        if not buffers:
            st.warning("No impact area buffer found. Please create a buffer in the previous step.")
            m = folium.Map(location=[63.5, -149], zoom_start=5)
            st_folium(m, use_container_width=True, height=500,
                      key="route_map", returned_objects=["last_clicked"])
            return

        # ------------------------------------------
        # 1) Query candidate routes (geometry = lon/lat)
        # ------------------------------------------
        try:
            results = query_routes_within_buffer(
                buffers,
                fields=("Route_ID", "Route_Name"),
                include_geometry=True
            ) or []
            tie_data["impact_route_candidates"] = results
        except Exception:
            results = tie_data.get("impact_route_candidates", []) or []

        id_field = "Route_ID"
        name_field = "Route_Name"

        id_to_name = {}
        id_to_geom = {}
        for r in results:
            attrs = r.get("attributes") or {}
            geom = r.get("geometry") or []   # ALWAYS [[lon,lat],...]
            rid = attrs.get(id_field)
            if rid and geom:
                id_to_name[rid] = attrs.get(name_field)
                id_to_geom[rid] = geom

        # ------------------------------------------
        # 2) CLICK HANDLING → nearest route selection
        # ------------------------------------------
        selected_id = tie_data.get("selected_route_id")
        map_state = st.session_state.get("route_map") or {}
        last_clicked = map_state.get("last_clicked")

        if last_clicked and id_to_geom:
            try:
                click_lat = float(last_clicked["lat"])
                click_lon = float(last_clicked["lng"])

                nearest_id = None
                nearest_dist = float("inf")

                for rid, geom in id_to_geom.items():
                    d = _line_distance_meters((click_lon, click_lat), geom)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest_id = rid

                # If within 100m → select it
                if nearest_id and nearest_dist <= 100:
                    if nearest_id != selected_id:
                        tie_data["selected_route_id"] = nearest_id
                        tie_data["selected_route_name"] = id_to_name.get(nearest_id)
                        tie_data["selected_route_geom"] = id_to_geom.get(nearest_id)  # raw lon/lat list
                        selected_id = nearest_id
                else:
                    tie_data["route_click_out_of_tolerance"] = True

            finally:
                # clear click event
                try:
                    st.session_state["route_map"]["last_clicked"] = None
                except Exception:
                    pass

        # ------------------------------------------
        # 3) Read‑only fields
        # ------------------------------------------
        col1, col2 = st.columns(2)
        with col1:
            ro_widget("route_id_ro", "Route ID",
                      fmt_string(tie_data.get("selected_route_id","")))
        with col2:
            ro_widget("route_name_ro", "Route Name",
                      fmt_string(tie_data.get("selected_route_name","")))

        # ------------------------------------------
        # 4) Build map and draw EVERYTHING via geometry_to_folium
        #    (All inputs to geometry_to_folium are lon/lat)
        # ------------------------------------------
        m = folium.Map(location=[63.5, -149], zoom_start=5, control_scale=True)

        # Draw buffers (impact area)
        for ring_lonlat in buffers:
            geometry_to_folium(
                ring_lonlat,    # lon/lat
                color="#e64a19",
                weight=2,
                fill=True,
                fill_color="#ff7043",
                fill_opacity=0.35,
                feature_type = 'polygon'
            ).add_to(m)

        # 👉 Fit to the IMPACT AREA ONLY (buffers)
        # Convert ring(s) lon/lat -> lat/lon for the bounds helper
        buffer_rings_latlon = []
        for ring_lonlat in buffers:
            buffer_rings_latlon.append([[lat, lon] for lon, lat in ring_lonlat])

        if buffer_rings_latlon:
            min_lat, min_lon, max_lat, max_lon = _compute_bounds_from_rings(buffer_rings_latlon)
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        # Draw route candidates (does NOT affect fit)
        for r in results:
            attrs = r.get("attributes") or {}
            rid = attrs.get(id_field)
            geom = r.get("geometry") or []

            if not rid or not geom:
                continue

            is_selected = (rid == selected_id)
            color = "#e53935" if is_selected else "#1976d2"
            weight = 6 if is_selected else 3

            tooltip_text = (
                f"Route ID: {attrs.get(id_field)}<br>"
                f"Route Name: {attrs.get(name_field)}"
            )

            geometry_to_folium(
                geom,       # lon/lat
                color=color,
                weight=weight,
                opacity=1.0 if is_selected else 0.6,
                tooltip=tooltip_text,
                feature_type = 'line'
            ).add_to(m)

        # render map
        st_folium(
            m,
            use_container_width=True,
            height=520,
            key="route_map",
            returned_objects=["last_clicked"],
        )

        if tie_data.get("route_click_out_of_tolerance"):
            st.info("Click closer to a route (within ~100m).")
            tie_data.pop("route_click_out_of_tolerance", None)



def select_route_endpoints(container):
    """
    Shows the buffer and ONLY the selected route (from select_impacted_route),
    then lets the user place a Start (green) and End (red) point snapped to that route.

    Contract:
      - All geometries are [lon, lat] internally.
      - Everything drawn on the map goes through geometry_to_folium.
      - Saves selection into st.session_state["tie_data"]:
          * selected_start_point
          * selected_end_point
        Each contains:
          {
            "lat": <float>, "lng": <float>,
            "lonlat": [lon, lat],
            "line_idx": int, "seg_idx": int, "t": float,
            "chainage_m": float
          }
    """
    import math

    st.markdown("<h5>DROP START & END POINTS FOR TRAFFIC IMPACT</h5>", unsafe_allow_html=True)
    st.caption(
        "Select the beginning and end points for the traffic impact. Choose either **Start Point** or **End Point**, "
        "then click on the map near the route—your point will automatically snap to the impacted line."
    )

    # ---------------------------
    # Helper: bounds (expects [lat, lon])
    # ---------------------------
    def _compute_bounds_from_rings(rings_latlon):
        """Return (min_lat, min_lon, max_lat, max_lon) for a list of rings in [lat, lon]."""
        min_lat = min_lon = float("inf")
        max_lat = max_lon = float("-inf")
        for ring in rings_latlon or []:
            for lat, lon in ring:
                latf, lonf = float(lat), float(lon)
                min_lat = min(min_lat, latf)
                min_lon = min(min_lon, lonf)
                max_lat = max(max_lat, latf)
                max_lon = max(max_lon, lonf)
        return (min_lat, min_lon, max_lat, max_lon)

    # ---------------------------
    # Distance / snapping helpers (lon/lat aware)
    # ---------------------------
    def _haversine_m_lonlat(lon1, lat1, lon2, lat2):
        """Great-circle distance between two points (lon/lat) in meters."""
        R = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    def _precompute_line_metrics_lonlat(lines_lonlat):
        """
        For each line-part (list of [lon, lat]), compute per-segment lengths and cumulative distances (meters).
        Returns: [{ 'lengths_m': [...], 'cum_m': [0, ...] }, ...]
        """
        metrics = []
        for line in lines_lonlat:
            lengths = []
            for i in range(len(line) - 1):
                lon1, lat1 = line[i]
                lon2, lat2 = line[i + 1]
                lengths.append(_haversine_m_lonlat(lon1, lat1, lon2, lat2))
            cum = [0.0]
            for L in lengths:
                cum.append(cum[-1] + L)
            metrics.append({"lengths_m": lengths, "cum_m": cum})
        return metrics

    def _project_to_segment_lonlat(px, py, ax, ay, bx, by):
        """
        Project point P(px,py) onto segment A(ax,ay)->B(bx,by) in lon/lat degrees (local Euclidean).
        Returns (t_clamped, proj_lon, proj_lat, euclid_dist_in_degrees).
        """
        dx, dy = (bx - ax), (by - ay)
        if dx == 0 and dy == 0:
            return 0.0, ax, ay, math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t_clamped = max(0.0, min(1.0, t))
        proj_lon = ax + t_clamped * dx
        proj_lat = ay + t_clamped * dy
        dist = math.hypot(px - proj_lon, py - proj_lat)
        return t_clamped, proj_lon, proj_lat, dist

    def _snap_to_route(clicked, lines_lonlat, metrics):
        """
        Snap clicked point to nearest point on any route part.
        Inputs:
          clicked: {'lat': <float>, 'lng': <float>}  (from st_folium)
          lines_lonlat: [ [[lon,lat], ...], ... ]
          metrics: output from _precompute_line_metrics_lonlat
        Returns:
          dict with lat/lng, lonlat, indices, t, chainage_m
        """
        cx, cy = float(clicked["lng"]), float(clicked["lat"])  # cx=lon, cy=lat

        best = {
            "euclid_dist": float("inf"),
            "line_idx": None,
            "seg_idx": None,
            "t": None,
            "proj_lon": None,
            "proj_lat": None,
            "chainage_m": None,
        }

        for li, line in enumerate(lines_lonlat):
            m = metrics[li]
            for si in range(len(line) - 1):
                ax, ay = line[si][0], line[si][1]       # lon, lat
                bx, by = line[si + 1][0], line[si + 1][1]
                t, proj_lon, proj_lat, e_dist = _project_to_segment_lonlat(cx, cy, ax, ay, bx, by)
                if e_dist < best["euclid_dist"]:
                    seg_len_m = m["lengths_m"][si] if m["lengths_m"] else 0.0
                    chainage = m["cum_m"][si] + seg_len_m * t
                    best.update({
                        "euclid_dist": e_dist,
                        "line_idx": li,
                        "seg_idx": si,
                        "t": t,
                        "proj_lon": proj_lon,
                        "proj_lat": proj_lat,
                        "chainage_m": chainage,
                    })

        return {
            "lat": best["proj_lat"],
            "lng": best["proj_lon"],
            "lonlat": [best["proj_lon"], best["proj_lat"]],
            "line_idx": best["line_idx"],
            "seg_idx": best["seg_idx"],
            "t": best["t"],
            "chainage_m": best["chainage_m"],
        }

    # -----------------------
    # Session & data
    # -----------------------
    with container:
        tie_data = st.session_state.setdefault("tie_data", {})
        buffers = tie_data.get("impact_buffers") or []                # list of rings [[lon,lat], ...]
        sel_route_geom = tie_data.get("selected_route_geom")          # [[lon,lat], ...]

        # Early exit: no buffer
        if not buffers:
            st.warning("No impact area buffer found. Please create a buffer in the previous step.")
            m = folium.Map(location=[63.5, -149.0], zoom_start=5)
            st_folium(m, use_container_width=True, height=520, key="route_snap_map",
                      returned_objects=["last_clicked"])
            return

        # Early exit: no route selected — show buffer only
        if not sel_route_geom:
            st.warning("No route selected. Please select a route in the previous step.")
            m = folium.Map(location=[63.5, -149.0], zoom_start=5, control_scale=True)
            for ring in buffers:
                geometry_to_folium(
                    ring,
                    color="#e64a19", weight=2, fill=True, fill_color="#ff7043", fill_opacity=0.35,
                    feature_type = 'polygon'
                ).add_to(m)
            # Fit to buffers
            buffer_rings_latlon = [ [ [lat, lon] for (lon, lat) in ring ] for ring in buffers ]
            min_lat, min_lon, max_lat, max_lon = _compute_bounds_from_rings(buffer_rings_latlon)
            if min_lat < float("inf"):
                m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
            st_folium(m, use_container_width=True, height=520, key="route_snap_map",
                      returned_objects=["last_clicked"])
            return

        # No normalizers; route is a single polyline in lon/lat
        lines_lonlat = [sel_route_geom]
        line_metrics = _precompute_line_metrics_lonlat(lines_lonlat)

        # ------------------------------------------------
        # 1) Segmented control (or radio fallback)
        # ------------------------------------------------
        try:
            placement_mode = st.segmented_control(
                "Choose a point to drop",
                options=["Start Point", "End Point"],
                default="Start Point",
                help="Clicks will move the selected endpoint, snapped to the route.",
                key="route_place_mode",
                width='stretch'
            )
        except Exception:
            placement_mode = st.radio(
                "Choose a point to drop",
                options=["Start Point", "End Point"],
                index=0,
                help="Clicks will move the selected endpoint, snapped to the route.",
                horizontal=True,
                key="route_place_mode_fallback"
            )

        # ------------------------------------------------
        # 2) Process click BEFORE drawing the map
        # ------------------------------------------------
        map_state_ss = st.session_state.get("route_snap_map") or {}
        last_clicked = (map_state_ss or {}).get("last_clicked")

        if last_clicked:
            try:
                snapped = _snap_to_route(last_clicked, lines_lonlat, line_metrics)

                # Write to the correct key ONLY based on the control
                if placement_mode == "Start Point":
                    tie_data["selected_start_point"] = snapped
                else:
                    tie_data["selected_end_point"] = snapped
            finally:
                # Consume click to avoid reprocessing on rerun
                try:
                    st.session_state["route_snap_map"]["last_clicked"] = None
                except Exception:
                    pass

        # ------------------------------------------------
        # Local copies for display (mirror, do NOT cross-assign)
        # ------------------------------------------------
        start_pt = tie_data.get("selected_start_point")
        st.session_state['selected_start_point'] = start_pt  # echo to top-level if you need it

        end_pt = tie_data.get("selected_end_point")
        st.session_state['selected_end_point'] = end_pt      # <-- fixed (no overwrite)

        # ------------------------------------------------
        # 3) Build & render map (everything via geometry_to_folium)
        # ------------------------------------------------
        m = folium.Map(location=[63.5, -149.0], zoom_start=5, control_scale=True)

        # Buffers (impact area)
        for ring in buffers:
            geometry_to_folium(
                ring,
                color="#e64a19",
                weight=2,
                fill=True,
                fill_color="#ff7043",
                fill_opacity=0.35,
                feature_type = 'polygon'
            ).add_to(m)

        # Fit to buffers only
        buffer_rings_latlon = [ [ [lat, lon] for (lon, lat) in ring ] for ring in buffers ]
        min_lat, min_lon, max_lat, max_lon = _compute_bounds_from_rings(buffer_rings_latlon)
        if min_lat < float("inf"):
            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

        # Selected route (single polyline)
        geometry_to_folium(
            sel_route_geom,
            color="#e53935",
            weight=6,
            opacity=1.0,
            feature_type = 'line'
        ).add_to(m)

        # Start/End markers
        if start_pt and isinstance(start_pt.get("lonlat"), list):
            geometry_to_folium(
                [start_pt["lonlat"]],  # [[lon, lat]] → marker
                icon=folium.Icon(color="green"),
                tooltip="Start point",
                feature_type = 'point'
            ).add_to(m)

        if end_pt and isinstance(end_pt.get("lonlat"), list):
            geometry_to_folium(
                [end_pt["lonlat"]],
                icon=folium.Icon(color="red"),
                tooltip="End point",
                feature_type = 'point'
            ).add_to(m)

        # Optional: remove Leaflet focus outlines
        try:
            from branca.element import Element
            css = Element("""
            <style>
              .leaflet-container a:focus,
              .leaflet-interactive:focus,
              .leaflet-overlay-pane svg path:focus,
              .leaflet-clickable:focus {
                outline: none !important; box-shadow: none !important;
              }
            </style>
            """)
            m.get_root().html.add_child(css)
        except Exception:
            pass

        _ = st_folium(
            m,
            use_container_width=True,
            height=520,
            key="route_snap_map",
            returned_objects=["last_clicked"],
        )