
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
      - Aggregates failures and attempts cleanup via delete_project() on error

Key behaviors:
    Upload order (and failure semantics):
      1) Project
         - HARD STOP if this fails (st.stop()) because dependent uploads require
           the created GlobalID.
      2) Geometry
         - May upload one or multiple geometry payloads
         - Aggregates per-geometry failures for clear user feedback
      3) Communities (optional)
      4) Contacts (optional)
      5) Geography layers (optional; depends on presence of {name}_list keys)

    Failure handling pattern:
      - Project failure: show error, record failure, and st.stop()
      - Downstream failure(s): record failures; at end, attempt delete_project()
        for cleanup and instruct user to reset application state.

Session-state dependencies (expected at runtime):
    Connection:
      - 'apex_url'

    Layer IDs:
      - 'projects_layer', 'sites_layer', 'routes_layer', 'boundaries_layer'
      - 'impact_comms_layer', 'contacts_layer'
      - 'region_layer', 'bor_layer', 'house_layer', 'senate_layer'
      - optional: 'impact_routes_layer' (used when route or boundary selected)

    Geometry selection flags:
      - 'selected_point', 'selected_route', 'selected_boundary'

    Geography presence flags:
      - '{name}_list' keys (e.g., 'region_list', 'borough_list', etc.)
        NOTE: these keys gate whether the corresponding geography layer uploads.

    Results / status:
      - 'apex_globalid' (set after project upload)
      - 'upload_complete' (set True when all steps succeed)

    Error aggregation:
      - 'step_failures' list (accumulated messages from any failed step)

Notes:
    - This module is intentionally UI-driven: it uses Streamlit spinners, success/
      error messages, and session_state to communicate status.
    - Cleanup is best-effort: delete_project() is attempted only after a GlobalID
      exists (i.e., project creation succeeded).

===============================================================================
"""

from __future__ import annotations

import streamlit as st

from agol.agol_util import AGOLDataLoader, delete_project, format_guid
from agol.agol_payloads import (
    communities_payload,
    geography_payload,
    geometry_payload,
    project_payload,
)


# =============================================================================
# ENTRYPOINT: PROJECT + RELATED DATASETS UPLOAD
# =============================================================================
# load_project_apex():
#   - Runs the full upload sequence in a fixed order
#   - Writes status updates to Streamlit UI
#   - Aggregates downstream failures and attempts cleanup at the end
# =============================================================================
def load_project_apex() -> None:
    """
    Upload the current Streamlit session's project and related records into APEX.

    Failure handling:
        - Project upload failure is a hard stop (st.stop()) because the GlobalID
          is required for all dependent payloads.
        - Subsequent failures are collected into st.session_state['step_failures'].
          If any failures exist at the end, the created project is deleted using
          delete_project() (best-effort), and the user is instructed to reset.

    Returns:
        None (side effects only: Streamlit UI + st.session_state updates).
    """

    # Spinner container used across steps for consistent UI behavior.
    spinner_container = st.empty()

    # -------------------------------------------------------------------------
    # STEP 1: UPLOAD PROJECT (HARD STOP ON FAILURE)
    # -------------------------------------------------------------------------
    # Rationale:
    #   The project record establishes the apex_globalid that all related payloads
    #   reference. If this step fails, nothing else can proceed safely.
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Project to APEX..."):
        try:
            payload_project = project_payload()
            projects_layer = st.session_state["projects_layer"]
            load_project = (
                AGOLDataLoader(
                    url=st.session_state["apex_url"],
                    layer=projects_layer,
                ).add_features(payload_project)
                if payload_project
                else {"success": False, "message": "Failed to Load Project to APEX DB"}
            )
        except Exception as e:
            load_project = {"success": False, "message": f"Project payload error: {e}"}
    spinner_container.empty()

    # --- HARD STOP IF PROJECT UPLOAD FAILS ---
    if not load_project.get("success"):
        error_msg = load_project.get("message", "Unknown error")
        st.error(f"LOAD PROJECT: FAILURE ❌ {error_msg}")
        st.session_state.setdefault("step_failures", []).append(error_msg)
        st.stop()

    # -------------------------------------------------------------------------
    # Project Upload Success Path
    # -------------------------------------------------------------------------
    # On success:
    #   - Store the created GlobalID (formatted) in session_state for downstream
    #     payload builders.
    # -------------------------------------------------------------------------
    if load_project.get("success"):
        st.session_state["apex_globalid"] = format_guid(load_project["globalids"])
        st.success("LOAD PROJECT: SUCCESS ✅")
    else:
        # Kept to preserve structure; normally unreachable due to st.stop().
        st.error(f"LOAD PROJECT: FAILURE ❌ {load_project.get('message')}")
        st.session_state.setdefault("step_failures", []).append(
            load_project.get("message")
        )

    # -------------------------------------------------------------------------
    # STEP 2: UPLOAD GEOMETRY (MAY BE MULTIPLE GEOMETRIES)
    # -------------------------------------------------------------------------
    # Rationale:
    #   Users may supply multiple geometries. We upload individually so partial
    #   failures can be reported without losing visibility into successes.
    #   Geometry layer choice is determined by the user's selection flags.
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Project Geometry to APEX..."):
        try:
            payload_geometries = geometry_payload(
                st.session_state.get("apex_globalid")
            )

            # Determine which layer to load into based on user selection.
            if st.session_state.get("selected_point"):
                geometry_layer = st.session_state["sites_layer"]
            elif st.session_state.get("selected_route"):
                geometry_layer = st.session_state["routes_layer"]
            elif st.session_state.get("selected_boundary"):
                geometry_layer = st.session_state["boundaries_layer"]
            else:
                raise ValueError("No geometry type selected.")

            loader = AGOLDataLoader(
                url=st.session_state["apex_url"],
                layer=geometry_layer,
            )

            failures = []

            # Ensure payload is iterable (list of payloads).
            geometries = (
                payload_geometries
                if isinstance(payload_geometries, list)
                else [payload_geometries]
            )

            # Upload each geometry individually so partial failures are visible.
            for idx, geom in enumerate(geometries, start=1):
                if not geom:
                    failures.append(f"Geometry #{idx}: Empty geometry payload.")
                    continue
                result = loader.add_features(geom)
                if not result.get("success"):
                    failures.append(
                        f"Geometry #{idx}: "
                        f"{result.get('message', 'Unknown geometry upload failure.')}"
                    )
        except Exception as e:
            failures = [f"Project Geometry payload error: {e}"]
    spinner_container.empty()

    # --- Final Status Message (Geometry) ---
    if not failures:
        st.success("LOAD GEOMETRY: SUCCESS ✅")
    else:
        st.error("LOAD GEOMETRY: FAILURE ❌")
        for msg in failures:
            st.error(f"• {msg}")
        st.session_state.setdefault("step_failures", []).extend(failures)

    # -------------------------------------------------------------------------
    # STEP 3: UPLOAD COMMUNITIES (OPTIONAL)
    # -------------------------------------------------------------------------
    # Notes:
    #   communities_payload() may return None when no community data exists.
    #   In that case we skip upload and do not treat it as a failure.
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Communities to APEX..."):
        try:
            payload_communities = communities_payload(
                st.session_state.get("apex_globalid")
            )
            communities_layer = st.session_state["impact_comms_layer"]
            if payload_communities is None:
                load_communities = None
            else:
                load_communities = AGOLDataLoader(
                    url=st.session_state["apex_url"],
                    layer=communities_layer,
                ).add_features(payload_communities)
        except Exception as e:
            load_communities = {
                "success": False,
                "message": f"Communities payload error: {e}",
            }
    spinner_container.empty()

    if load_communities is not None:
        if load_communities.get("success"):
            st.success("LOAD COMMUNITIES: SUCCESS ✅")
        else:
            st.error(
                "LOAD COMMUNITIES: FAILURE ❌ "
                f"{load_communities.get('message')}"
            )
            st.session_state.setdefault("step_failures", []).append(
                load_communities.get("message")
            )


    # -------------------------------------------------------------------------
    # STEP 4: UPLOAD GEOGRAPHY (OPTIONAL; GATED BY SESSION_STATE LIST PRESENCE)
    # -------------------------------------------------------------------------
    # Mechanism:
    #   - geography_layers maps logical geography names to AGOL layer IDs
    #   - We only upload a geography type if "{name}_list" exists in session_state
    #
    # NOTE (mapping correctness):
    #   - 'senate' -> senate_layer
    #   - 'house'  -> house_layer
    #
    # Conditional layer:
    #   - Add impacted routes only when route or boundary is selected.
    # -------------------------------------------------------------------------
    with spinner_container, st.spinner("Loading Geography to APEX..."):
        geography_layers = {
            "region": st.session_state["region_layer"],
            "borough": st.session_state["bor_layer"],
            "senate": st.session_state["senate_layer"],
            "house": st.session_state["house_layer"],
        }

        # Add impacted routes only when route or boundary is selected.
        if st.session_state["selected_route"] or st.session_state["selected_boundary"]:
            geography_layers["route"] = st.session_state["impact_routes_layer"]


        load_results = {}
        try:
            for name, layer_id in geography_layers.items():
                # Only upload if the corresponding list exists in session_state.
                if f"{name}_list" in st.session_state:
                    payload = geography_payload(
                        st.session_state.get("apex_globalid"),
                        name,
                    )
                    if payload is None:
                        load_results[name] = None
                    else:
                        load_results[name] = AGOLDataLoader(
                            url=st.session_state["apex_url"],
                            layer=layer_id,
                        ).add_features(payload)
        except Exception as e:
            load_results["error"] = {
                "success": False,
                "message": f"Geography payload error: {e}",
            }
    spinner_container.empty()

    failed_layers = []
    fail_messages = []
    for name, result in load_results.items():
        if result is not None and not result.get("success", True):
            failed_layers.append(name.upper())
            fail_messages.append(result.get("message"))

    if failed_layers:
        st.error(
            "LOAD GEOGRAPHIES: FAILURE ❌\n"
            f"Failed layers: {', '.join(failed_layers)}\n"
            f"Messages: {', '.join(fail_messages)}"
        )
        st.session_state.setdefault("step_failures", []).extend(fail_messages)
    else:
        st.success("LOAD GEOGRAPHIES: SUCCESS ✅")

    # -------------------------------------------------------------------------
    # FINALIZATION: CLEANUP ON FAILURE OR MARK COMPLETE
    # -------------------------------------------------------------------------
    # If any step failed:
    #   - If no GlobalID: project never created -> instruct user to reset
    #   - If GlobalID exists: best-effort delete_project() cleanup, then reset
    #
    # If no failures:
    #   - Set upload_complete and present completion message
    # -------------------------------------------------------------------------
    if st.session_state.get("step_failures"):
        # Case 1: No GlobalID → project never loaded.
        if not st.session_state.get("apex_globalid"):
            st.error(
                "UPLOAD FAILED ❌ Project did not load into APEX. "
                "Please reset the application and try again."
            )
        else:
            # Case 2: GlobalID exists → run backend cleanup.
            try:
                if delete_project(
                    st.session_state["apex_url"],
                    0,
                    st.session_state["apex_globalid"],
                ):
                    st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
                else:
                    st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
            except Exception:
                st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
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