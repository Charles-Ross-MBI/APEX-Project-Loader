
import streamlit as st
import datetime
import re
from typing import Optional

from agol_util import query_record, get_multiple_fields, select_record

# ======================================================
# Pull Central dictionary for AWP mappings
# Expect: st.session_state['awp_fields'] is a dict mapping:
#   save_key -> awp_session_key
# ======================================================
AWP_FIELDS = st.session_state.get("awp_fields", {})

# ======================================================
# Session state initialization
# ======================================================
for key, default in [
    ("prev_aashto_id", None),
    ("show_duplicate_dialog", False),
    ("duplicate_found", False),
    ("continue_w_duplicate", None),
    ("awp_saved_snapshot", None),

    # NEW: pending-save flow for duplicate dialog support
    ("awp_pending_save", False),
    ("pending_pname", ""),
    ("pending_cy", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''") if isinstance(value, str) else value


def _previous_construction_year(construction_year: str, mode: str = "CY") -> Optional[str]:
    """Return the previous construction year. Accepts 'CY2026' or 'CY(2026)'."""
    if not construction_year:
        return None

    if mode.upper() == "CY":
        s = construction_year.strip()
        m = re.search(r"^CY\((\d{4})\)$", s, flags=re.IGNORECASE)
        if m:
            return f"CY{int(m.group(1)) - 1}"

        m2 = re.search(r"^CY(\d{4})$", s, flags=re.IGNORECASE)
        if m2:
            return f"CY{int(m2.group(1)) - 1}"

        return None

    try:
        year = int(str(construction_year).strip())
        return str(year - 1)
    except Exception:
        return None


def compute_new_or_continuing(*, project_name: str, construction_year: str, set_session: bool = True) -> str:
    """Compute New/Continuing. set_session True only when safe to update widget key."""
    if not project_name or not construction_year:
        result = "New"
        if set_session:
            st.session_state["form_new_continuing_state"] = result
        return result

    prev_year = _previous_construction_year(construction_year, mode="CY")
    if not prev_year:
        result = "New"
        if set_session:
            st.session_state["form_new_continuing_state"] = result
        return result

    pname = _escape_sql_literal(project_name.strip())
    where = f"AWP_Proj_Name = '{pname}' AND Construction_Year = '{prev_year}'"
    rec = query_record(
        url=st.session_state["projects_url"],
        layer=0,
        where=where,
    )

    result = "Continuing" if rec else "New"
    if set_session:
        st.session_state["form_new_continuing_state"] = result
    return result


# ======================================================
# DUPLICATE CONFIRMATION DIALOG
# ======================================================
@st.dialog("WARNING")
def confirm_duplicate_dialog(pname, cy):
    st.markdown(
        f"""
        <div style="text-align:center; font-size:1.05rem; line-height:1.55;">
          <h3>⚠️ Potential Duplicate Detected</h3>
          A project named <b><code>{pname}</code></b> already exists for construction year <b><code>{cy}</code></b>.
          <br/><br/>
          <b>Do you want to continue saving anyway?</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        if st.button("Yes, continue", type="primary", use_container_width=True):
            # IMPORTANT: keep pending-save alive and mark user approved
            st.session_state["continue_w_duplicate"] = True
            st.session_state["show_duplicate_dialog"] = False
            st.session_state["awp_pending_save"] = True
            st.rerun()

    with c2:
        if st.button("No, cancel", use_container_width=True):
            st.session_state["continue_w_duplicate"] = False
            st.session_state["show_duplicate_dialog"] = False
            st.session_state["awp_pending_save"] = False
            st.rerun()


# ======================================================
# CSS for read-only styling
# ======================================================
_RO_CSS = """
<style>
.ro-field { margin-bottom: 0.75rem; }
.ro-label { font-size: 0.875rem; color: #6b7280; margin-bottom: 0.25rem; }
.ro-box {
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  color: #111827;
  font-size: 0.95rem;
  min-height: 38px;
  display: flex; align-items: center;
  word-break: break-word;
}
.ro-box.mono { font-variant-numeric: tabular-nums; }
.ro-box .placeholder { color: #9ca3af; }
.ro-box-textarea {
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  color: #111827;
  font-size: 0.95rem;
  min-height: 160px;
  white-space: pre-wrap;
  word-break: break-word;
  display: block;
}
.ro-box-textarea .placeholder { color: #9ca3af; }
</style>
"""


def fmt_date(val):
    if not val:
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%m/%d/%Y")
    try:
        d = datetime.datetime.fromisoformat(val).date()
        return d.strftime("%m/%d/%Y")
    except Exception:
        return str(val)


def fmt_currency(val):
    try:
        f = float(val)
        return f"${f:,.2f}"
    except Exception:
        return str(val) if val else ""


def ro(label, value, mono=False):
    safe_value = value if value not in (None, "") else '<span class="placeholder">—</span>'
    st.markdown(
        f"""
        <div class="ro-field">
          <div class="ro-label">{label}</div>
          <div class="ro-box{' mono' if mono else ''}">{safe_value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ro_cols(specs):
    for col, label, value, mono in specs:
        with col:
            ro(label, value, mono)


def normalize_awp(value):
    if value is None:
        return ""
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "" or cleaned.lower() == "none":
            return ""
        return cleaned
    return value


def ro_textarea(label, value):
    safe_value = value if value not in (None, "") else '<span class="placeholder">—</span>'
    st.markdown(
        f"""
        <div class="ro-field">
          <div class="ro-label">{label}</div>
          <div class="ro-box-textarea">{safe_value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ======================================================
# Review mode helpers
# ======================================================
def in_review_mode() -> bool:
    return (
        st.session_state.get("details_complete") is True
        and st.session_state.get("details_type") == "AASHTOWare Database"
    )


def awp_value(key: str, *, transform=None, normalize=True):
    """Resolve a value from session_state, using AWP_FIELDS mapping when available."""
    awp_key = AWP_FIELDS.get(key, key)

    val = st.session_state.get(awp_key)

    if val is None and isinstance(awp_key, str) and not awp_key.startswith("awp_"):
        val = st.session_state.get(f"awp_{awp_key.lower()}")

    if (val is None or val == "") and key in st.session_state:
        val = st.session_state.get(key)

    if transform:
        val = transform(val)

    if normalize:
        return normalize_awp(val)
    return val


def _capture_review_snapshot() -> dict:
    """Capture values displayed on this page so returning users see what they submitted."""
    ui_keys = [
        "awp_name",
        "awp_public_proj_name",
        "phase",
        "fed_proj_num",
        "iris",
        "stip",
        "proj_prac",
        "fund_type",
        "anticipated_start",
        "anticipated_end",
        "award_date",
        "award_fiscalyear",
        "contractor",
        "awarded_amount",
        "current_contract_amount",
        "amount_paid_to_date",
        "tenadd",
        "awp_proj_desc",
        "proj_desc",
        "proj_web",
        "apex_mapper_link",
        "email_signup",
    ]

    snap = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "aashto_label": st.session_state.get("aashto_label"),
        "aashto_id": st.session_state.get("aashto_id"),
        "construction_year": st.session_state.get("construction_year"),
        "new_continuing": st.session_state.get("new_continuing"),
        "ui": {},
    }

    for k in ui_keys:
        snap["ui"][k] = awp_value(k, transform=None, normalize=True)

    return snap


def display_value(key: str, *, transform=None, normalize=True):
    """Display value that prefers saved snapshot in review mode."""
    snap = st.session_state.get("awp_saved_snapshot")
    if in_review_mode() and isinstance(snap, dict):
        val = (snap.get("ui") or {}).get(key)
    else:
        val = awp_value(key, transform=None, normalize=normalize)

    if transform:
        val = transform(val)

    if normalize:
        return normalize_awp(val)
    return val


def init_form_defaults():
    """Initialize widget-backed keys BEFORE widgets are instantiated."""
    cy_list = st.session_state.get("construction_years", [])
    current_cy = f"CY{datetime.datetime.now().year}"
    if not cy_list:
        cy_list = [current_cy]

    if in_review_mode():
        saved_cy = st.session_state.get("construction_year")
        saved_nc = st.session_state.get("new_continuing")
        st.session_state["form_construction_year"] = saved_cy or (current_cy if current_cy in cy_list else cy_list[0])
        st.session_state["form_new_continuing_state"] = saved_nc or "New"
    else:
        if "form_construction_year" not in st.session_state or not st.session_state.get("form_construction_year"):
            st.session_state["form_construction_year"] = current_cy if current_cy in cy_list else cy_list[0]
        if "form_new_continuing_state" not in st.session_state or st.session_state.get("form_new_continuing_state") is None:
            st.session_state["form_new_continuing_state"] = "New"


def _recompute_new_continuing_callback():
    """Callback used by Construction Year widget (safe timing)."""
    awp_name_val = (st.session_state.get("awp_name") or "").strip()
    cy_val = (st.session_state.get("form_construction_year") or "").strip()
    if awp_name_val and cy_val:
        compute_new_or_continuing(project_name=awp_name_val, construction_year=cy_val, set_session=True)


# ======================================================
# AASHTOWARE SELECTION
# ======================================================
def _extract_global_id(p: dict):
    return p.get("GlobalId") or p.get("GlobalID") or p.get("globalid") or p.get("globalId")


def aashtoware_project():
    aashtoware = st.session_state["aashtoware_url"]

    projects = get_multiple_fields(aashtoware, 0, ["Name", "ProposalId", "StateProjectNumber", "GlobalId"])

    label_to_gid = {
        f"{p.get('StateProjectNumber', '')} – {p.get('Name', '')}": _extract_global_id(p)
        for p in projects
        if _extract_global_id(p)
    }

    labels = sorted(label_to_gid.keys())
    placeholder_label = "— Select a project —"
    labels = [placeholder_label] + labels

    widget_key = "awp_project_select"

    saved_label = st.session_state.get("aashto_label")
    if saved_label and widget_key not in st.session_state:
        st.session_state[widget_key] = saved_label

    prev_label = st.session_state.get(widget_key) or saved_label
    initial_index = labels.index(prev_label) if prev_label in labels else 0

    def _load_selected_project(selected_gid: str):
        record = select_record(aashtoware, 0, "GlobalID", selected_gid)
        if record and isinstance(record, list) and "attributes" in record[0]:
            attrs = record[0]["attributes"]
            for k, v in attrs.items():
                st.session_state[f"awp_{str(k).lower()}"] = v

    def _on_project_change():
        selected_label = st.session_state[widget_key]

        if selected_label == placeholder_label:
            st.session_state["aashto_label"] = None
            st.session_state["aashto_id"] = None
            st.session_state["aashto_selected_project"] = None
            st.session_state["awp_guid"] = None
            st.session_state["awp_update"] = "No"
            st.session_state["awp_saved_snapshot"] = None
            st.session_state["details_complete"] = False
            return

        selected_gid = label_to_gid.get(selected_label)
        prev_gid = st.session_state.get("aashto_id")

        st.session_state["aashto_label"] = selected_label
        st.session_state["aashto_id"] = selected_gid
        st.session_state["aashto_selected_project"] = selected_label
        st.session_state["awp_guid"] = selected_gid
        st.session_state["awp_update"] = "Yes"

        if selected_gid and selected_gid != prev_gid:
            _load_selected_project(selected_gid)

            # leaving review mode
            st.session_state["awp_saved_snapshot"] = None
            st.session_state["details_complete"] = False

            # reset widget-backed defaults (safe in callback)
            st.session_state["form_construction_year"] = f"CY{datetime.datetime.now().year}"
            st.session_state["form_new_continuing_state"] = "New"

    st.selectbox(
        "AASHTOWare Project List",
        labels,
        index=initial_index,
        key=widget_key,
        on_change=_on_project_change,
    )

    return st.session_state.get("aashto_label")


# ======================================================
# MAIN FORM
# ======================================================
def aashtoware_form():
    st.markdown(_RO_CSS, unsafe_allow_html=True)

    # Initialize widget keys BEFORE widgets
    init_form_defaults()

    st.markdown("<h5>Select Project (AASHTOWare)</h5>", unsafe_allow_html=True)
    aashtoware_project()

    if not st.session_state.get("aashto_id"):
        st.info("Please select a project to view AASHTOWare details.")
        return

    # ======================================================
    # If a duplicate dialog is pending, show it OUTSIDE save_clicked logic
    # ======================================================
    if st.session_state.get("show_duplicate_dialog"):
        confirm_duplicate_dialog(
            st.session_state.get("pending_pname", ""),
            st.session_state.get("pending_cy", ""),
        )
        st.stop()

    if in_review_mode():
        st.success("Saved. You are viewing the submitted values for this step.")

    with st.container(border=True):
        # ======================================================
        # 1. Construction Year + New/Continuing
        # ======================================================
        st.markdown("<h5>1. Construction Year</h5>", unsafe_allow_html=True)

        cy_list = st.session_state.get("construction_years", [])
        current_cy = f"CY{datetime.datetime.now().year}"
        if not cy_list:
            cy_list = [current_cy]

        cy_val = st.session_state.get("form_construction_year") or (current_cy if current_cy in cy_list else cy_list[0])
        if cy_val not in cy_list:
            cy_list = [cy_val] + cy_list

        c1, c2 = st.columns(2)
        with c1:
            st.selectbox(
                "Select Construction Year",
                cy_list,
                index=cy_list.index(cy_val) if cy_val in cy_list else 0,
                key="form_construction_year",
                on_change=_recompute_new_continuing_callback,
            )

        with c2:
            options = ["", "New", "Continuing"]
            nc_val = st.session_state.get("form_new_continuing_state", "")
            idx = options.index(nc_val) if nc_val in options else 0
            st.selectbox(
                "New or Continuing?",
                options,
                index=idx,
                key="form_new_continuing_state",
            )

        st.write("")
        st.write("")

        # ======================================================
        # 2. Project Name
        # ======================================================
        st.markdown("<h5>2. Project Name</h5>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        ro_cols([
            (col1, "AASHTOWare Project Name", display_value("awp_name"), False),
            (col2, "Public Project Name", display_value("awp_public_proj_name"), False),
        ])

        st.write("")
        st.write("")

        # ======================================================
        # 3. Phase & Project Identifiers
        # ======================================================
        st.markdown("<h5>3. Phase & Project Identifiers</h5>", unsafe_allow_html=True)
        ro("Phase", display_value("phase"), False)

        col_fp1, col_fp2, col_fp3 = st.columns(3)
        ro_cols([
            (col_fp1, "Federal Project Number", display_value("fed_proj_num"), True),
            (col_fp2, "IRIS", display_value("iris"), True),
            (col_fp3, "STIP", display_value("stip"), True),
        ])

        col_ft1, col_ft2 = st.columns(2)
        ro_cols([
            (col_ft1, "Project Practice", display_value("proj_prac"), False),
            (col_ft2, "Funding Type", display_value("fund_type"), False),
        ])

        st.write("")
        st.write("")

        # ======================================================
        # 4. Timeline
        # ======================================================
        st.markdown("<h5>4. Timeline</h5>", unsafe_allow_html=True)
        col10, col11 = st.columns(2)
        ro_cols([
            (col10, "Anticipated Begin Year", display_value("anticipated_start"), True),
            (col11, "Anticipated End Year", display_value("anticipated_end"), True),
        ])

        st.write("")
        st.write("")

        # ======================================================
        # 5. Award Information
        # ======================================================
        st.markdown("<h5>5. Award Information</h5>", unsafe_allow_html=True)
        col12, col13 = st.columns(2)
        ro_cols([
            (col12, "Award Date", display_value("award_date", transform=fmt_date), True),
            (col13, "Awarded Fiscal Year", display_value("award_fiscalyear"), True),
        ])

        ro("Awarded Contractor", display_value("contractor"), False)

        col15, col16, col17 = st.columns(3)
        ro_cols([
            (col15, "Awarded Amount", display_value("awarded_amount", transform=fmt_currency), True),
            (col16, "Current Contract Amount", display_value("current_contract_amount", transform=fmt_currency), True),
            (col17, "Amount Paid to Date", display_value("amount_paid_to_date", transform=fmt_currency), True),
        ])

        ro("Tentative Advertise Date", display_value("tenadd", transform=fmt_date), True)

        st.write("")
        st.write("")

        # ======================================================
        # 6. Description
        # ======================================================
        st.markdown("<h5>6. Description</h5>", unsafe_allow_html=True)
        ro_textarea("AASHTOWare Description", display_value("awp_proj_desc"))
        ro_textarea("Public Description", display_value("proj_desc"))

        st.write("")
        st.write("")

        # ======================================================
        # 7. Web Links
        # ======================================================
        st.markdown("<h5>7. Web Links</h5>", unsafe_allow_html=True)
        ro("Project Website", display_value("proj_web"))
        ro("APEX Mapper", display_value("apex_mapper_link"))
        ro("Email Signup Link", display_value("email_signup"))

        st.write("")
        st.write("")

        # ======================================================
        # SAVE BUTTON (supports duplicate dialog continuation)
        # ======================================================
        save_label = "Save AASHTOWare Details" if not in_review_mode() else "Re-save AASHTOWare Details"
        save_clicked = st.button(save_label, use_container_width=True)

        # If user clicked save, begin a pending-save transaction
        if save_clicked:
            cy = (st.session_state.get("form_construction_year") or "").strip()
            if not cy:
                st.error("⚠️ Construction Year is required to continue.")
                st.stop()

            pname = (st.session_state.get("awp_name") or "").strip()
            st.session_state["pending_pname"] = pname
            st.session_state["pending_cy"] = cy

            # reset dialog flags for a new save attempt
            st.session_state["continue_w_duplicate"] = None
            st.session_state["duplicate_found"] = False
            st.session_state["awp_pending_save"] = True

            # duplicate check
            if pname and cy:
                safe_pname = pname.replace("'", "''")
                where = f"AWP_Proj_Name = '{safe_pname}' AND Construction_Year = '{cy}'"
                rec = query_record(url=st.session_state["projects_url"], layer=0, where=where)
                if rec:
                    st.session_state["duplicate_found"] = True
                    st.session_state["show_duplicate_dialog"] = True
                    confirm_duplicate_dialog(pname, cy)
                    st.stop()

        # If user cancelled from dialog earlier
        if st.session_state.get("continue_w_duplicate") is False:
            st.session_state["awp_pending_save"] = False
            st.info(
                "Save cancelled. You can either locate your project in the "
                "AASHTOWare Editor app, or select another project from the list above."
            )
            st.stop()

        # FINAL: perform save if a pending-save exists and either:
        #  - no duplicate was found, OR
        #  - user approved continuing with duplicate
        proceed_with_save = (
            st.session_state.get("awp_pending_save") is True
            and (
                st.session_state.get("duplicate_found") is False
                or st.session_state.get("continue_w_duplicate") is True
            )
        )

        if proceed_with_save:
            # Persist identifiers
            st.session_state["aashto_id"] = st.session_state.get("aashto_id")
            st.session_state["aashto_label"] = st.session_state.get("aashto_label")

            # Persist construction year & new/continuing into saved keys
            st.session_state["construction_year"] = st.session_state.get("form_construction_year")
            st.session_state["new_continuing"] = st.session_state.get("form_new_continuing_state")

            # Assign all AWP-related values via the mapping
            for save_key, awp_key in AWP_FIELDS.items():
                st.session_state[save_key] = st.session_state.get(awp_key)

            # Mark completion and capture snapshot for review mode
            st.session_state["details_complete"] = True
            st.session_state["details_type"] = "AASHTOWare Database"
            st.session_state["awp_saved_snapshot"] = _capture_review_snapshot()

            # Clear pending transaction + dialog flags
            st.session_state["awp_pending_save"] = False
            st.session_state["duplicate_found"] = False
            st.session_state["continue_w_duplicate"] = None
            st.session_state["show_duplicate_dialog"] = False

            st.success("AASHTOWare details saved. You may continue to the next step or return later to review.")
