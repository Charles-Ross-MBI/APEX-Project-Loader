import streamlit as st
from streamlit_folium import st_folium
import folium
from agol_util import get_multiple_fields
from agol_util import select_record
from map import add_small_geocoder



def aashtoware_point(lat: float, lon: float):
    st.write("")
    st.markdown("<h5>AASHTOWare Coordinates</h5>", unsafe_allow_html=True)
    st.write(
        "The coordinates below reflect the project’s location in the AASHTOWare database. "
        "If they are correct, you may continue. If not, please select another geospatial upload option."
    )

    
    # Two columns for lat and lon inputs
    cols = st.columns(2)
    with cols[0]:
        lat_val = st.number_input(
            "Latitude",
            value=float(lat),
            format="%.6f",
            key="awp_lat"
        )
    with cols[1]:
        lon_val = st.number_input(
            "Longitude",
            value=float(lon),
            format="%.6f",
            key="awp_lon"
        )

    # Create map centered on the coordinates
    m = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker([lat, lon], icon=folium.Icon(color="blue"), tooltip="Uploaded Point").add_to(m)
    add_small_geocoder(m)
    st_folium(m, width=700, height=500)
    
    # ✅ Update session_state if valid point
    if lat and lon:
        try:
            st.session_state["selected_point"] = [round(float(lat), 6), round(float(lon), 6)]
        except Exception:
            st.session_state["selected_point"] = None



def aashtoware_project():
    aashtoware = (
        "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/"
        "AWP_PROJECTS_EXPORT_XYTableToPoint_ExportFeatures/FeatureServer"
    )

    # Build <label> -> <GlobalID> mapping for the dropdown
    projects = get_multiple_fields(
        aashtoware, 0, ["Name", "ProposalId", "StateProjectNumber", "GlobalId"]
    )
    label_to_gid = {
        f"{p.get('StateProjectNumber', '')} – {p.get('Name', '')}": p.get("GlobalID")
        for p in projects
        if p.get("GlobalID")
    }

    # Sorted labels for a stable and deterministic order
    labels = sorted(label_to_gid.keys())

    # Insert a placeholder option at the top
    placeholder_label = "— Select a project —"
    labels = [placeholder_label] + labels

    # Versioned widget key so changing source/project forces a hard reset
    version = st.session_state.get("form_version", 0)
    widget_key = f"awp_project_select_{version}"

    # Determine initial index: if we have a previous label, use it; otherwise point to placeholder
    prev_label = st.session_state.get("aashto_label", None)
    if prev_label in labels:
        initial_index = labels.index(prev_label)
    else:
        initial_index = 0  # default to placeholder

    # --- on_change handler ---
    def _on_project_change():
        selected_label = st.session_state[widget_key]
        if selected_label == placeholder_label:
            # Reset session state if user chooses placeholder
            st.session_state["aashto_label"] = None
            st.session_state["aashto_id"] = None
            st.session_state["aashto_selected_project"] = None
            return

        selected_gid = label_to_gid.get(selected_label)
        prev_gid = st.session_state.get("aashto_id")

        st.session_state["aashto_label"] = selected_label
        st.session_state["aashto_id"] = selected_gid
        st.session_state["aashto_selected_project"] = selected_label

        if selected_gid and selected_gid != prev_gid:
            # Clear user-entered fields
            user_keys = [
                "construction_year", "new_continuing", "proj_name", "iris", "stip",
                "fed_proj_num", "fund_type", "proj_prac", "anticipated_start",
                "anticipated_end", "award_date", "award_fiscal_year", "contractor",
                "awarded_amount", "current_contract_amount", "amount_paid_to_date",
                "tenadd", "proj_desc", "proj_purp", "proj_impact", "proj_web",
                "apex_mapper_link", "apex_infosheet", "impact_comm"
            ]
            for k in user_keys:
                st.session_state[k] = "" if k not in ["award_date", "tenadd"] else None

            # Load full AWP record
            record = select_record(aashtoware, 0, "GlobalID", selected_gid)
            if record and "attributes" in record[0]:
                attrs = record[0]["attributes"]
                for k, v in attrs.items():
                    st.session_state[f"awp_{k.lower()}"] = v

            st.session_state["awp_selection_changed"] = True
            st.session_state["form_version"] = st.session_state.get("form_version", 0) + 1

    # Render selectbox
    st.selectbox(
        "AASHTOWare Project List",
        labels,
        index=initial_index,
        key=widget_key,
        on_change=_on_project_change,
    )




    