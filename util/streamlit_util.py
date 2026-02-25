import streamlit as st
from agol.agol_district_queries import run_district_queries
from util.read_only_util import ro_widget
from agol.agol_util import (
    get_multiple_fields,
    select_record
)
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
# - Builds label <-> Id mappings for user-friendly selection + authoritative lookup
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
        ["ProjectName", "IRIS", "ConstructionYears", "Id"]
    ) or []

    # NEW: lookup for existing ConstructionYears by Id (from same pull)
    gid_to_cy = {
        p.get("Id"): _format_construction_years(p.get("ConstructionYears"))
        for p in projects
        if p.get("Id")
    }

    
    # Sort projects by ProjectName (case-insensitive), blank names go last
    projects_sorted = sorted(
        (p for p in projects if p.get("Id")),
        key=lambda p: ((p.get("ProjectName") or "").strip().lower() == "", (p.get("ProjectName") or "").strip().lower())
    )

    label_to_gid = {
        f"{p.get('Id', '')} – {p.get('ProjectName', '')}": p.get("Id")
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
        record = select_record(aashtoware, 0, "Id", selected_gid)
        if record and "attributes" in record[0]:
            attrs = record[0]["attributes"]
            for k, v in attrs.items():
                st.session_state[f"awp_{k}".lower()] = v

        st.session_state["awp_last_loaded_gid"] = selected_gid
        st.session_state["awp_selection_changed"] = True

        # Reset All Construction Year Defaults
        for k in [k for k in st.session_state if k.startswith("awp_widget_key_construction_year_")]:
            st.session_state[k] = None



def segmented_with_safe_default(label: str, options: list[str], state_key: str) -> str:
    """
    Render a segmented control and persist the selection to session state.

    This helper ensures the selection is always valid for the provided options:
    - If the previous session value is present and still valid, it is reused.
    - Otherwise, the first item in `options` becomes the default selection.

    Args:
        label: UI label displayed above the segmented control.
        options: Allowed option strings presented to the user.
        state_key: Session-state key used to store the selected option.

    Returns:
        The selected option string written to st.session_state[state_key].

    Side Effects:
        - Writes to st.session_state[state_key].
    """
    prev = st.session_state.get(state_key)
    if prev not in options:
        prev = options[0]
    st.session_state[state_key] = st.segmented_control(label, options, default=prev)
    return st.session_state[state_key]


def clear_geography_outputs() -> None:
    """
    Clear computed geography/district output strings.

    These values are displayed in the "PROJECT GEOGRAPHIES" expander and should
    be reset when the project type changes to avoid stale/mismatched results.

    Side Effects:
        - Sets house_string/senate_string/borough_string/region_string to "".
    """
    st.session_state.house_string = ""
    st.session_state.senate_string = ""
    st.session_state.borough_string = ""
    st.session_state.region_string = ""


def clear_geometry(*, point=False, route=False, boundary=False) -> None:
    """
    Clear selected geometry values in session state.

    Args:
        point: If True, clears st.session_state.selected_point.
        route: If True, clears st.session_state.selected_route.
        boundary: If True, clears st.session_state.selected_boundary.

    Side Effects:
        - Sets selected_* keys to None depending on flags.
    """
    if point:
        st.session_state.selected_point = None
    if route:
        st.session_state.selected_route = None
    if boundary:
        st.session_state.selected_boundary = None


def handle_project_type_change() -> None:
    """
    Handle a change in project type.

    When a user switches project types (Site/Route/Boundary), previously selected
    geometry and computed geographies can become invalid. This routine clears:
      - Geography output strings
      - Selected geometry values (point/route/boundary)
      - Upload method selection ("option")
    and updates the tracker key 'prev_project_type'.

    Side Effects:
        - Mutates multiple st.session_state keys.
    """
    if st.session_state.get("prev_project_type") != st.session_state.get("project_type"):
        clear_geography_outputs()
        clear_geometry(point=True, route=True, boundary=True)
        st.session_state["option"] = None
        st.session_state.prev_project_type = st.session_state.get("project_type")


def handle_upload_method_change(option: str, *, clear_boundary: bool = False) -> None:
    """
    Handle a change in upload method.

    Different upload methods write to the same canonical geometry keys
    (selected_point/selected_route/selected_boundary). To prevent cross-method
    bleed (e.g., a previously drawn line persisting when switching to shapefile),
    the prior geometry is cleared when the upload method changes.

    Args:
        option: Newly selected upload method string.
        clear_boundary: If True, also clears selected_boundary (used by Boundary projects).

    Side Effects:
        - Clears selected geometry keys (point/route, and possibly boundary).
        - Writes st.session_state.geo_option to the new option.
    """
    if st.session_state.get("geo_option") != option:
        clear_geometry(point=True, route=True, boundary=clear_boundary)
        st.session_state.geo_option = option


def ensure_prev_geometry_trackers() -> None:
    """
    Ensure that "previous geometry" trackers exist in session state.

    These keys are used to detect geometry changes between reruns and avoid
    expensive district queries unless necessary.

    Side Effects:
        - Initializes prev_selected_point/route/boundary to None if absent.
    """
    if "prev_selected_point" not in st.session_state:
        st.session_state.prev_selected_point = None
    if "prev_selected_route" not in st.session_state:
        st.session_state.prev_selected_route = None
    if "prev_selected_boundary" not in st.session_state:
        st.session_state.prev_selected_boundary = None


def run_queries_if_geometry_changed(point_val, route_val, boundary_val) -> None:
    """
    Run district/geography queries only when the selected geometry changes.

    Query calls may be expensive; this function compares current selected geometry
    to "prev_selected_*" values and triggers run_district_queries() only when:
      - the value is not None, AND
      - the value differs from the previous value.

    Args:
        point_val: Current st.session_state.selected_point value.
        route_val: Current st.session_state.selected_route value.
        boundary_val: Current st.session_state.selected_boundary value.

    Side Effects:
        - May call run_district_queries().
        - Updates prev_selected_point/route/boundary when a change is detected.
    """
    ensure_prev_geometry_trackers()

    point_changed = point_val is not None and point_val != st.session_state.prev_selected_point
    route_changed = route_val is not None and route_val != st.session_state.prev_selected_route
    boundary_changed = boundary_val is not None and boundary_val != st.session_state.prev_selected_boundary

    if point_changed or route_changed or boundary_changed:
        run_district_queries(sections = ['house', 'senate', 'borough', 'region'], message = "Querying against the geography layers...")
        st.session_state.prev_selected_point = point_val
        st.session_state.prev_selected_route = route_val
        st.session_state.prev_selected_boundary = boundary_val


def render_geographies_expander(*, show_routes: bool = False) -> None:
    """
    Render the "PROJECT GEOGRAPHIES" expander section.

    This is shown only when:
      - a geometry exists for the selected project type, AND
      - at least one geography output string is present.

    Args:
        show_routes: If True, also display route IDs and names (Route/Boundary flows).

    Side Effects:
        - Renders Streamlit UI elements (expander, columns, markdown).
    """
    house_val = st.session_state.get("house_string")
    senate_val = st.session_state.get("senate_string")
    borough_val = st.session_state.get("borough_string")
    region_val = st.session_state.get("region_string")

    with st.expander("**PROJECT GEOGRAPHIES**", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**House Districts:** {house_val or '—'}")
        col2.markdown(f"**Senate Districts:** {senate_val or '—'}")
        col1.markdown(f"**Boroughs:** {borough_val or '—'}")
        col2.markdown(f"**Regions:** {region_val or '—'}")

        if show_routes:
            route_ids = st.session_state.get("route_ids", None)
            route_names = st.session_state.get("route_names", None)
            st.markdown(f"**Route IDs:** {route_ids}")
            st.markdown(f"**Route Names:** {route_names} ")
