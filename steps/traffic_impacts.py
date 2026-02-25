import streamlit as st
from util.geometry_util import (
    impact_area,
    select_impacted_route,
    select_route_endpoints
)
import json


def add_traffic_impact():
    """
    Streamlit UI entrypoint for Traffic Impact Event selection.

    This orchestrates three steps and always shows a SUBMIT button.
    On submit, validates the presence of:
      - selected_impact_area
      - selected_route_geom
      - selected_start_point
      - selected_end_point

    Behavior:
      - The submit button is always visible.
      - If clicked and any of the four required values are missing, show errors
        and do not submit.
      - If clicked and all values are present, save to project_* keys and show
        a ✅ state.
      - If any of those four values change post-submit, the button resets and
        is available for another submission.
    """

    # ----------------------------------------
    # Persistent State
    # ----------------------------------------
    st.session_state.setdefault("traffic_impact_answer", None)
    st.session_state.setdefault("traffic_impact_step", "Set Impact Area")
    st.session_state.setdefault("traffic_impact_submitted", False)
    st.session_state.setdefault("just_submitted_traffic_impact", False)
    st.session_state.setdefault("submitted_traffic_impact_sig", None)  # signature of submitted values

    # ----------------------------------------
    # HEADER
    # ----------------------------------------
    st.markdown("###### WILL THIS PROJECT HAVE A TRAFFIC IMPACT EVENT?\n")

    answer = st.segmented_control(
        "Select **Yes** to create a Traffic Impact Event, **No** to continue",
        options=["Yes", "No"],
        default=st.session_state.get("traffic_impact_answer", None),
    )
    st.session_state["traffic_impact_answer"] = answer

    # =========================================================================
    # MAIN CONTENT — ONLY WHEN "YES"
    # =========================================================================
    if answer == "Yes":
        st.write("")
        st.markdown("###### CREATE TRAFFIC IMPACT EVENT\n")

        # ----------------------------------------
        # Step Segmented Control
        # ----------------------------------------
        step_options = [
            "Set Impact Area",
            "Select Impacted Route",
            "Set Start/End Point",
        ]

        selected_step = st.segmented_control(
            "Traffic Impact Steps",
            options=step_options,
            default=st.session_state["traffic_impact_step"],
        )
        st.session_state["traffic_impact_step"] = selected_step

        # ----------------------------------------
        # Step Container
        # ----------------------------------------
        container = st.container(border=True)
        with container:
            tie_data = st.session_state.setdefault("tie_data", {})

            # STEP 1
            if selected_step == "Set Impact Area":
                impact_area(container)

            # STEP 2
            elif selected_step == "Select Impacted Route":
                select_impacted_route(container)

            # STEP 3
            elif selected_step == "Set Start/End Point":
                select_route_endpoints(container)

            # ----------------------------------------
            # Gather required values from session (with fallbacks to tie_data)
            # ----------------------------------------
            def _get_required_values():
                """
                Returns a dict of the four required values for validation & signature.
                Prefers st.session_state values; falls back to tie_data for compatibility.
                """
                selected_impact_area = st.session_state.get("selected_impact_area")
                if selected_impact_area is None:
                    selected_impact_area = tie_data.get("impact_buffers")

                selected_route_geom = st.session_state.get("selected_route_geom")
                if selected_route_geom is None:
                    selected_route_geom = tie_data.get("selected_route_geom")

                selected_start_point = st.session_state.get("selected_start_point")
                if selected_start_point is None:
                    # support the tie_data version saved by select_route_endpoints
                    selected_start_point = tie_data.get("selected_start_point") or tie_data.get("route_start_point")

                selected_end_point = st.session_state.get("selected_end_point")
                if selected_end_point is None:
                    # support the tie_data version saved by select_route_endpoints
                    selected_end_point = tie_data.get("selected_end_point") or tie_data.get("route_end_point")

                return {
                    "selected_impact_area": selected_impact_area,
                    "selected_route_geom": selected_route_geom,
                    "selected_start_point": selected_start_point,
                    "selected_end_point": selected_end_point,
                }

            required = _get_required_values()

            # ----------------------------------------
            # Build a signature of current required values
            # ----------------------------------------
            def _safe_dump(x):
                try:
                    return json.dumps(x, sort_keys=True, default=str)
                except Exception:
                    return str(x)

            def _traffic_impact_signature(vals) -> str:
                return "|".join([
                    _safe_dump(vals.get("selected_impact_area")),
                    _safe_dump(vals.get("selected_route_geom")),
                    _safe_dump(vals.get("selected_start_point")),
                    _safe_dump(vals.get("selected_end_point")),
                ])

            current_sig = _traffic_impact_signature(required)

            # ----------------------------------------
            # Reset submitted state if values changed after a submit
            # ----------------------------------------
            if st.session_state.get("traffic_impact_submitted"):
                if st.session_state.get("submitted_traffic_impact_sig") != current_sig:
                    st.session_state["traffic_impact_submitted"] = False
                    st.session_state["just_submitted_traffic_impact"] = False

            # ----------------------------------------
            # Always show SUBMIT button
            # ----------------------------------------
            btn_ph = st.empty()
            submitted = bool(st.session_state.get("traffic_impact_submitted"))

            def _render_btn(is_done: bool):
                label = "SUBMIT TRAFFIC IMPACT ✅" if is_done else "SUBMIT TRAFFIC IMPACT"
                suffix = "done" if is_done else "live"
                return btn_ph.button(
                    label,
                    use_container_width=True,
                    key=f"submit_traffic_impact_btn_{suffix}",
                    disabled=is_done,
                )

            clicked = _render_btn(submitted)

            # ----------------------------------------
            # Handle click
            # ----------------------------------------
            if clicked and not submitted:
                # Validate four required values
                missing_msgs = []
                if not required["selected_impact_area"]:
                    missing_msgs.append("• Set the **Impact Area** in *Set Impact Area*.")
                if not required["selected_route_geom"]:
                    missing_msgs.append("• Select an **Impacted Route** in *Select Impacted Route*.")
                if not required["selected_start_point"]:
                    missing_msgs.append("• Drop the **Start Point** in *Set Start/End Point*.")
                if not required["selected_end_point"]:
                    missing_msgs.append("• Drop the **End Point** in *Set Start/End Point*.")

                if missing_msgs:
                    st.error("Please complete the following before submitting:\n\n" + "\n".join(missing_msgs))
                else:
                    # ----------------------------------------
                    # All required present -> persist to project_* keys
                    # ----------------------------------------
                    st.session_state["project_traffic_impact_area"] = required["selected_impact_area"]
                    st.session_state["project_impacted_route"] = required["selected_route_geom"]

                    # Route ID/Name: prefer top-level; fallback to tie_data
                    st.session_state["project_impact_route_id"] = (
                        st.session_state.get("selected_route_id") or tie_data.get("selected_route_id")
                    )
                    st.session_state["project_impact_route_name"] = (
                        st.session_state.get("selected_route_name") or tie_data.get("selected_route_name")
                    )

                    # Start/End points: support dict with lonlat OR simple [lon,lat]
                    def _extract_lon_lat(pt):
                        if isinstance(pt, dict) and isinstance(pt.get("lonlat"), (list, tuple)) and len(pt["lonlat"]) == 2:
                            lon, lat = pt["lonlat"]
                            return float(lon), float(lat)
                        if isinstance(pt, (list, tuple)) and len(pt) == 2:
                            lon, lat = pt
                            return float(lon), float(lat)
                        # Fallback: try keys lng/lat
                        if isinstance(pt, dict) and "lng" in pt and "lat" in pt:
                            return float(pt["lng"]), float(pt["lat"])
                        return None, None

                    start_lon, start_lat = _extract_lon_lat(required["selected_start_point"])
                    end_lon, end_lat = _extract_lon_lat(required["selected_end_point"])

                    st.session_state["project_impact_start_point"] = [[start_lon, start_lat]]
                    st.session_state["project_impact_end_point"] = [[end_lon, end_lat]]

                    # Also store scalar x/y (lon/lat) if available
                    if start_lon is not None and start_lat is not None:
                        st.session_state["project_impact_start_point_x"] = start_lon
                        st.session_state["project_impact_start_point_y"] = start_lat
                    if end_lon is not None and end_lat is not None:
                        st.session_state["project_impact_end_point_x"] = end_lon
                        st.session_state["project_impact_end_point_y"] = end_lat

                    # Mark success and persist signature
                    st.session_state["traffic_impact_submitted"] = True
                    st.session_state["just_submitted_traffic_impact"] = True
                    st.session_state["submitted_traffic_impact_sig"] = current_sig

                    # Swap in the ✓ button immediately
                    btn_ph.button(
                        "SUBMIT TRAFFIC IMPACT ✅",
                        use_container_width=True,
                        key="submit_traffic_impact_btn_done",
                        disabled=True,
                    )

            # ----------------------------------------
            # Success banner just after submission
            # ----------------------------------------
            if st.session_state.get("just_submitted_traffic_impact"):
                st.session_state["just_submitted_traffic_impact"] = False

    # =========================================================================
    # NO RESPONSE
    # =========================================================================
    else:
        st.write("")
        st.info("No Traffic Impact Event selected. You may continue.")
