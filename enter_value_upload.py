import streamlit as st
from streamlit_folium import st_folium
import folium
from map import add_small_geocoder, add_bottom_message
from agol_util import get_unique_field_values


def enter_latlng():
    st.write("")
    st.markdown("<h5>Enter Latitude & Longitude Coordinates</h5>", unsafe_allow_html=True)

    # If a point already exists, use it as default values
    existing_point = st.session_state.get("selected_point")
    if existing_point:
        default_lat, default_lon = existing_point
    else:
        default_lat, default_lon = 0.0, 0.0

    # Two columns for lat/lon inputs with labels above
    cols = st.columns(2)
    with cols[0]:
        lat = st.number_input(
            "Latitude",
            value=default_lat,
            format="%.6f",
            key="manual_lat"
        )
    with cols[1]:
        lon = st.number_input(
            "Longitude",
            value=default_lon,
            format="%.6f",
            key="manual_lon"
        )

    # Only show map if both values are non-zero
    if lat != 0.0 and lon != 0.0:
        try:
            # ✅ Store consistently as [lat, lon]
            st.session_state.selected_point = [round(lat, 6), round(lon, 6)]

            st.write("")
            st.markdown("<h5>Review Mapped Point</h5>", unsafe_allow_html=True)

            m = folium.Map(location=[lat, lon], zoom_start=12)
            folium.Marker([lat, lon], icon=folium.Icon(color="blue"), tooltip="Uploaded Point").add_to(m)

            add_small_geocoder(m)

            st_folium(m, width=700, height=500)

        except ValueError:
            st.error("Please enter valid numeric values for latitude and longitude.")
    else:
        st.info("Enter both latitude and longitude to display the map.")


def enter_mileposts():
    st.write("")
    # Milepost AGOL Layer
    mileposts = 'https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AKDOT_Routes_Mileposts/FeatureServer'

    # Grab List of Route Names
    route_names = get_unique_field_values(
        url=mileposts,
        layer=1,
        field="Route_Name_Unique",
        sort_type='alpha',
        sort_order='asc'
    )

    # Create dropdown list for route selection (no default selected)
    route_name = st.selectbox("Route Name", route_names, index=None, placeholder="Select a route")

    if route_name is None:
        st.info("Please select a route before milepost options are available.")
    else:
        # Get milepost values for the selected route
        milepost_values = get_unique_field_values(
            url=mileposts,
            layer=1,
            field="Milepost_Number",
            where=f"Route_Name_Unique='{route_name}'",
            sort_type='numeric',
            sort_order='asc'
        )

        # Dropdowns for start and end mileposts (no default selected)
        col1, col2 = st.columns(2)

        with col1:
            start = st.selectbox("Start Milepost", milepost_values, index=None, placeholder="Select Start MP")
        with col2:
            end = st.selectbox("End Milepost", milepost_values, index=None, placeholder="Select End MP")

        if start is not None and end is not None:
            st.write('')
            st.write(f"MAP WITH LRS LINEAR ROUTE WILL APPEAR BELOW")