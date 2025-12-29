import streamlit as st
import re

def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def is_valid_phone(phone):
    return re.match(r'^\d{3}-\d{3}-\d{4}$', phone) is not None

def contacts_list():
    if "contacts" not in st.session_state:
        st.session_state["contacts"] = []
    if "ver" not in st.session_state:
        st.session_state["ver"] = 0  # input version

    v = st.session_state["ver"]

    role = st.selectbox(
        "Role",
        ["", "Design Manager", "Construction Manager", "Project Engineer", "Survey Contact"],
        key=f"role_{v}"
    )
    name = st.text_input("Name", key=f"name_{v}")
    c1, c2 = st.columns(2)
    with c1:
        email = st.text_input("Email", key=f"email_{v}")
    with c2:
        phone = st.text_input("Phone", key=f"phone_{v}")

    if st.button("Add Contact"):
        if name and email and phone:
            if not is_valid_email(email):
                st.error("❌ Please enter a valid email address.")
            elif not is_valid_phone(phone):
                st.error("❌ Phone must be in format XXX-XXX-XXXX.")
            else:
                st.session_state["contacts"].append({
                    "Role": role,
                    "Name": name,
                    "Email": email,
                    "Phone": phone
                })
                st.session_state["ver"] += 1  # new keys -> cleared inputs
                st.rerun()
        else:
            st.warning("⚠️ Please fill in all fields before adding.")

    st.write("")
    st.write("")

    st.markdown("<h5>Contacts List</h5>", unsafe_allow_html=True)
    # ✅ Updated logic: always display existing contacts if they are already there
    if st.session_state["contacts"]:
        for i, contact in enumerate(st.session_state["contacts"]):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"{contact['Role']} - {contact['Name']} ({contact['Email']}, {contact['Phone']})")
            with c2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state["contacts"].pop(i)
                    st.rerun()
    else:
        st.info("No contacts added yet.")
