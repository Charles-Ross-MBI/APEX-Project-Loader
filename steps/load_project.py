"""
===============================================================================
LOAD PROJECT (STREAMLIT) — APEX / AGOL UPLOAD ORCHESTRATION
===============================================================================

Purpose:
    Orchestrates the Streamlit workflow for uploading a project and its related
    datasets into APEX (AGOL-backed) layers using AGOLDataLoader.

    This module:
      - Builds payloads using the payload factory functions (payloads.py)
      - Uploads records to the appropriate AGOL layers in a defined sequence
      - Reports per-step success/failure to the Streamlit UI
      - Aggregates failures and summarizes them (no automatic deletion)

Key behaviors:
    Upload order (and failure semantics):
      1) Project
         - HARD STOP if this fails (st.stop()) because dependent uploads require
           the created GlobalID.
      2) Geometry
         - May upload one or multiple geometry payloads
         - Aggregates per-geometry failures for clear user feedback
      3) Communities (optional)
      4) Contacts (optional)   # (contacts not in this function; reserved)
      5) Geography layers (optional; depends on presence of {name}_list keys)
      6) Traffic impact artifacts (silent; failures summarized at the end)

    Failure handling pattern:
      - Project failure: show error, record failure with step name, and st.stop()
      - Downstream failure(s): record failures with step names; at end, present
        a clear summary of which steps failed. No automatic deletion is performed.

Session-state dependencies (expected at runtime):
    Connection:
      - 'apex_url'

    Layer IDs:
      - 'projects_layer', 'sites_layer', 'routes_layer', 'boundaries_layer'
      - 'impact_comms_layer', 'contacts_layer'  # contacts not used in this file
      - 'region_layer', 'bor_layer', 'house_layer', 'senate_layer'
      - optional: 'impact_routes_layer' (used when route or boundary selected)
      - 'traffic_impacts', 'start_points', 'end_points'

    Geometry selection flags:
      - 'selected_point', 'selected_route', 'selected_boundary'

    Geography presence flags:
      - '{name}_list' keys (e.g., 'region_list', 'borough_list', etc.)
        NOTE: these keys gate whether the corresponding geography layer uploads.

    Results / status:
      - 'apex_globalid' (set after project upload)
      - 'upload_complete' (set True when all steps succeed)

    Error aggregation:
      - 'step_failures' list (accumulated dicts: {'step': str, 'message': str})

Notes:
    - This module is intentionally UI-driven: it uses Streamlit spinners, success/
      error messages, and session_state to communicate status.
    - No automatic cleanup is attempted on error.
===============================================================================
"""

from __future__ import annotations

import streamlit as st

from agol.agol_util import AGOLDataLoader, format_guid, delete_cascade_by_globalid
from agol.agol_payloads import (
    communities_payload,
    geography_payload,
    geometry_payload,
    project_payload,
    ti_card_payload,
    awp_apex_cy_payload
)

# -----------------------------------------------------------------------------
# Helper: record a structured failure with step name and message
# -----------------------------------------------------------------------------
def _record_failure(step: str, message: str) -> None:
    st.session_state.setdefault("step_failures", [])
    st.session_state["step_failures"].append({"step": step, "message": str(message)})


# =============================================================================
# ENTRYPOINT: PROJECT + RELATED DATASETS UPLOAD
# =============================================================================
def load_project_apex() -> None:
    """
    Upload the current Streamlit session's project and related records into APEX.

    Failure handling:
        - Project upload failure is a hard stop (st.stop()) because the GlobalID
          is required for all dependent payloads.
        - Subsequent failures are collected into st.session_state['step_failures'].
          At the end, a summary of failed steps is displayed. No deletion is attempted.

    Returns:
        None (side effects only: Streamlit UI + st.session_state updates).
    """

    spinner_container = st.empty()

    # -------------------------------------------------------------------------
    # STEP 1: UPLOAD PROJECT (HARD STOP ON FAILURE)
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Project to APEX..."):
        try:
            payload_project = project_payload()
            projects_layer = st.session_state["projects_layer"]
            load_project = (
                AGOLDataLoader(
                    url=st.session_state["apex_url"], layer=projects_layer
                ).add_features(payload_project)
                if payload_project
                else {"success": False, "message": "Failed to Load Project to APEX DB"}
            )
        except Exception as e:
            load_project = {"success": False, "message": f"Project payload error: {e}"}
    spinner_container.empty()

    if not load_project.get("success"):
        error_msg = load_project.get("message", "Unknown error")
        st.error(f"LOAD PROJECT: FAILURE ❌ {error_msg}")
        _record_failure("Project", error_msg)
        st.stop()

    # Project success
    st.session_state["apex_globalid"] = format_guid(load_project["globalids"])
    st.success("LOAD PROJECT: SUCCESS ✅")
    

    # -------------------------------------------------------------------------
    # STEP 2: UPLOAD GEOMETRY (MAY BE MULTIPLE GEOMETRIES)
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Project Geometry to APEX..."):
        failures = []
        try:
            payload_geometries = geometry_payload()

            # Determine which layer to load based on the selection flags.
            if st.session_state.get("selected_point"):
                geometry_layer = st.session_state["sites_layer"]
                geometry_type = "Point Geometry"
            elif st.session_state.get("selected_route"):
                geometry_layer = st.session_state["routes_layer"]
                geometry_type = "Route Geometry"
            elif st.session_state.get("selected_boundary"):
                geometry_layer = st.session_state["boundaries_layer"]
                geometry_type = "Boundary Geometry"
            else:
                raise ValueError("No geometry type selected.")

            loader = AGOLDataLoader(
                url=st.session_state["apex_url"], layer=geometry_layer
            )

            geometries = (
                payload_geometries
                if isinstance(payload_geometries, list)
                else [payload_geometries]
            )

            for idx, geom in enumerate(geometries, start=1):
                step_name = f"{geometry_type} #{idx}" if len(geometries) > 1 else geometry_type
                if not geom:
                    msg = f"{step_name}: Empty geometry payload."
                    failures.append(msg)
                    _record_failure(step_name, msg)
                    continue
                result = loader.add_features(geom)
                if not result.get("success"):
                    msg = f"{step_name}: {result.get('message', 'Unknown geometry upload failure.')}"
                    failures.append(msg)
                    _record_failure(step_name, msg)
        except Exception as e:
            msg = f"Project Geometry payload error: {e}"
            failures.append(msg)
            _record_failure("Geometry", msg)
    spinner_container.empty()

    if not failures:
        st.success("LOAD GEOMETRY: SUCCESS ✅")
    else:
        st.error("LOAD GEOMETRY: FAILURE ❌")
        for msg in failures:
            st.error(f"• {msg}")

    # -------------------------------------------------------------------------
    # STEP 3: UPLOAD COMMUNITIES (OPTIONAL)
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Communities to APEX..."):
        try:
            payload_communities = communities_payload()
            communities_layer = st.session_state["impact_comms_layer"]
            if payload_communities is None:
                load_communities = None
            else:
                load_communities = AGOLDataLoader(
                    url=st.session_state["apex_url"], layer=communities_layer
                ).add_features(payload_communities)
        except Exception as e:
            load_communities = {"success": False, "message": f"Communities payload error: {e}"}
    spinner_container.empty()

    if load_communities is not None:
        if load_communities.get("success"):
            st.success("LOAD COMMUNITIES: SUCCESS ✅")
        else:
            msg = load_communities.get("message", "Unknown communities upload error.")
            st.error(f"LOAD COMMUNITIES: FAILURE ❌ {msg}")
            _record_failure("Communities", msg)

    # -------------------------------------------------------------------------
    # STEP 4: UPLOAD GEOGRAPHY (OPTIONAL; GATED BY SESSION_STATE LIST PRESENCE)
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Geography to APEX..."):
        geography_layers = {
            "region": st.session_state["region_layer"],
            "borough": st.session_state["bor_layer"],
            "senate": st.session_state["senate_layer"],
            "house": st.session_state["house_layer"],
        }

        if st.session_state.get("selected_route") or st.session_state.get("selected_boundary"):
            geography_layers["route"] = st.session_state["impact_routes_layer"]

        load_results = {}
        try:
            for name, layer_id in geography_layers.items():
                if f"{name}_list" in st.session_state:
                    payload = geography_payload(name)
                    if payload is None:
                        load_results[name] = None
                    else:
                        load_results[name] = AGOLDataLoader(
                            url=st.session_state["apex_url"], layer=layer_id
                        ).add_features(payload)
        except Exception as e:
            load_results["__error__"] = {"success": False, "message": f"Geography payload error: {e}"}
    spinner_container.empty()

    failed_layers = []
    fail_messages = []

    for name, result in load_results.items():
        if name == "__error__":
            msg = result.get("message", "Unknown geography error.")
            failed_layers.append("GEOGRAPHY")
            fail_messages.append(msg)
            _record_failure("Geography", msg)
            continue

        if result is not None and not result.get("success", True):
            step_name = f"Geography: {name.upper()}"
            msg = result.get("message", f"{step_name} failed.")
            failed_layers.append(name.upper())
            fail_messages.append(msg)
            _record_failure(step_name, msg)

    if failed_layers:
        st.error(
            "LOAD GEOGRAPHIES: FAILURE ❌\n"
            f"Failed layers: {', '.join(failed_layers)}\n"
            f"Messages: {', '.join(fail_messages)}"
        )
    else:
        st.success("LOAD GEOGRAPHIES: SUCCESS ✅")

    # -------------------------------------------------------------------------
    # STEP 5: LOAD TRAFFIC IMPACT CARD
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Traffic Impact Card to APEX..."):
        step5_ok = True

        # TRAFFIC IMPACT
        try:
            payload_traffic = ti_card_payload()
            traffic_layer = st.session_state["ti_card_layer"]
            if payload_traffic is None:
                load_traffic = None
            else:
                load_traffic = AGOLDataLoader(
                    url=st.session_state["apex_url"], layer=traffic_layer
                ).add_features(payload_traffic)

            if load_traffic is not None:
                if isinstance(load_traffic, dict):
                    if not load_traffic.get("success", False):
                        _record_failure("Traffic Impact", load_traffic.get("message", "Unknown error"))
                        step5_ok = False
            else:
                _record_failure("Traffic Impact", "No payload or no response from loader.")
                step5_ok = False

        except Exception as e:
            _record_failure("Traffic Impact", f"Traffic impact payload error: {e}")
            step5_ok = False
            load_traffic = {"success": False, "message": f"Traffic Impact Card payload error: {e}"}


    # Final message now matches all other steps
    if step5_ok:
        st.success("LOAD TRAFFIC IMPACT CARD: SUCCESS ✅")
    else:
        st.error("LOAD TRAFFIC IMPACT CARD: ERROR — CHECK MESSAGES ABOVE")

    # Diagnostics
    st.session_state["step5_uploads"] = {
        "traffic_impact_card": load_traffic if "load_traffic" in locals() else None,
    }

    # -------------------------------------------------------------------------
    # STEP 6 (SILENT): AWP APEX CY UPDATE
    # -------------------------------------------------------------------------
    if st.session_state.get("details_type", None) == 'AASHTOWare Database':
        try:
            payload_awp_cy = awp_apex_cy_payload()
            cy_layer = st.session_state["contracts_layer"]  # adjust if needed
            if payload_awp_cy is None:
                load_awp_cy = None
            else:
                load_awp_cy = AGOLDataLoader(
                    url=st.session_state["aashtoware_url"], layer=cy_layer
                ).update_features(payload_awp_cy)

            if load_awp_cy is not None:
                if isinstance(load_awp_cy, dict):
                    if not load_awp_cy.get("success", False):
                        _record_failure("AWP Apex CY", load_awp_cy.get("message", "Unknown error"))
                else:
                    if not bool(load_awp_cy):
                        _record_failure("AWP Apex CY", "Unknown loader response")
        except Exception as e:
            _record_failure("AWP Apex CY", f"AWP Apex CY payload error: {e}")
            load_awp_cy = {"success": False, "message": f"AWP Apex CY payload error: {e}"}

        # (OPTIONAL) record step 6 in diagnostics
        st.session_state["step6_uploads"] = {
            "awp_apex_cy": load_awp_cy if "load_awp_cy" in locals() else None,
        }


    # -------------------------------------------------------------------------
    # FINALIZATION: CLEANUP ON FAILURE OR MARK COMPLETE
    # -------------------------------------------------------------------------
    if st.session_state.get("step_failures"):
        st.session_state["upload_complete"] = False

        st.error("UPLOAD FAILED ❌ One or more steps failed.")

        # Show detailed failure list
        with st.expander("Failure details", expanded=True):
            for failure in st.session_state["step_failures"]:
                if isinstance(failure, dict):
                    step = failure.get("step", "Unknown step")
                    msg = failure.get("message", "No message provided")
                else:
                    step = "Unknown step"
                    msg = str(failure)
                st.markdown(f"- **{step}**: {msg}")

        # ---------------------------------------------------------
        # Perform cleanup only if project was successfully created
        # ---------------------------------------------------------
        if st.session_state.get("apex_globalid"):
            try:
                cleaned = delete_cascade_by_globalid(
                    url=st.session_state['apex_url'],
                    main_layer=st.session_state['projects_layer'],
                    related_layers=[
                        st.session_state["sites_layer"],
                        st.session_state["routes_layer"],
                        st.session_state["boundaries_layer"],
                        st.session_state["impact_comms_layer"],
                        st.session_state["region_layer"],
                        st.session_state["bor_layer"],
                        st.session_state["senate_layer"],
                        st.session_state["house_layer"],
                        st.session_state["impact_routes_layer"],
                        st.session_state["ti_card_layer"],
                        st.session_state["ti_route_layer"],
                        st.session_state["ti_start_layer"],
                        st.session_state["ti_end_layer"]
                    ],
                    globalid_field='GlobalID',
                    globalid_value=st.session_state['apex_globalid'],
                    parent_field='parentglobalid',
                )


                if cleaned:
                    st.warning(
                        "Partial uploads were cleaned up (placeholder). "
                        "Please address the errors and try again."
                    )
                else:
                    st.warning(
                        "Cleanup attempted but did not complete (placeholder). "
                        "Check logs or try again."
                    )

            except Exception as e:
                st.error(f"Cleanup (placeholder) encountered an error: {e}")

        else:
            st.info(
                "The project record was never created, so no cleanup was required. "
                "Please correct the above issue(s) and try again."
            )

    else:
        st.session_state["upload_complete"] = True
        st.write("")
        st.markdown(
            """
            <h3 style="font-size:20px; font-weight:600;">
                ✅ Upload Finished! Refresh the page to
                <span style="font-weight:700;">add a new project</span>.
            </h3>
            """,
            unsafe_allow_html=True,
        )
        
       


    
