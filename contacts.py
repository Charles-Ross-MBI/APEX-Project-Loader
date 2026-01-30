
"""
===============================================================================
CONTACTS CAPTURE (STREAMLIT) — PROJECT CONTACT LIST UI
===============================================================================

Purpose:
    Provides a small Streamlit UI for collecting project contacts (role/name/
    email/phone) into st.session_state['project_contacts'].

Key behaviors:
    - Validates:
        * Email format (simple regex)
        * Phone format (XXX-XXX-XXXX)
    - Appends validated contacts to session_state as dictionaries with keys:
        'Role', 'Name', 'Email', 'Phone'
    - Uses a "versioned input key" pattern (session_state['ver']) so that after
      adding a contact, the widget keys change and inputs clear automatically.
    - Displays the current contact list and supports removing individual entries.

Session-state dependencies:
    - 'project_contacts': list of contact dicts (created if missing)
    - 'ver': integer used to version Streamlit widget keys (created if missing)

Notes:
    - This module intentionally uses st.rerun() after add/remove so that the UI
      refreshes immediately and widget state is consistent.
    - Regex validation is deliberately strict for phone numbers and minimal for
      email addresses (sufficient for basic UI validation).

===============================================================================
"""

import streamlit as st
import re

# =============================================================================
# VALIDATORS (INPUT SANITY CHECKS)
# =============================================================================
# These functions provide lightweight format validation for user-entered fields.
# They are UI-guards only (not authoritative validation).
# =============================================================================
def is_valid_email(email):
    """Return True if email looks like a basic 'name@domain.tld' pattern."""
    return re.match(r'^[\w\.\-]+@[\w\.\-]+\.\w+$', email) is not None


def is_valid_phone(phone):
    """Return True if phone is in strict 'XXX-XXX-XXXX' format."""
    return re.match(r'^\d{3}\-\d{3}\-\d{4}$', phone) is not None


# =============================================================================
# UI ENTRYPOINT: CONTACTS LIST BUILDER
# =============================================================================
# contacts_list():
#   - Initializes required session_state keys
#   - Renders contact entry widgets (role/name/email/phone)
#   - Validates and appends to st.session_state['project_contacts']
#   - Displays existing contacts and supports removal
#
# IMPORTANT:
#   This function is intentionally stateful and relies on Streamlit reruns.
# =============================================================================
def contacts_list():
    # -------------------------------------------------------------------------
    # Session initialization (ensures expected keys exist)
    # -------------------------------------------------------------------------
    if "project_contacts" not in st.session_state:
        st.session_state["project_contacts"] = []
    if "ver" not in st.session_state:
        st.session_state["ver"] = 0

    # Input version:
    # Streamlit widget keys persist; bumping 'ver' forces new widget keys so the
    # inputs clear after adding a contact.
    v = st.session_state["ver"]

    # -------------------------------------------------------------------------
    # Contact entry controls
    # -------------------------------------------------------------------------
    role = st.selectbox(
        "Role",
        ["", "Design Manager", "Construction Manager", "Project Engineer", "Survey Contact"],
        key=f"role_{v}"
    )
    name = st.text_input("Name", key=f"name_{v}")

    c1, c2 = st.columns(2)
    with c1:
        email = st.text_input(
            "Email",
            key=f"email_{v}",
            help="Enter email in valid email format (e.g., name@example.com)."
        )
    with c2:
        phone = st.text_input(
            "Phone",
            key=f"phone_{v}",
            help="Enter the phone number in standard format (e.g., XXX‑XXX‑XXXX)."
        )

    # -------------------------------------------------------------------------
    # Add contact action + validation
    # -------------------------------------------------------------------------
    if st.button("ADD CONTACT", use_container_width=True):
        # Require all fields before validating formats.
        if name and email and phone:
            if not is_valid_email(email):
                st.error("❌ Please enter a valid email address.")
            elif not is_valid_phone(phone):
                st.error("❌ Phone must be in format XXX-XXX-XXXX.")
            else:
                # Persist contact in session_state
                st.session_state["project_contacts"].append({
                    "Role": role,
                    "Name": name,
                    "Email": email,
                    "Phone": phone
                })

                # Version bump => new keys => cleared inputs on rerun
                st.session_state["ver"] += 1  # new keys -> cleared inputs
                st.rerun()
        else:
            st.warning("⚠️ Please fill in all fields before adding.")

    # -------------------------------------------------------------------------
    # Current contacts display + removal controls
    # -------------------------------------------------------------------------
    st.write("")
    st.write("")
    st.markdown(
        """
###### Contacts List

""",
        unsafe_allow_html=True
    )

    # ✅ Updated logic: always display existing contacts if they are already there
    if st.session_state["project_contacts"]:
        for i, contact in enumerate(st.session_state["project_contacts"]):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"{contact['Role']} - {contact['Name']} ({contact['Email']}, {contact['Phone']})")
            with c2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state["project_contacts"].pop(i)
                    st.rerun()
    else:
        st.info("No contacts added yet.")
