import streamlit as st
from streamlit_folium import st_folium
import folium
from map import add_small_geocoder, add_bottom_message
from agol_util import get_unique_field_values




def enter_latlng():
    # ----------------------------------------------------
    # Init state
    # ----------------------------------------------------
    if "manual_points_buffer" not in st.session_state:
        st.session_state.manual_points_buffer = []
    if "map_reset_counter" not in st.session_state:
        st.session_state.map_reset_counter = 0

    st.write("")
    st.markdown("<h5>Enter Latitude & Longitude Coordinates</h5>", unsafe_allow_html=True)
    st.write(
        "Enter coordinates and press **Add point**. Repeat as needed. "
        "Press **LOAD** to save your points. Press **CLEAR** to start over."
    )

    # ----------------------------------------------------
    # Normalize helper
    # ----------------------------------------------------
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

    # Default input from last existing point
    if existing_points:
        default_lat, default_lon = existing_points[-1]
    else:
        default_lat, default_lon = 0.0, 0.0

    # ----------------------------------------------------
    # Input fields
    # ----------------------------------------------------
    cols = st.columns(2)
    with cols[0]:
        lat = st.number_input("Latitude", value=float(default_lat), format="%.6f")

    with cols[1]:
        lon = st.number_input("Longitude", value=float(default_lon), format="%.6f")

    # ----------------------------------------------------
    # ADD POINT (full width below inputs)
    # ----------------------------------------------------
    if st.button("ADD POINT", use_container_width=True):
        if not -90 <= lat <= 90:
            st.error("Latitude must be between -90 and 90.")
        elif not -180 <= lon <= 180:
            st.error("Longitude must be between -180 and 180.")
        else:
            pt = [round(float(lat), 6), round(float(lon), 6)]
            st.session_state.manual_points_buffer.append(pt)
            st.rerun()

    # ----------------------------------------------------
    # Build map
    # ----------------------------------------------------
    m = folium.Map(location=[64.0, -152.0], zoom_start=4)

    saved_fg  = folium.FeatureGroup(name="Saved Points").add_to(m)
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

    st_folium(m, width=700, height=500, key=f"latlng_map_{st.session_state.map_reset_counter}")

    # ----------------------------------------------------
    # LOAD and CLEAR at bottom (like draw_point)
    # ----------------------------------------------------
    bottom = st.container()
    with bottom:
        c1, c2 = st.columns([1, 1])

        with c1:
            if st.button("LOAD", use_container_width=True):
                if st.session_state.manual_points_buffer:
                    st.session_state["selected_point"] = list(st.session_state.manual_points_buffer)
                    st.success(f"Loaded {len(st.session_state.manual_points_buffer)} point(s).")
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




def enter_mileposts():
    st.write("")
    # Milepost AGOL Layer
    mileposts = st.sessoin_state['mileposts']

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