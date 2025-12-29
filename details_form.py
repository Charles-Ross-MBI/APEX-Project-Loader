
import streamlit as st
import datetime
from agol_util import get_multiple_fields
from aashtoware import aashtoware_project

# --- Widget key helper ---
def widget_key(name: str, version: int, is_awp: bool) -> str:
    """
    Build a per-source, per-version widget key so Streamlit treats AWP and UI
    as distinct controls and doesn't retain values across source switches.

    Result format:
      - AASHTOWare: awp_widget_key_<name>_<version>
      - User Input : ui_widget_key_<name>_<version>
    """
    prefix = "awp_widget_key" if is_awp else "ui_widget_key"
    return f"{prefix}_{name}_{version}"


# --- Helpers ---
def session_selectbox(
    key: str,
    label: str,
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
    )
    return st.session_state[key]


def impacted_comms_select(is_awp: bool = False):
    """
    Multiselect for impacted communities.
    - Displays community names but stores both IDs and names in session_state.
    - Restores selection by mapping stored IDs -> names and falling back to stored names.
    - Uses source-specific, versioned widget key yet provides an explicit default to persist across versions.
    """
    version = st.session_state.get("form_version", 0)
    comms_url = (
        "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/"
        "All_Alaska_Communities_Baker/FeatureServer"
    )
    # Expected shape: [{"OverallName": "...", "DCCED_CommunityId": "..."}]
    comms_list = get_multiple_fields(comms_url, 7, ["OverallName", "DCCED_CommunityId"]) or []

    # Mappings
    name_to_id = {
        c["OverallName"]: c["DCCED_CommunityId"]
        for c in comms_list
        if c.get("OverallName") and c.get("DCCED_CommunityId")
    }
    id_to_name = {v: k for k, v in name_to_id.items()}

    # Restore previous selections across reruns/version changes
    prev_ids = st.session_state.get("impact_comm_ids", []) or []
    prev_names = st.session_state.get("impact_comm_names", []) or []
    default_names_from_ids = [id_to_name[i] for i in prev_ids if i in id_to_name]
    default_names_fallback = [n for n in prev_names if n in name_to_id]
    default_names = default_names_from_ids or default_names_fallback

    selected_names = st.multiselect(
        "Select communities:",
        options=sorted(name_to_id.keys()),
        default=sorted(default_names),
        key=widget_key("impact_comm", version, is_awp),
        help="Choose one or more communities impacted by the project.",
    )
    selected_ids = [name_to_id[n] for n in selected_names if n in name_to_id]

    st.session_state["impact_comm_ids"] = selected_ids
    st.session_state["impact_comm_names"] = ",".join(selected_names)
    st.session_state["impact_comm"] = selected_ids  # compatibility

    return selected_ids


# -----------------------------
# Snapshotting utilities
# -----------------------------
_PERSISTED_KEYS = [
    "construction_year", "phase", "proj_name", "iris", "stip", "fed_proj_num",
    "fund_type", "proj_prac", "anticipated_start", "anticipated_end",
    "award_date", "award_fiscal_year", "contractor",
    "awarded_amount", "current_contract_amount", "amount_paid_to_date",
    "tenadd", "proj_desc", "proj_purp", "proj_impact",
    "proj_web", "apex_mapper_link", "apex_infosheet",
    "impact_comm", "impact_comm_ids", "impact_comm_names",
    # AWP-specific display fields:
    "awp_proj_name", "awp_proj_desc",
    # identifiers for re-population
    "aashto_id", "aashto_label", "aashto_selected_project",
]
_SOURCE_SNAPSHOT_KEY = {
    "AASHTOWare Database": "saved_awp",
    "User Input": "saved_user",
}


def _snapshot_form(source: str):
    """Copy current form values into a per-source snapshot."""
    snap_key = _SOURCE_SNAPSHOT_KEY.get(source)
    if not snap_key:
        return
    st.session_state[snap_key] = {k: st.session_state.get(k, None) for k in _PERSISTED_KEYS}


def _preload_from_snapshot(source: str):
    """Pre-populate session_state from a per-source snapshot (if present)."""
    snap_key = _SOURCE_SNAPSHOT_KEY.get(source)
    if not snap_key:
        return
    snap = st.session_state.get(snap_key, {})
    for k, v in snap.items():
        if v is not None:
            st.session_state[k] = v


# --- Main form wrapper ---

def project_details_form():
    """
    Source selection (AASHTOWare vs User Input) using segmented_control.
    Forms render only when a selection is made. Resets/bump happen on source switches.
    """

    # Initialize once
    st.session_state.setdefault("form_version", 0)
    st.session_state.setdefault("prev_info_option", None)
    st.session_state.setdefault("info_option", None)

    OPTIONS = ["AASHTOWare Database", "User Input"]

    # --- Seed the segmented control from a previously submitted value ---
    # If the user has submitted before, st.session_state['details_type'] holds their choice.
    # Use it as the default ONLY if no current selection is set.
    prior_choice = st.session_state.get("details_type")
    if (
        prior_choice in OPTIONS
        and (st.session_state.get("info_option") is None or st.session_state.get("info_option") == "")
    ):
        st.session_state["info_option"] = prior_choice

    # NOTE: No explicit default passed; the widget will use session_state['info_option'] if present.
    selection = st.segmented_control(
        "Choose Source Method:",
        OPTIONS,
        key="info_option",
        # selection_mode stays "single" (default)
    )
    st.write("")  # spacer

    current_option = selection  # value returned by the widget
    st.session_state["current_option"] = selection
    previous_option = st.session_state.get("prev_info_option")

    # Handle source change immediately (outside any callback)
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

    # Preload from snapshot for current option (if any)
    if current_option:
        _preload_from_snapshot(current_option)

    if current_option == "AASHTOWare Database":
        st.markdown("<h5>Select Project & Complete Form</h5>", unsafe_allow_html=True)
        # If aashtoware_project internally changes project selection,
        # ensure it increments form_version there to hard-reset widgets when needed.
        aashtoware_project()
        _render_original_form(is_awp=True)
    elif current_option == "User Input":
        st.markdown("<h5>Complete Form</h5>", unsafe_allow_html=True)
        _render_original_form(is_awp=False)
    else:
        st.info("Please choose a source method above to begin.")



# --- Original form renderer with source-specific, versioned keys ---
def _render_original_form(is_awp: bool):
    version = st.session_state.get("form_version", 0)
    form_key = f"project_details_form_{version}"

    def val(key_user: str, key_awp: str = None, coerce_float: bool = False):
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

    with st.form(form_key):
        st.markdown("<h5>1. PROJECT NAME </h4>", unsafe_allow_html=True)
        # Project Names
        if is_awp:
            c1, c2 = st.columns(2)
            with c1:
                st.session_state["awp_proj_name"] = st.text_input(
                    "AASHTOWare Project Name",
                    value=val("awp_proj_name", "awp_name"),
                    key=widget_key("awp_proj_name", version, is_awp),
                )
            with c2:
                st.session_state["proj_name"] = st.text_input(
                    "Public Project Name*",
                    value=st.session_state.get("proj_name", ""),
                    key=widget_key("proj_name", version, is_awp),
                )
        else:
            st.session_state["proj_name"] = st.text_input(
                "Public Project Name*",
                value=st.session_state.get("proj_name", ""),
                key=widget_key("proj_name", version, is_awp),
            )
        st.write("")

        

        st.markdown("<h5>2. CONSTRUCTION YEAR, PHASE, & IDS</h4>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)

        with col1:
            cy_options = ['', 'CY2025', 'CY2026', 'CY2027', 'CY2028', 'CY2029', 'CY2030']
            # Determine current year in CY format
            current_year = datetime.datetime.now().year
            current_cy_str = f"CY{current_year}"
            # If current year is not in the list, fall back to ''
            default_index = cy_options.index(current_cy_str) if current_cy_str in cy_options else 0
            current_cy = st.session_state.get("construction_year", cy_options[default_index])
            st.session_state["construction_year"] = st.selectbox(
                "Construction Year*",
                cy_options,
                index=default_index,
                key=widget_key("construction_year", version, is_awp),
            )
        with col2:
            phase_options = ['', "Planning", "Construction"]
            current_phase = st.session_state.get('phase', '')
            st.session_state["phase"] = st.selectbox(
                "Phase*", phase_options,
                index=(phase_options.index(current_phase) if current_phase in phase_options else 0),
                key=widget_key("phase", version, is_awp),
            )

        # Project Identifiers
        col5, col6, col7 = st.columns(3)
        with col5:
            st.session_state["iris"] = st.text_input(
                "IRIS",
                value=val("iris", "awp_iris_number"),
                key=widget_key("iris", version, is_awp),
            )
        with col6:
            st.session_state["stip"] = st.text_input(
                "STIP",
                value=st.session_state.get("stip", ""),
                key=widget_key("stip", version, is_awp),
            )
        with col7:
            st.session_state["fed_proj_num"] = st.text_input(
                "Federal Project Number",
                value=st.session_state.get("fed_proj_num", ""),
                key=widget_key("fed_proj_num", version, is_awp),
            )

        st.write("")
        st.write("")
        st.markdown("<h5>3. FUNDING TYPE & PRACTICE</h4>", unsafe_allow_html=True)
        col13, col14 = st.columns(2)
        with col13:
            st.session_state["fund_type"] = session_selectbox(
                key="fund_type*",
                label="Funding Type?",
                options=(["", "FHWA", "FAA", "STATE", "OTHER"] if not is_awp else ["", "FHWY", "FHWA", "FAA", "STATE", "OTHER"]),
                default_key=("awp_funding_type" if is_awp else None),
                is_awp=is_awp,
            )
        with col14:
            st.session_state["proj_prac"] = session_selectbox(
                key="proj_prac*",
                label="Project Practice?",
                options=['', 'Highways', "Aviation", "Facilities", "Marine Highway", "Other"],
                default_key=("awp_project_practice" if is_awp else None),
                is_awp=is_awp,
            )

        st.write("")
        st.write("")
        st.markdown("<h5>4. START & END DATE</h4>", unsafe_allow_html=True)
        col10, col11 = st.columns(2)
        with col10:
            st.session_state["anticipated_start"] = st.text_input(
                "Anticipated Start Date",
                placeholder="MM-YYYY (07-2025)",
                value=st.session_state.get("anticipated_start", ""),
                key=widget_key("anticipated_start", version, is_awp),
            )
        with col11:
            st.session_state["anticipated_end"] = st.text_input(
                "Anticipated End Date",
                placeholder="MM-YYYY (07-2025)",
                value=st.session_state.get("anticipated_end", ""),
                key=widget_key("anticipated_end", version, is_awp),
            )

        st.write("")
        st.write("")
        st.markdown("<h5>5. AWARD INFORMATION</h4>", unsafe_allow_html=True)
        col12, col13 = st.columns(2)
        with col12:
            stored_award_date = st.session_state.get("award_date", None)
            default_award_date = stored_award_date if isinstance(stored_award_date, datetime.date) else None
            if is_awp and default_award_date is None:
                awp_date = st.session_state.get("awp_award_date", None)
                default_award_date = awp_date if isinstance(awp_date, datetime.date) else None
            st.session_state["award_date"] = st.date_input(
                "Award Date",
                format="MM/DD/YYYY",
                value=default_award_date,
                key=widget_key("award_date", version, is_awp),
            )
        with col13:
            st.session_state["award_fiscal_year"] = session_selectbox(
                key="award_fiscal_year",
                label="Awarded Fiscal Year",
                options=["", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028", "2029", "2030"],
                default_key=("awp_awardfederalfiscalyear" if is_awp else None),
                force_str=is_awp,
                is_awp=is_awp,
            )

        st.session_state["contractor"] = st.text_input(
            "Awarded Contractor",
            value=val("contractor", "awp_contractor"),
            key=widget_key("contractor", version, is_awp),
        )

        col15, col16, col17 = st.columns(3)
        with col15:
            st.session_state["awarded_amount"] = st.number_input(
                "Awarded Amount",
                value=val("awarded_amount", "awp_proposal_awardedamount", coerce_float=True),
                key=widget_key("awarded_amount", version, is_awp),
            )
        with col16:
            st.session_state["current_contract_amount"] = st.number_input(
                "Current Contract Amount",
                value=val("current_contract_amount", "awp_contract_currentcontractamount", coerce_float=True),
                key=widget_key("current_contract_amount", version, is_awp),
            )
        with col17:
            st.session_state["amount_paid_to_date"] = st.number_input(
                "Amount Paid to Date",
                value=val("amount_paid_to_date", "awp_contract_amountpaidtodate", coerce_float=True),
                key=widget_key("amount_paid_to_date", version, is_awp),
            )

        # Tentative Advertise Date
        stored_tenadd = st.session_state.get("tenadd", None)
        default_tenadd = stored_tenadd if isinstance(stored_tenadd, datetime.date) else None
        if is_awp and default_tenadd is None:
            awp_tenadd = st.session_state.get("awp_tentative_advertising_date", None)
            default_tenadd = awp_tenadd if isinstance(awp_tenadd, datetime.date) else None
        st.session_state["tenadd"] = st.date_input(
            "Tentative Advertise Date",
            format="MM/DD/YYYY",
            value=default_tenadd,
            key=widget_key("tenadd", version, is_awp),
        )

        st.write("")
        st.write("")
        st.markdown("<h5>6. DESCRIPTIONS, IMPACTS, PURPOSE</h4>", unsafe_allow_html=True)
        if is_awp:
            st.session_state["awp_proj_desc"] = st.text_area(
                "AASHTOWare Description",
                height=200,
                value=st.session_state.get("awp_project_description", ""),
                key=widget_key("awp_proj_desc", version, is_awp),
            )
            st.session_state["proj_desc"] = st.text_area(
                "Public Description",
                height=200,
                value=st.session_state.get("proj_desc", ""),
                key=widget_key("proj_desc", version, is_awp),
            )
        else:
            st.session_state["proj_desc"] = st.text_area(
                "Description",
                height=200,
                value=st.session_state.get("proj_desc", ""),
                key=widget_key("proj_desc", version, is_awp),
            )

        st.session_state["proj_purp"] = st.text_area(
            "Project Purpose",
            height=200,
            value=st.session_state.get("proj_purp", ""),
            key=widget_key("proj_purp", version, is_awp),
        )
        st.session_state["proj_impact"] = st.text_area(
            "Current Traffic Impact",
            height=200,
            value=st.session_state.get("proj_impact", ""),
            key=widget_key("proj_impact", version, is_awp),
        )

        st.write("")
        st.write("")
        st.markdown("<h5>7. WEB LINKS</h4>", unsafe_allow_html=True)
        st.session_state["proj_web"] = st.text_input(
            "Project Website",
            value=st.session_state.get("proj_web", ""),
            key=widget_key("proj_web", version, is_awp),
        )
        st.session_state["apex_mapper_link"] = st.text_input(
            "APEX Mapper",
            value=st.session_state.get("apex_mapper_link", ""),
            key=widget_key("apex_mapper_link", version, is_awp),
        )
        st.session_state["apex_infosheet"] = st.text_input(
            "APEX Info Sheet",
            value=st.session_state.get("apex_infosheet", ""),
            key=widget_key("apex_infosheet", version, is_awp),
        )

        st.write("")
        st.write("")
        st.markdown("<h5>8. IMPACTED COMMUNITIES</h4>", unsafe_allow_html=True)
        st.session_state["impact_comm"] = impacted_comms_select(is_awp=is_awp)

        st.write("")
        # Submit button
        submit_button = st.form_submit_button("Submit")

        # Validation and post-submit output
        if submit_button:
            required_fields = {
                "Construction Year": st.session_state.get("construction_year"),
                "Project Name": st.session_state.get("proj_name"),
                "Description": st.session_state.get("proj_desc")

            }
            missing_fields = [field for field, value in required_fields.items() if not value]
            if missing_fields:
                for field in missing_fields:
                    st.error(f"{field} Required")
                st.session_state["details_complete"] = False
            else:
                st.success("Project Information Saved")
                st.session_state["details_complete"] = True
                st.session_state["project_details"] = required_fields
                st.session_state['details_type'] = st.session_state['current_option']


            # Preserve selected project label so the list repopulates on return
            if is_awp:
                st.session_state["aashto_selected_project"] = st.session_state.get("aashto_label", "")

            # Snapshot everything for this source so it persists across page navigation
            current_source = st.session_state.get("info_option")
            _snapshot_form(current_source)
