### =============================================================================
### PROJECT DEPLOYMENT TAB
### =============================================================================

import streamlit as st
from datetime import datetime
import time
from typing import Optional, Dict, Any

from agol.agol_util import (
    AGOLDataLoader,
    select_record,
)

from agol.agol_payloads import (
    manage_deployment_payload,
)

from util.input_util import (
    widget_key,
)

# -----------------------------------------------------------------------------
# Helper: fetch active project record
# -----------------------------------------------------------------------------

def _get_project_record():
    apex_guid = st.session_state.get("apex_guid")
    url = st.session_state.get("apex_url")
    layer = st.session_state.get("projects_layer")

    if not (apex_guid and url and layer is not None):
        return None

    recs = select_record(
        url=url,
        layer=layer,
        id_field="globalid",
        id_value=apex_guid,
        fields="*",
        return_geometry=False,
    )

    return recs[0]["attributes"] if recs else None


# -----------------------------------------------------------------------------
# Build package_out for deployment update
# -----------------------------------------------------------------------------

def _build_deployment_package() -> dict:
    """Build a package of deployment values for manage_deployment_payload.

    Deployment version is generated automatically.

    Widget values are stored under versioned widget_key() values. This module
    mirrors the current selections into stable session_state keys
    (database_status / target_applications) inside manage_deployment() so the
    payload builder can remain simple.
    """
    return {
        "database_status": st.session_state.get("database_status"),
        "target_applications": st.session_state.get("target_applications"),
        "deployment_version": datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
    }


# -----------------------------------------------------------------------------
# DEPLOY to AGOL
# -----------------------------------------------------------------------------

def _deploy_to_agol_deployment(
    payload: Dict[str, Any],
    edit_type: str,
) -> Dict[str, Any]:

    base_url = st.session_state.get("apex_url")
    layer_idx = st.session_state.get("projects_layer")

    if base_url is None or layer_idx is None:
        st.error("AGOL Projects layer is not configured.")
        return {"success": False}

    loader = AGOLDataLoader(base_url, layer_idx)

    # UI progress is handled by the caller (manage_deployment) so this function
    # stays UI-neutral.
    return loader.update_features(payload)


# -----------------------------------------------------------------------------
# Default seeding from project record
# -----------------------------------------------------------------------------

def _seed_database_defaults(project: dict, version: str, is_awp: bool, *, force: bool = False):
    """Seed widget defaults from the AGOL project record.

    Defaults are pulled from:
      - Database_Status (single value for the selectbox)
      - Target_Applications (comma-and-space separated text field -> multiselect list)

    If force=True, existing widget state is overwritten.
    """

    status_opts = st.session_state.get("database_status_vals", [])
    target_opts = st.session_state.get("target_applications_vals", [])

    status_key = widget_key("database_status", version, is_awp)
    target_key = widget_key("target_applications", version, is_awp)

    # -------------------------
    # Deployment Status
    # -------------------------
    record_status = project.get("Database_Status")

    if force or status_key not in st.session_state:
        if record_status in status_opts:
            st.session_state[status_key] = record_status
        elif status_opts:
            st.session_state[status_key] = status_opts[0]
        else:
            st.session_state[status_key] = None

    # -------------------------
    # Target Applications
    # -------------------------
    record_targets = project.get("Target_Applications")

    if force or target_key not in st.session_state:
        if isinstance(record_targets, str) and record_targets.strip():
            parsed = [v.strip() for v in record_targets.split(",") if v.strip()]
            st.session_state[target_key] = [v for v in parsed if v in target_opts]
        elif target_opts:
            st.session_state[target_key] = [target_opts[0]]
        else:
            st.session_state[target_key] = []


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

def manage_deployment():

    project = _get_project_record()
    if not project:
        return

    version = st.session_state.get("version")
    is_awp = False  # database never AWP-driven

    status_key = widget_key("database_status", version, is_awp)
    target_key = widget_key("target_applications", version, is_awp)

    # -------------------------------------------------------------
    # Seed defaults ON FIRST LOAD (or if widget keys were cleared)
    # -------------------------------------------------------------
    if status_key not in st.session_state or target_key not in st.session_state:
        _seed_database_defaults(project, version, is_awp)

    # -------------------------------------------------------------
    # Widgets
    # -------------------------------------------------------------
    st.selectbox(
        "Database Status",
        options=st.session_state.get("database_status_vals", []),
        key=status_key,
    )

    st.multiselect(
        "Target Applications",
        options=st.session_state.get("target_applications_vals", []),
        key=target_key,
    )

    # Mirror widget selections into stable keys used by payload builder.
    st.session_state["database_status"] = st.session_state.get(status_key)
    st.session_state["target_applications"] = st.session_state.get(target_key)

    st.write('')

    clicked = st.button(
        "UPDATE DEPLOYMENT",
        type="primary",
        use_container_width=True,
    )

    # Progress UI sits directly under the button.
    progress_slot = st.empty()

    if clicked:
        bar = progress_slot.progress(0, text="Preparing deployment package…")

        package_out = _build_deployment_package()

        # Include OBJECTID for update
        if "apex_object_id" in st.session_state:
            package_out["objectid"] = st.session_state.apex_object_id

        bar.progress(20, text="Building AGOL payload…")
        payload = manage_deployment_payload(package_out, "updates")

        bar.progress(55, text="Updating AGOL deployment…")
        result = _deploy_to_agol_deployment(
            payload,
            "updates",
        )

        if not result.get("success"):
            bar.progress(100, text="Update failed.")
            st.error("Deployment update failed.")
            return

        bar.progress(80, text="Refreshing project record…")

        # -------------------------------------------------------------
        # Re-pull project record and rebuild widget defaults
        # -------------------------------------------------------------
        project = _get_project_record()
        if not project:
            bar.progress(100, text="Refresh failed.")
            st.error("Unable to refresh project record after update.")
            return

        # Remove ONLY the current widget state + mirrored stable keys.
        status_key = widget_key("database_status", version, is_awp)
        target_key = widget_key("target_applications", version, is_awp)

        for k in (status_key, target_key, "database_status", "target_applications"):
            if k in st.session_state:
                del st.session_state[k]

        # Reseed defaults from updated record (force overwrite)
        _seed_database_defaults(project, version, is_awp, force=True)

        bar.progress(100, text="Complete.")
        time.sleep(0.4)
        progress_slot.empty()

        # Rerun so widgets reflect reseeded defaults.
        st.rerun()