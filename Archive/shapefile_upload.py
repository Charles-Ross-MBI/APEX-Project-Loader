"""
Utility for uploading and displaying shapefiles in a Streamlit app.

This module lets users upload zipped shapefiles containing point or polyline geometry.
It extracts the file, reads it with GeoPandas, and displays the geometry on
an interactive Folium map inside Streamlit, with a bottom message bar showing details.
"""

import streamlit as st
import tempfile
import zipfile
from streamlit_folium import st_folium
import folium
import geopandas as gpd
from map_util import add_small_geocoder, set_bounds_route, add_bottom_message, set_zoom


def point_shapefile():
    st.write("")
    st.markdown("<h5>Upload a Point Shapefile (ZIP)</h5>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload a zipped point shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"]
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
        st.markdown("<h5>Review Mapped Point</h5>", unsafe_allow_html=True)

        points = st.session_state.selected_point

        # Center map on first point
        first_lat, first_lon = points[0]
        m = folium.Map(location=[first_lat, first_lon], zoom_start=12)

        # Add all points as markers
        for lat, lon in points:
            folium.Marker(
                [lat, lon],
                icon=folium.Icon(color="blue"),
                tooltip="Uploaded Point"
            ).add_to(m)

        add_small_geocoder(m)
        st_folium(m, width=700, height=500)



def polyline_shapefile():
    st.write("")
    st.markdown("<h5>Upload a PolyLine Shapefile (ZIP)</h5>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload a zipped polyline shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"]
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
                    else:  # MultiLineString
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
        st.markdown("<h5>Review Mapped Route</h5>", unsafe_allow_html=True)

        routes = st.session_state["selected_route"]

        # Flatten all coordinates for bounds
        all_coords = [pt for line in routes for pt in line]
        bounds = set_bounds_route(all_coords)

        # Center map on first point of first line
        m = folium.Map(location=[all_coords[0][0], all_coords[0][1]], zoom_start=set_zoom(bounds))

        # Draw all polylines
        for coords in routes:
            folium.PolyLine(
                coords,
                color="#3388ff",
                weight=8,
                opacity=1
            ).add_to(m)

        add_small_geocoder(m)
        m.fit_bounds(set_bounds_route(bounds))

        st_folium(m, width=700, height=500)




def polygon_shapefile():
    st.write("")
    st.markdown("<h5>Upload a Polygon Shapefile (ZIP)</h5>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload a zipped polygon shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).",
        type=["zip"]
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
                    else:  # MultiPolygon
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
        st.markdown("<h5>Review Mapped Boundary</h5>", unsafe_allow_html=True)

        polygons = st.session_state["selected_boundary"]

        # Flatten all coordinates to compute bounds
        all_coords = [pt for poly in polygons for pt in poly]
        bounds = set_bounds_route(all_coords)

        # Center map on first coordinate of first polygon
        m = folium.Map(location=[all_coords[0][0], all_coords[0][1]], zoom_start=set_zoom(bounds))

        # Draw all polygons
        for coords in polygons:
            folium.Polygon(
                coords,
                color="#3388ff",
                weight=4,
                fill=True,
                fill_opacity=0.3
            ).add_to(m)

        add_small_geocoder(m)
        m.fit_bounds(set_bounds_route(bounds))

        st_folium(m, width=700, height=500)


