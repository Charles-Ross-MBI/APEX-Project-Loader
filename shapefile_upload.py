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
from map import add_small_geocoder, set_bounds_route, add_bottom_message, set_zoom


def point_shapefile():
    st.write("")
    st.markdown("<h5>Upload a Point Shapefile (ZIP)</h5>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload a zipped point shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).", type=["zip"])


    # ✅ If a new file is uploaded, process and store it
    if uploaded:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = f"{tmpdir}/shapefile.zip"
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            gdf = gpd.read_file(tmpdir)

            if gdf.geom_type.iloc[0] == "Point":
                coords = gdf.geometry.iloc[0].coords[0]
                lat, lon = coords[1], coords[0]

                # Store selected point in session state
                st.session_state.selected_point = [round(lat, 6), round(lon, 6)]
                st.session_state.point_shapefile_uploaded = True
            else:
                st.warning("Uploaded shapefile is not point geometry.")
                st.session_state.point_shapefile_uploaded = False

    # ✅ If a point shapefile was uploaded earlier, display it again
    if st.session_state.get("point_shapefile_uploaded") and st.session_state.get("selected_point"):
        st.write("")
        st.markdown("<h5>Review Mapped Point</h5>", unsafe_allow_html=True)
        lat, lon = st.session_state.selected_point
        m = folium.Map(location=[lat, lon], zoom_start=12)
        folium.Marker([lat, lon], icon=folium.Icon(color="blue"), tooltip="Uploaded Point").add_to(m)
        add_small_geocoder(m)
        st_folium(m, width=700, height=500)


def polyline_shapefile():
    st.write("")
    st.markdown("<h5>Upload a PolyLine Shapefile (ZIP)</h5>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload a zipped polyline shapefile containing all required files "
        "(.shp, .shx, .dbf, .prj).", type=["zip"])

    # ✅ If a new file is uploaded, process and store it
    if uploaded:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = f"{tmpdir}/shapefile.zip"
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            gdf = gpd.read_file(tmpdir)

            if gdf.geom_type.iloc[0] == "LineString":
                coords = list(gdf.geometry.iloc[0].coords)
                formatted = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
                st.session_state.selected_route = formatted
                st.session_state.route_shapefile_uploaded = True
            else:
                st.warning("Uploaded shapefile is not polyline geometry.")
                st.session_state.route_shapefile_uploaded = False

    # ✅ If a polyline shapefile was uploaded earlier, display it again
    if st.session_state.get("route_shapefile_uploaded") and st.session_state.get("selected_route"):
        #coords = [(lon, lat) for lat, lon in st.session_state.selected_route]
        st.write("")
        st.markdown("<h5>Review Mapped Route</h5>", unsafe_allow_html=True)
        coords = st.session_state['selected_route']
        bounds = set_bounds_route(coords)
        m = folium.Map(location=[coords[1][0], coords[1][0]], zoom_start=set_zoom(bounds))
        # ✅ Updated PolyLine symbology
        folium.PolyLine(
            coords,                # list of [lat, lon] pairs
            color="#3388ff",       # Leaflet default blue
            weight=8,              # line thickness
            opacity=1           # transparency
        ).add_to(m)
        add_small_geocoder(m)
        m.fit_bounds(set_bounds_route(bounds))
        st_folium(m, width=700, height=500)
