
"""
=============================================================================
PROJECT DETAILS FORM (STREAMLIT)
=============================================================================
Purpose:
Renders a two-mode project details form:
    1) AASHTOWare Database (read-only display of values pulled into session_state)
    2) User Input (editable Streamlit widgets)

Key behaviors:
    - Source-specific widget keys to prevent value bleed between AWP vs UI
   - Read-only “widgets” rendered via HTML/CSS while still persisting values
   - Per-source snapshot persistence for navigation and switching modes
   - Impacted communities selection persisted per source and mirrored for legacy usage
=============================================================================

"""

import streamlit as st
import datetime
from agol.agol_util import get_multiple_fields, select_record, aashtoware_geometry
from util.read_only_util import ro_widget
from util.input_util import (
    fmt_currency, 
    fmt_date, 
    fmt_date_or_none, 
    fmt_int, 
    fmt_int_or_none, 
    fmt_string,
    fmt_agol_date,
    widget_key
)


# =============================================================================
# GENERIC SESSION-BASED WIDGET HELPERS
# =============================================================================
# session_selectbox:
#   A standard selectbox wrapper that defaults to prior session_state values,
#   with optional string coercion and source-specific widget keys.
# =============================================================================
def session_selectbox(
    key: str,
    label: str,
    help: str,
    options: list,
    default_key: str = None,
    force_str: bool = False,
    is_awp: bool = False,
):
    """
    Render a Streamlit selectbox that defaults to the current session_state value
    or to another session_state key passed in as default_key. If the default value
    is not in options, it will be added. Optionally convert the default value to str.
    Uses source-specific, versioned widget keys to allow hard resets on source/project switches.
    """
    version = st.session_state.get("form_version", 0)

    # Resolve default value robustly
    if default_key and default_key in st.session_state:
        default_value = st.session_state.get(default_key)
    else:
        default_value = st.session_state.get(key, options[0] if options else "")
    if force_str and default_value is not None:
        default_value = str(default_value)

    # Normalize options to ensure the default exists and can be indexed
    normalized_options = [str(opt) if force_str else opt for opt in options]
    if default_value not in normalized_options and default_value is not None:
        normalized_options = [default_value] + normalized_options
    default_index = normalized_options.index(default_value) if default_value in normalized_options else 0

    # Use source-specific widget key
    st.session_state[key] = st.selectbox(
        label,
        normalized_options,
        index=default_index,
        key=widget_key(key, version, is_awp),
        help=help
    )
    return st.session_state[key]


# =============================================================================
# FORM SUBSECTION: IMPACTED COMMUNITIES (MULTISELECT)
# =============================================================================
# - Pulls communities from ArcGIS FeatureServer via get_multiple_fields()
# - Persists selections per source (awp vs ui)
# - Mirrors current selection into legacy keys for downstream compatibility
# =============================================================================
def impacted_comms_select(is_awp: bool = False):
    """Multiselect for impacted communities.

    IMPORTANT: selections are *source-specific*.
    - User Input selections do not bleed into AASHTOWare selections (and vice-versa).
    - We persist into dedicated session_state keys per source:
        * ui_impact_comm_ids / ui_impact_comm_names / ui_impact_comm
        * awp_impact_comm_ids / awp_impact_comm_names / awp_impact_comm
    - For backwards compatibility with downstream code, we also mirror the *current* selection
      into the legacy shared keys: impact_comm_ids / impact_comm_names / impact_comm.
    """

    version = st.session_state.get("form_version", 0)
    src = "awp" if is_awp else "ui"

    # Source-specific persistence keys
    ids_key = f"{src}_impact_comm_ids"
    names_key = f"{src}_impact_comm_names"
    value_key = f"{src}_impact_comm"

    # Data source for communities (ArcGIS FeatureServer)
    comms_url = st.session_state['communities']
    comms_list = get_multiple_fields(comms_url, 7, ["OverallName", "DCCED_CommunityId"]) or []

    # Build lookups:
    # - name_to_id: display name => unique community ID
    # - id_to_name: reverse mapping used for restoring selections
    name_to_id = {
        c["OverallName"]: c["DCCED_CommunityId"]
        for c in comms_list
        if c.get("OverallName") and c.get("DCCED_CommunityId")
    }
    id_to_name = {v: k for k, v in name_to_id.items()}

    # Restore previous selections (SOURCE-SPECIFIC)
    prev_ids = st.session_state.get(ids_key, []) or []
    prev_names_raw = st.session_state.get(names_key, "") or ""

    # names may be stored as comma-separated string
    if isinstance(prev_names_raw, str):
        prev_names = [n.strip() for n in prev_names_raw.split(",") if n.strip()]
    else:
        prev_names = list(prev_names_raw) if prev_names_raw else []

    # Prefer restoration from IDs; fallback to stored names
    default_names_from_ids = [id_to_name[i] for i in prev_ids if i in id_to_name]
    default_names_fallback = [n for n in prev_names if n in name_to_id]
    default_names = default_names_from_ids or default_names_fallback

    # UI: multiselect widget
    selected_names = st.multiselect(
        "Select communities:",
        options=sorted(name_to_id.keys()),
        default=sorted(default_names),
        key=widget_key(f"{src}_impact_comm", version, is_awp),
        help="Choose one or more communities impacted by the project.",
    )

    # Translate selection => IDs for storage/processing
    selected_ids = [name_to_id[n] for n in selected_names if n in name_to_id]

    # Persist per source (this prevents bleed between modes)
    st.session_state[ids_key] = selected_ids
    st.session_state[names_key] = ",".join(selected_names)
    st.session_state[value_key] = selected_ids

    # Mirror into legacy/shared keys for downstream compatibility (current source only)
    st.session_state["impact_comm_ids"] = selected_ids
    st.session_state["impact_comm_names"] = ",".join(selected_names)
    st.session_state["impact_comm"] = selected_ids

    return selected_ids



# =============================================================================
# FORM SUBSECTION: AASHTOWARE PROJECT SELECTOR (DROPDOWN + STATE SYNC)
# =============================================================================
# - Pulls AASHTOWare project rows from the AWP FeatureServer via get_multiple_fields()
# - Builds label <-> GlobalID mappings for user-friendly selection + authoritative lookup
# - Uses a versioned widget key (form_version) to prevent Streamlit widget state bleed
# - Syncs the selectbox display to an existing awp_guid / aashto_id when returning to the page
# - on_change callback updates ONLY selection state (record loading is handled elsewhere)
# =============================================================================
def aashtoware_project():
    # ---------------------------------------------------------------------
    # Helper: format ConstructionYears for display
    #   None / ""      -> ""
    #   "CY2024,CY2025"-> "[CY2024, CY2025]"
    #   ["CY2024", ...]-> "[CY2024, ...]"
    # ---------------------------------------------------------------------
    def _format_construction_years(cy):
        if not cy:
            return ""
        if isinstance(cy, (list, tuple, set)):
            parts = [str(x).strip() for x in cy if x and str(x).strip()]
        else:
            parts = [p.strip() for p in str(cy).split(",") if p.strip()]
        return f"{', '.join(parts)}" if parts else ""

    aashtoware = st.session_state["aashtoware_url"]

    # -------------------------------------------------------------------------
    # Pull projects (same data pull you referenced)
    # -------------------------------------------------------------------------
    projects = get_multiple_fields(
        aashtoware,
        st.session_state["contracts_layer"],
        ["ProjectName", "IRIS", "ConstructionYears", "GlobalID"]
    ) or []

    # NEW: lookup for existing ConstructionYears by GlobalID (from same pull)
    gid_to_cy = {
        p.get("GlobalID"): _format_construction_years(p.get("ConstructionYears"))
        for p in projects
        if p.get("GlobalID")
    }

    
    # Sort projects by ProjectName (case-insensitive), blank names go last
    projects_sorted = sorted(
        (p for p in projects if p.get("GlobalID")),
        key=lambda p: ((p.get("ProjectName") or "").strip().lower() == "", (p.get("ProjectName") or "").strip().lower())
    )

    label_to_gid = {
        f"{p.get('IRIS', '')} – {p.get('ProjectName', '')}": p.get("GlobalID")
        for p in projects_sorted
    }

    gid_to_label = {gid: label for label, gid in label_to_gid.items()}
    placeholder_label = "— Select a project —"
    labels = [placeholder_label] + list(label_to_gid.keys())  # already sorted by ProjectName


    # -------------------------------------------------------------------------
    # Widget key management (versioned keys prevent Streamlit state bleed)
    # -------------------------------------------------------------------------
    version = st.session_state.get("form_version", 0)
    widget_key = f"awp_project_select_{version}"

    # ------------------------------------------------------------
    # 1) Sync selection when returning to an entry
    # ------------------------------------------------------------
    active_gid = st.session_state.get("awp_guid") or st.session_state.get("aashto_id")
    active_label = gid_to_label.get(active_gid) if active_gid else None

    if active_gid and active_label:
        st.session_state["aashto_id"] = active_gid
        st.session_state["aashto_label"] = active_label
        st.session_state["aashto_selected_project"] = active_label

        # NEW: also seed the construction years display when restoring
        st.session_state["awp_selected_construction_years"] = gid_to_cy.get(active_gid, "")

    # ------------------------------------------------------------
    # 2) Seed widget display value WITHOUT using index=
    # ------------------------------------------------------------
    desired_label = st.session_state.get(widget_key)

    if desired_label not in labels:
        desired_label = st.session_state.get("aashto_label")
    if desired_label not in labels:
        desired_label = active_label
    if desired_label not in labels:
        desired_label = placeholder_label

    if st.session_state.get(widget_key) not in labels:
        st.session_state[widget_key] = desired_label

    # ------------------------------------------------------------
    # 3) Callback: ONLY update selection state
    #    + NEW: update read-only ConstructionYears display
    # ------------------------------------------------------------
    def _on_project_change():
        selected_label = st.session_state[widget_key]

        if selected_label == placeholder_label:
            st.session_state["aashto_label"] = None
            st.session_state["aashto_id"] = None
            st.session_state["aashto_selected_project"] = None
            st.session_state["awp_guid"] = None
            st.session_state["awp_update"] = "No"

            # NEW: clear the display field
            st.session_state["awp_selected_construction_years"] = ""
            return

        selected_gid = label_to_gid.get(selected_label)
        st.session_state["aashto_label"] = selected_label
        st.session_state["aashto_id"] = selected_gid
        st.session_state["aashto_selected_project"] = selected_label
        st.session_state["awp_guid"] = selected_gid
        st.session_state["awp_update"] = "Yes"

        # NEW: set the display field from the same data pull
        st.session_state["awp_selected_construction_years"] = gid_to_cy.get(selected_gid, "")

    # Render widget (NO index= here)
    st.selectbox(
        "AASHTOWare Project List",
        labels,
        key=widget_key,
        on_change=_on_project_change,
    )

    # -------------------------------------------------------------------------
    # NEW: Ensure display value is populated on programmatic restores / reruns
    # -------------------------------------------------------------------------
    selected_gid = st.session_state.get("aashto_id")
    if selected_gid and st.session_state.get("awp_selected_construction_years") is None:
        st.session_state["awp_selected_construction_years"] = gid_to_cy.get(selected_gid, "")
    elif selected_gid and not st.session_state.get("awp_selected_construction_years"):
        # If empty string, keep it (means no years). If missing key, repopulate.
        st.session_state["awp_selected_construction_years"] = gid_to_cy.get(selected_gid, "")

    # -------------------------------------------------------------------------
    # NEW: Read-only display ABOVE the project form (right after selectbox)
    # -------------------------------------------------------------------------
    ro_widget(
        key="awp_selected_construction_years",
        label="Existing Construction Year(s) in APEX",
        value=fmt_string(st.session_state.get("awp_selected_construction_years", "")),
    )
    st.write("")  # spacer

    # -------------------------------------------------------------------------
    # 4) LOAD FORM WHEN GUID CHANGES (UNCHANGED)
    # -------------------------------------------------------------------------
    last_loaded = st.session_state.get("awp_last_loaded_gid")
    if selected_gid and selected_gid != last_loaded:
        user_keys = [
            "construction_year",
            "phase",
            "proj_name",
            "iris",
            "stip",
            "fed_proj_num",
            "fund_type",
            "proj_prac",
            "anticipated_start",
            "anticipated_end",
            "award_date",
            "award_fiscal_year",
            "contractor",
            "awarded_amount",
            "current_contract_amount",
            "amount_paid_to_date",
            "tenadd",
            "proj_desc",
            # CONTACT (new)
            "awp_contact_name",
            "awp_contact_role",
            "awp_contact_email",
            "awp_contact_phone",
            # WEB
            "proj_web",
            # impacted communities (legacy/shared mirror key used elsewhere)
            "impact_comm",
        ]

        for k in user_keys:
            st.session_state[k] = "" if k not in ["award_date", "antcipated_start", "anticipated_end", "tenadd"] else None

        # Load full AWP record
        record = select_record(aashtoware, 0, "GlobalID", selected_gid)
        if record and "attributes" in record[0]:
            attrs = record[0]["attributes"]
            for k, v in attrs.items():
                st.session_state[f"awp_{k}".lower()] = v

        st.session_state["awp_last_loaded_gid"] = selected_gid
        st.session_state["awp_selection_changed"] = True

        # Reset All Construction Year Defaults
        for k in [k for k in st.session_state if k.startswith("awp_widget_key_construction_year_")]:
            st.session_state[k] = None



# =============================================================================
# SNAPSHOTTING / PERSISTENCE
# =============================================================================
# These utilities allow you to:
# - Switch between sources without losing the other source's values
# - Navigate away and return while maintaining progress
#
# Mechanism:
# - Snapshot persisted keys into st.session_state['saved_awp'] or ['saved_user']
# - Preload values back into st.session_state upon re-entering a mode
# =============================================================================
_PERSISTED_KEYS = [
    # Core fields
    "construction_year",
    "phase",
    "proj_name",
    "iris",
    "stip",
    "fed_proj_num",
    "fund_type",
    "proj_prac",
    "anticipated_start",
    "anticipated_end",

    # Award info
    "award_date",
    "award_fiscal_year",
    "contractor",
    "awarded_amount",
    "current_contract_amount",
    "amount_paid_to_date",
    "tenadd",

    # Descriptions / links
    "proj_desc",
    "proj_web",

    # Contact (new/current)
    "awp_contact_name",
    "awp_contact_role",
    "awp_contact_email",
    "awp_contact_phone",

    # Impacted communities (legacy mirror keys used downstream)
    "impact_comm",
    "impact_comm_ids",
    "impact_comm_names",

    # AWP-specific display fields (read-only widgets)
    "awp_proj_name",
    "awp_proj_desc",

    # identifiers for re-population
    "aashto_id",
    "aashto_label",
    "aashto_selected_project",
]
_SOURCE_SNAPSHOT_KEY = {
    "AASHTOWare Database": "saved_awp",
    "User Input": "saved_user",
}


def _snapshot_form(source: str):
    # Copy current form values into a per-source snapshot.
    # NOTE: This is called after submission to persist the entered/viewed state.
    snap_key = _SOURCE_SNAPSHOT_KEY.get(source)
    if not snap_key:
        return
    st.session_state[snap_key] = {k: st.session_state.get(k, None) for k in _PERSISTED_KEYS}


def _preload_from_snapshot(source: str):
    # Pre-populate session_state from a per-source snapshot (if present).
    # Only non-None snapshot values overwrite the current session_state.
    snap_key = _SOURCE_SNAPSHOT_KEY.get(source)
    if not snap_key:
        return
    snap = st.session_state.get(snap_key, {})
    for k, v in snap.items():
        if v is not None:
            st.session_state[k] = v


# =============================================================================
# FORM ENTRYPOINT: SOURCE SELECTION + ROUTING
# =============================================================================
# project_details_form():
# - Displays segmented control:
#     ["AASHTOWare Database", "User Input"]
# - Handles source switching:
#     - Clears AWP keys when going to User Input
#     - Bumps form_version to force widget key refresh
# - Preloads from snapshot for the selected source
# - Renders the appropriate form mode via _render_original_form()
# =============================================================================
def project_details_form():
    """
    Source selection (AASHTOWare vs User Input) using segmented_control.
    Forms render only when a selection is made. Resets/bump happen on source switches.
    """

    # ---- Session init: ensures expected keys exist ----
    st.session_state.setdefault("form_version", 0)
    st.session_state.setdefault("prev_info_option", None)
    st.session_state.setdefault("info_option", None)

    OPTIONS = ["AASHTOWare Database", "User Input"]

    # ---- Seed the segmented control from a previously submitted value ----
    # If the user has submitted before, st.session_state['details_type'] holds their choice.
    # Use it as the default ONLY if no current selection is set.
    prior_choice = st.session_state.get("details_type")
    if (
        prior_choice in OPTIONS
        and (st.session_state.get("info_option") is None or st.session_state.get("info_option") == "")
    ):
        st.session_state["info_option"] = prior_choice

    # ---- Source selection control ----
    selection = st.segmented_control(
        "Choose Source Method:",
        OPTIONS,
        key="info_option",
        # selection_mode stays "single" (default)
    )
    st.write("")  # spacer

    # Current vs previous selection used to detect mode switches
    current_option = selection
    st.session_state["current_option"] = selection
    previous_option = st.session_state.get("prev_info_option")

    # ---- Mode switch handler (runs immediately on selection change) ----
    if current_option is not None and current_option != previous_option:
        if current_option == "User Input":
            # Clear AWP-specific keys and selection memory (keep user-entered fields)
            for k in list(st.session_state.keys()):
                if k.startswith("awp_"):
                    st.session_state[k] = ""
            st.session_state["aashto_id"] = ""
            st.session_state["aashto_label"] = ""
            st.session_state["aashto_selected_project"] = ""

            # ALSO clear shared non-AWP keys so User Input starts fresh.
            # We'll reload any prior user data from the 'saved_user' snapshot right after.
            for k in _PERSISTED_KEYS:
                if not k.startswith("awp_"):
                    st.session_state[k] = ""

        elif current_option == "AASHTOWare Database":
            # Keep user-entered fields; AWP will prefill where applicable
            pass

        # Persist selection and force widget reset via version bump
        st.session_state["prev_info_option"] = current_option
        st.session_state["details_complete"] = False
        st.session_state["form_version"] = st.session_state.get("form_version", 0) + 1
        # No explicit st.rerun()—the widget interaction already caused a rerun.

    # ---- Restore prior values for the chosen mode (if any snapshot exists) ----
    if current_option:
        _preload_from_snapshot(current_option)

    # ---- Route to source-specific rendering ----
    if current_option == "AASHTOWare Database":
        st.markdown("<h5>Select Project & Complete Form</h5>", unsafe_allow_html=True)
        # aashtoware_project() is expected to populate st.session_state with AWP values
        aashtoware_project()
        _render_original_form(is_awp=True)
    elif current_option == "User Input":
        st.markdown("<h5>Complete Form</h5>", unsafe_allow_html=True)
        _render_original_form(is_awp=False)
    else:
        st.info("Please choose a source method above to begin.")


# =============================================================================
# FORM BODY RENDERER: ALL SECTIONS 1-8 + SUBMIT/VALIDATION
# =============================================================================
# _render_original_form(is_awp):
# - is_awp=True  => render read-only fields populated from AWP keys
# - is_awp=False => render user-editable Streamlit widgets
#
# Inside the form, the code is structured into numbered sections:
#   1) Project Name
#   2) Construction Year, Phase, & IDs
#   3) Funding Type & Practice
#   4) Start & End Date
#   5) Award Information
#   6) Description
#   7) Web Links
#   8) Impacted Communities
#   + Submit/Validation + Snapshot
# =============================================================================
def _render_original_form(is_awp: bool):
    # Versioned form key forces widget regeneration on version bump
    version = st.session_state.get("form_version", 0)
    form_key = f"project_details_form_{version}"

    def val(key_user: str, key_awp: str = None, coerce_float: bool = False):
        # Unified getter:
        # - AWP mode reads from AWP session_state keys
        # - UI mode reads from user keys
        if is_awp and key_awp:
            v = st.session_state.get(key_awp, "")
        else:
            v = st.session_state.get(key_user, "")
        if coerce_float:
            try:
                return float(v or 0)
            except Exception:
                return 0.0
        return v


    # =============================================================================
    # BEGIN FORM (Streamlit form block)
    # =============================================================================
    with st.form(form_key):

        AWP_FIELDS = st.session_state['awp_fields']

        # ---------------------------------------------------------------------
        # SECTION 1: PROJECT NAME
        # ---------------------------------------------------------------------
        st.markdown("<h5>1. PROJECT NAME </h4>", unsafe_allow_html=True)
        if is_awp:
            # AWP mode: show read-only AASHTOWare name + Public name
            c1, c2 = st.columns(2)
            with c1:
                ro_widget(
                    key="awp_proj_name",
                    label="AASHTOWare Project Name",
                    value=fmt_string(val(AWP_FIELDS['awp_proj_name'])),
                )
            with c2:
                ro_widget(
                    key="proj_name",
                    label="Public Project Name",
                    value=fmt_string(val(AWP_FIELDS['proj_name'])),
                )
        else:
            # UI mode: editable public project name
            st.session_state["proj_name"] = st.text_input(
                "Public Project Name ⮜",
                value=st.session_state.get("proj_name", ""),
                key=widget_key("proj_name", version, is_awp),
                help="Provide the project name that will be displayed publicly.",
            )

        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 2: CONSTRUCTION YEAR, PHASE, & IDS
        # ---------------------------------------------------------------------
        st.markdown("<h5>2. CONSTRUCTION YEAR, PHASE, & IDS</h4>", unsafe_allow_html=True)

        # Subsection 2A: Construction Year + Phase
        col1, col2 = st.columns(2)
        with col1:
            # All available options (already strings like "CY2025")
            options = [str(o) if o is not None else "" for o in st.session_state["construction_years"]]

            # Saved value
            saved = st.session_state.get("construction_year", "")
            saved_str = str(saved) if saved is not None else ""

            # Already-used construction years (string or comma-separated string or list)
            existing_raw = st.session_state.get("awp_selected_construction_years", "")

            # Normalize existing values to a set of strings
            if isinstance(existing_raw, str):
                existing = {v.strip() for v in existing_raw.split(",") if v.strip()}
            elif isinstance(existing_raw, (list, tuple, set)):
                existing = {str(v).strip() for v in existing_raw}
            else:
                existing = set()

            # --- SIMPLE FILTER: remove any option already in existing years ---
            filtered_options = [opt for opt in options if opt not in existing]

            # Safety: ensure at least one choice exists
            if not filtered_options:
                filtered_options = [""]

            # Pick index safely
            if saved_str in filtered_options:
                idx = filtered_options.index(saved_str)
            elif "" in filtered_options:
                idx = filtered_options.index("")
            else:
                idx = 0

            st.session_state["construction_year"] = st.selectbox(
                "Construction Year ⮜",
                filtered_options,
                index=idx,
                key=widget_key("construction_year", version, is_awp),
                help="The project’s assigned year. Continuing projects must also receive a new year.",
            )
        if is_awp:
            with col2:
                ro_widget(
                    key="phase",
                    label="Phase",
                    value=fmt_string(val(AWP_FIELDS['phase'])),
                )
        else:
            with col2:
                st.session_state["phase"] = session_selectbox(
                    key="phase",
                    label="Phase",
                    help="Indicates the construction phase scheduled for this project in the current year.",
                    options=(st.session_state['phase_list']),
                    is_awp=is_awp,
                )

        # Subsection 2B: Identifiers (IRIS / STIP / Federal Project Number)
        if is_awp:
            col5, col6, col7 = st.columns(3)
            with col5:
                ro_widget(
                    key="iris",
                    label="IRIS",
                    value=fmt_string(val(AWP_FIELDS['iris'])),
                )
            with col6:
                ro_widget(
                    key="stip",
                    label="STIP",
                    value=fmt_string(val(AWP_FIELDS['stip'])),
                )
            with col7:
                ro_widget(
                    key="fed_proj_num",
                    label="Federal Project Number",
                    value=fmt_string(val(AWP_FIELDS['fed_proj_num'])),
                )
        else:
            col5, col6, col7 = st.columns(3)
            with col5:
                st.session_state["iris"] = st.text_input(
                    label="IRIS",
                    value=st.session_state.get("iris", ""),
                    key=widget_key("iris", version, is_awp),
                )
            with col6:
                st.session_state["stip"] = st.text_input(
                    label="STIP",
                    value=st.session_state.get("stip", ""),
                    key=widget_key("stip", version, is_awp),
                )
            with col7:
                st.session_state["fed_proj_num"] = st.text_input(
                    label="Federal Project Number",
                    value=st.session_state.get("fed_proj_num", ""),
                    key=widget_key("fed_proj_num", version, is_awp),
                )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 3: FUNDING TYPE & PRACTICE
        # ---------------------------------------------------------------------
        st.markdown("<h5>3. FUNDING TYPE & PRACTICE</h4>", unsafe_allow_html=True)
        if is_awp:
            col13, col14 = st.columns(2)
            with col13:
                ro_widget(
                    key="fund_type",
                    label="Funding Type",
                    value=fmt_string(val(AWP_FIELDS['fund_type'])),
                )
            with col14:
                ro_widget(
                    key="proj_prac",
                    label="Project Practice",
                    value=fmt_string(val(AWP_FIELDS['proj_prac'])),
                )
        else:
            col13, col14 = st.columns(2)
            with col13:
                st.session_state["fund_type"] = session_selectbox(
                    key="fund_type",
                    label="Funding Type",
                    help="",
                    options=(st.session_state['funding_list']),
                    is_awp=is_awp,
                )
            with col14:
                st.session_state["proj_prac"] = session_selectbox(
                    key="proj_prac",
                    label="Project Practice",
                    help="",
                    options=st.session_state['practice_list'],
                    is_awp=is_awp,
                )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 4: START & END DATE
        # ---------------------------------------------------------------------
        st.markdown("<h5>4. START & END DATE</h4>", unsafe_allow_html=True)

        if is_awp:
            col10, col11 = st.columns(2)
            with col10:
                ro_widget(
                    key="anticipated_start",
                    label="Anticipated Start",
                    value=fmt_date(val(AWP_FIELDS['anticipated_start'])),
                )
            with col11:
                ro_widget(
                    key="anticipated_end",
                    label="Anticipated End",
                    value=fmt_date(val(AWP_FIELDS['anticipated_end'])),
                )
        else:
            col10, col11 = st.columns(2)
            with col10:
                st.session_state["anticipated_start"] = st.date_input(
                    label="Anticpated Start",
                    format="MM/DD/YYYY",
                    value=fmt_date_or_none(st.session_state.get("anticipated_start", None)),
                    key=widget_key("anticipated_start", version, is_awp),
                    help="The date the project was awarded to a contractor; sourced from AASHTOWare when available."
                )
            with col11:
                st.session_state["anticipated_end"] = st.date_input(
                    label="Anticpated End",
                    format="MM/DD/YYYY",
                    value=fmt_date_or_none(st.session_state.get("anticipated_end", None)),
                    key=widget_key("anticipated_end", version, is_awp),
                    help="The date the project was awarded to a contractor; sourced from AASHTOWare when available."
                )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 5: AWARD INFORMATION
        # ---------------------------------------------------------------------
        st.markdown("<h5>5. AWARD INFORMATION</h4>", unsafe_allow_html=True)

        # Subsection 5A: Award Date + Fiscal Year
        if is_awp:
            col12, col13 = st.columns(2)
            with col12:
                ro_widget(
                    key="award_date",
                    label="Award Date",
                    value=fmt_agol_date(val(AWP_FIELDS['award_date'])),
                )
            with col13:
                ro_widget(
                    key="award_fiscal_year",
                    label="Awarded Fiscal Year",
                    value=fmt_int(val(AWP_FIELDS['award_fiscal_year']), year=True),
                )
        else:
            col12, col13 = st.columns(2)
            with col12:
                st.session_state["award_date"] = st.date_input(
                    label="Award Date",
                    format="MM/DD/YYYY",
                    value=fmt_date_or_none(st.session_state.get("award_date", None)),
                    key=widget_key("award_date", version, is_awp),
                    help="The date the project was awarded to a contractor; sourced from AASHTOWare when available."
                )
            with col13:
                st.session_state["award_fiscal_year"] = session_selectbox(
                    key="award_fiscal_year",
                    label="Awarded Fiscal Year",
                    help="The fiscal year in which the project was awarded; fiscal years run from October through September. Sourced from AASHTOWare when available.",
                    options=st.session_state['years'],
                    force_str=is_awp,
                    is_awp=is_awp,
                )

        # Subsection 5B: Contractor
        if is_awp:
            ro_widget(
                key="contractor",
                label="Awarded Contractor",
                value=fmt_string(val(AWP_FIELDS['contractor'])),
            )
        else:
            st.session_state["contractor"] = st.text_input(
                label="Awarded Contractor",
                key=widget_key("contractor", version, is_awp),
                value=st.session_state.get("contractor", ''),
                help="The name of the awarded contractor for this project, sourced from AASHTOWare when available"
            )

        # Subsection 5C: Award/Contract Financials
        if is_awp:
            col15, col16, col17 = st.columns(3)
            with col15:
                ro_widget(
                    key="awarded_amount",
                    label="Awarded Amount",
                    value=fmt_currency(val(AWP_FIELDS['awarded_amount'])),
                )
            with col16:
                ro_widget(
                    key="current_contract_amount",
                    label="Current Contract Amount",
                    value=fmt_currency(val(AWP_FIELDS['current_contract_amount'])),
                )
            with col17:
                ro_widget(
                    key="amount_paid_to_date",
                    label="Amount Paid to Date",
                    value=fmt_currency(val(AWP_FIELDS['amount_paid_to_date'])),
                )
        else:
            col15, col16, col17 = st.columns(3)
            with col15:
                st.session_state["awarded_amount"] = st.number_input(
                    label="Awarded Amount",
                    key=widget_key("awarded_amount", version, is_awp),
                    value=fmt_int_or_none(st.session_state.get("awarded_amount", None)),
                    help="Total awarded amount in dollars for the project, sourced from AASHTOWare when available"
                )
            with col16:
                st.session_state["current_contract_amount"] = st.number_input(
                    label="Current Contract Amount",
                    key=widget_key("current_contract_amount", version, is_awp),
                    value=fmt_int_or_none(st.session_state.get("current_contract_amount", None)),
                    help="The current contract amount for the project, sourced from AASHTOWare when available"
                )
            with col17:
                st.session_state["amount_paid_to_date"] = st.number_input(
                    label="Amount Paid to Date",
                    key=widget_key("amount_paid_to_date", version, is_awp),
                    value=fmt_int_or_none(st.session_state.get("amount_paid_to_date", None)),
                    help="Total amount paid to date to the contractor for the project, sourced from AASHTOWare when available"
                )

        # Subsection 5D: Tentative Advertise Date
        if is_awp:
            ro_widget(
                key="tenadd",
                label="Tentative Advertise Date",
                value=fmt_date(val(AWP_FIELDS['tenadd'])),
            )
        else:
            st.session_state["tenadd"] = st.date_input(
                label="Tentative Advertise Date",
                format="MM/DD/YYYY",
                value=fmt_date_or_none(st.session_state.get("tenadd", None)),
                help="The tentative advertised date represents the preliminary target month and year when the project is expected to be publicly posted for contractor bidding. "
                "This date is used for planning and coordination purposes and may shift as design progress, funding availability, permitting, and review milestones evolve.",
                key=widget_key("tenadd", version, is_awp),
            )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 6: DESCRIPTION
        # ---------------------------------------------------------------------
        st.markdown("<h5>6. DESCRIPTION</h4>", unsafe_allow_html=True)
        if is_awp:
            # AWP mode: show both AASHTOWare description and Public description (read-only)
            ro_widget(
                key="awp_proj_desc",
                label="AASHTOWare Description",
                value=fmt_string(val(AWP_FIELDS['awp_proj_desc'])),
                textarea=True
            )
            ro_widget(
                key="proj_desc",
                label="Public Description",
                value=fmt_string(val(AWP_FIELDS['proj_desc'])),
                textarea=True
            )
        else:
            # UI mode: editable public description
            st.session_state["proj_desc"] = st.text_area(
                "Public Description ⮜",
                height=200,
                max_chars=8000,
                value=st.session_state.get("proj_desc", ""),
                key=widget_key("proj_desc", version, is_awp),
                help="A comprehensive description of the project that will be visible to the public, summarizing the key details, objectives, and anticipated benefits in a clear and approachable manner."
            )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 7: CONTACT
        # ---------------------------------------------------------------------
        st.markdown("<h5>7. CONTACT</h4>", unsafe_allow_html=True)
        if is_awp:
            ro_widget(
                key="awp_contact_name",
                label="Contact",
                value=fmt_string(val(AWP_FIELDS['awp_contact_name']))
            )
            col18, col19 = st.columns(2)
            with col18:
                ro_widget(
                    key="awp_contact_email",
                    label="Email",
                    value=fmt_string(val(AWP_FIELDS['awp_contact_email']))
                )
            with col19:
                ro_widget(
                    key="awp_contact_phone",
                    label="Phone",
                    value=fmt_string(val(AWP_FIELDS['awp_contact_phone']))
                )
        else:
            st.session_state["awp_contact_name"] = st.text_input(
                label="Name",
                key=widget_key("awp_contact_name", version, is_awp),
                value=st.session_state.get("awp_sel_contact_name", ''),
            )
            col18, col19 = st.columns(2)
            with col18:
                st.session_state["awp_contact_email"] = st.text_input(
                    label="Email",
                    key=widget_key("awp_contact_email", version, is_awp),
                    value=st.session_state.get("awp_contact_email", ''),
                )
            with col19:
                st.session_state["awp_contact_phone"] = st.text_input(
                    label="Phone",
                    key=widget_key("awp_contact_phone", version, is_awp),
                    value=st.session_state.get("awp_contact_phone", ''),
                )

        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 8:PROJECT WEBSITE
        # ---------------------------------------------------------------------
        st.markdown("<h5>8. WEB LINK</h4>", unsafe_allow_html=True)
        if is_awp:
            ro_widget(
                key="proj_web",
                label="Project Website",
                value=fmt_string(val(AWP_FIELDS['proj_web']))
            )
            
        else:
            st.session_state["proj_web"] = st.text_input(
                label="Project Website",
                key=widget_key("proj_web", version, is_awp),
                value=st.session_state.get("proj_web", ''),
            )
           
        st.write("")
        st.write("")

        # ---------------------------------------------------------------------
        # SECTION 9: IMPACTED COMMUNITIES
        # ---------------------------------------------------------------------
        st.markdown("<h5>9. IMPACTED COMMUNITIES</h4>", unsafe_allow_html=True)
        st.session_state["impact_comm"] = impacted_comms_select(is_awp=is_awp)

        st.write("")

        # ---------------------------------------------------------------------
        # SUBMIT + VALIDATION + SNAPSHOT
        # ---------------------------------------------------------------------
        submit_button = st.form_submit_button("SUBMIT INFORMATION", use_container_width=True)

        if submit_button:
            
            # Required field rules differ by mode:
            # - AWP: requires Construction Year only
            # - UI : requires Construction Year, Public Project Name, Public Description
            if is_awp:
                required_fields = {
                    "Construction Year": st.session_state.get("construction_year"),
                }
            else:
                required_fields = {
                    "Construction Year": st.session_state.get("construction_year"),
                    "Public Project Name": st.session_state.get("proj_name"),
                    "Public Description": st.session_state.get("proj_desc"),
                }

            # Determine missing required values
            missing_fields = [field for field, value in required_fields.items() if not value]

            if missing_fields:
                # Display an error per missing field
                for field in missing_fields:
                    st.error(f"{field} Required")
                st.session_state["details_complete"] = False
            else:
                # Success state and persistence
                st.success("All necessary project information is now complete. Please continue.")
                st.session_state["details_complete"] = True
                st.session_state["project_details"] = required_fields
                st.session_state["details_type"] = st.session_state["current_option"]
                
                # Fields to format ONLY in UI mode (is_awp == False)
                UI_TRANSFORM_MAP = {
                    'anticipated_start': fmt_date,
                    'anticipated_end': fmt_date,
                    'award_date': fmt_date,
                    'tenadd': fmt_date     
                }
                
                # ------------------ TRANSFORM STEP (UI mode only) ------------------
                if not is_awp:
                    for key, func in UI_TRANSFORM_MAP.items():
                        if key in st.session_state:
                            try:
                                st.session_state[key] = func(st.session_state.get(key))
                            except Exception:
                                pass

                #Select Geometry Points if AASHTOWARE Project
                if is_awp:
                    st.session_state["awp_geometry_points"] = aashtoware_geometry(st.session_state['awp_id'])

            # Snapshot everything for this source so it persists across page navigation
            current_source = st.session_state.get("info_option")
            _snapshot_form(current_source)