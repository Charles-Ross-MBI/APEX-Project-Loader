
import streamlit as st
import datetime
from agol_util import get_multiple_fields

# --------------------------------------------------
# Helper: unique widget key
# --------------------------------------------------
def widget_key(name: str, version: int) -> str:
    return f"ui_widget_key_{name}_{version}"

# --------------------------------------------------
# Helper: selectbox with session persistence
# --------------------------------------------------
def session_selectbox(
    key: str,
    label: str,
    help: str,
    options: list,
    default_key: str = None,
    force_str: bool = False,
):
    version = st.session_state.get("form_version", 0)

    default_value = st.session_state.get(key, options[0] if options else "")

    if force_str and default_value is not None:
        default_value = str(default_value)

    normalized_options = [str(opt) if force_str else opt for opt in options]

    if default_value not in normalized_options and default_value is not None:
        normalized_options = [default_value] + normalized_options

    default_index = (
        normalized_options.index(default_value)
        if default_value in normalized_options
        else 0
    )

    st.session_state[key] = st.selectbox(
        label,
        normalized_options,
        index=default_index,
        key=widget_key(key, version),
        help=help,
    )

    return st.session_state[key]

# --------------------------------------------------
# Impacted Community Selector
# --------------------------------------------------
def impacted_comms_select():
    version = st.session_state.get("form_version", 0)

    comms_url = (
        "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/"
        "All_Alaska_Communities_Baker/FeatureServer"
    )

    comms_list = get_multiple_fields(
        comms_url, 7, ["OverallName", "DCCED_CommunityId"]
    ) or []

    name_to_id = {
        c["OverallName"]: c["DCCED_CommunityId"]
        for c in comms_list
        if c.get("OverallName") and c.get("DCCED_CommunityId")
    }
    id_to_name = {v: k for k, v in name_to_id.items()}

    prev_ids = st.session_state.get("impact_comm_ids", []) or []
    prev_names = st.session_state.get("impact_comm_names", []) or []

    default_names_from_ids = [id_to_name[i] for i in prev_ids if i in id_to_name]
    default_names_fallback = [n for n in prev_names if n in name_to_id]
    default_names = default_names_from_ids or default_names_fallback

    selected_names = st.multiselect(
        "Select communities:",
        options=sorted(name_to_id.keys()),
        default=sorted(default_names),
        key=widget_key("impact_comm", version),
        help="Choose one or more communities impacted by the project.",
    )

    selected_ids = [name_to_id[n] for n in selected_names if n in name_to_id]

    st.session_state["impact_comm_ids"] = selected_ids
    st.session_state["impact_comm_names"] = ",".join(selected_names)
    st.session_state["impact_comm"] = selected_ids

    return selected_ids

# --------------------------------------------------
# FULL FORM — ALWAYS SHOWN
# --------------------------------------------------
def user_input_form():
    st.session_state.setdefault("form_version", 0)
    version = st.session_state["form_version"]
    form_key = f"project_details_form_{version}"
    
    st.write('')

    with st.form(form_key):

        # -------------------------
        # 1. PROJECT NAME
        # -------------------------
        st.markdown("<h5>1. PROJECT NAME</h5>", unsafe_allow_html=True)

        st.session_state["proj_name"] = st.text_input(
            "Public Project Name ⮜",
            value=st.session_state.get("proj_name", ""),
            key=widget_key("proj_name", version),
        )

        # -------------------------
        # 2. YEAR / PHASE / IDS
        # -------------------------
        st.markdown("<h5>2. CONSTRUCTION YEAR, PHASE, & IDS</h5>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)

        with col1:
            current_year = datetime.datetime.now().year
            current_cy_str = f"CY{current_year}"

            years = st.session_state.get("construction_years", [current_cy_str])
            default_index = years.index(current_cy_str) if current_cy_str in years else 0

            st.session_state["construction_year"] = st.selectbox(
                "Construction Year ⮜",
                years,
                index=default_index,
                key=widget_key("construction_year", version),
            )

        with col2:
            st.session_state["phase"] = session_selectbox(
                key="phase",
                label="Phase",
                help="Construction phase for this year's project cycle.",
                options=st.session_state.get("phase_list", [""]),
            )

        col5, col6, col7 = st.columns(3)
        with col5:
            st.session_state["iris"] = st.text_input(
                "IRIS",
                value=st.session_state.get("iris", ""),
                key=widget_key("iris", version),
            )
        with col6:
            st.session_state["stip"] = st.text_input(
                "STIP",
                value=st.session_state.get("stip", ""),
                key=widget_key("stip", version),
            )
        with col7:
            st.session_state["fed_proj_num"] = st.text_input(
                "Federal Project Number",
                value=st.session_state.get("fed_proj_num", ""),
                key=widget_key("fed_proj_num", version),
            )

        # -------------------------
        # 3. FUNDING & PRACTICE
        # -------------------------
        st.markdown("<h5>3. FUNDING TYPE & PRACTICE</h5>", unsafe_allow_html=True)
        col13, col14 = st.columns(2)

        with col13:
            st.session_state["fund_type"] = session_selectbox(
                key="fund_type",
                label="Funding Type",
                help=None,
                options=st.session_state.get("funding_list", [""]),
            )

        with col14:
            st.session_state["proj_prac"] = session_selectbox(
                key="proj_prac",
                label="Project Practice",
                help=None,
                options=st.session_state.get("practice_list", [""]),
            )

        # -------------------------
        # 4. START / END YEAR
        # -------------------------
        st.markdown("<h5>4. START & END DATE</h5>", unsafe_allow_html=True)
        col10, col11 = st.columns(2)

        with col10:
            st.session_state["anticipated_start"] = session_selectbox(
                key="anticipated_start",
                label="Anticipated Begin Year",
                help="Expected year work begins.",
                options=st.session_state.get("years", [""]),
                force_str=True,
            )

        with col11:
            st.session_state["anticipated_end"] = session_selectbox(
                key="anticipated_end",
                label="Anticipated End Year",
                help="Expected year work completes.",
                options=st.session_state.get("years", [""]),
                force_str=True,
            )

        # -------------------------
        # 5. AWARD INFORMATION
        # -------------------------
        st.markdown("<h5>5. AWARD INFORMATION</h5>", unsafe_allow_html=True)
        col12, col13 = st.columns(2)

        with col12:
            default_award_date = st.session_state.get("award_date")
            st.session_state["award_date"] = st.date_input(
                "Award Date",
                value=default_award_date,
                format="MM/DD/YYYY",
                key=widget_key("award_date", version),
            )

        with col13:
            st.session_state["award_fiscal_year"] = session_selectbox(
                key="award_fiscal_year",
                label="Awarded Fiscal Year",
                help="FY based on Oct–Sep cycle.",
                options=["", "2020", "2021", "2022", "2023", "2024", "2025",
                         "2026", "2027", "2028", "2029", "2030"],
                force_str=True,
            )

        st.session_state["contractor"] = st.text_input(
            "Awarded Contractor",
            value=st.session_state.get("contractor", ""),
            key=widget_key("contractor", version),
        )

        col15, col16, col17 = st.columns(3)
        with col15:
            st.session_state["awarded_amount"] = st.number_input(
                "Awarded Amount",
                value=float(st.session_state.get("awarded_amount") or 0),
                key=widget_key("awarded_amount", version),
            )
        with col16:
            st.session_state["current_contract_amount"] = st.number_input(
                "Current Contract Amount",
                value=float(st.session_state.get("current_contract_amount") or 0),
                key=widget_key("current_contract_amount", version),
            )
        with col17:
            st.session_state["amount_paid_to_date"] = st.number_input(
                "Amount Paid to Date",
                value=float(st.session_state.get("amount_paid_to_date") or 0),
                key=widget_key("amount_paid_to_date", version),
            )

        st.session_state["tenadd"] = st.date_input(
            "Tentative Advertise Date",
            value=st.session_state.get("tenadd"),
            format="MM/DD/YYYY",
            key=widget_key("tenadd", version),
        )

        # -------------------------
        # 6. DESCRIPTION
        # -------------------------
        st.markdown("<h5>6. DESCRIPTION</h5>", unsafe_allow_html=True)

        st.session_state["proj_desc"] = st.text_area(
            "Public Description ⮜",
            height=200,
            value=st.session_state.get("proj_desc", ""),
            max_chars=8000,
            key=widget_key("proj_desc", version),
        )

        # -------------------------
        # 7. WEB LINKS
        # -------------------------
        st.markdown("<h5>7. WEB LINKS</h5>", unsafe_allow_html=True)

        st.session_state["proj_web"] = st.text_input(
            "Project Website",
            value=st.session_state.get("proj_web", ""),
            key=widget_key("proj_web", version),
        )

        st.session_state["apex_mapper_link"] = st.text_input(
            "APEX Mapper",
            value=st.session_state.get("apex_mapper_link", ""),
            key=widget_key("apex_mapper_link", version),
        )

        st.session_state["email_signup"] = st.text_input(
            "Email Signup Link",
            value=st.session_state.get("email_signup", ""),
            key=widget_key("email_signup", version),
        )

        # -------------------------
        # 8. IMPACTED COMMUNITIES
        # -------------------------
        st.markdown("<h5>8. IMPACTED COMMUNITIES</h5>", unsafe_allow_html=True)
        st.session_state["impact_comm"] = impacted_comms_select()

        # -------------------------
        # SUBMIT
        # -------------------------
        submit = st.form_submit_button("Submit Information")

        if submit:
            required = {
                "Construction Year": st.session_state.get("construction_year"),
                "Public Project Name": st.session_state.get("proj_name"),
                "Public Description": st.session_state.get("proj_desc"),
            }

            missing = [k for k, v in required.items() if not v]

            if missing:
                for m in missing:
                    st.error(f"{m} Required")
                st.session_state["details_complete"] = False
            else:
                st.success("All necessary project information is now complete. Please continue.")
                st.session_state["details_complete"] = True
                st.session_state["project_details"] = required
