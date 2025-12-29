# review.py
import streamlit as st
from streamlit_folium import st_folium
import folium
from map import set_bounds_route, set_zoom

# # ----------------------------------------------------------------------
# # Dialog for confirmation
# # ----------------------------------------------------------------------
# @st.dialog("Confirm Submission")
# def confirm_submit_dialog():
#     st.write(
#         "You're about to submit this project to the APEX database. "
#         "Please confirm all information has been reviewed."
#     )
#     st.write("**This action cannot be undone from this workflow.**")

#     col_ok, col_cancel = st.columns(2)

#     with col_ok:
#         if st.button("Confirm & Submit", type="primary"):
#             st.session_state["show_confirm_dialog"] = False
#             st.session_state.step = 6
#             st.rerun()
        

#     with col_cancel:
#         if st.button("Cancel", type="secondary"):
#             st.session_state["show_confirm_dialog"] = False
#             st.rerun()




# ----------------------------------------------------------------------
# Navigation helpers
# ----------------------------------------------------------------------
def goto_step(target_step: int):
    """Set the wizard step and rerun immediately."""
    st.session_state["step"] = target_step
    st.session_state["scroll_to_top"] = True
    st.rerun()


def header_with_edit(title: str, target_step: int, *, help: str = None):
    """Render a left-aligned section header with a right-aligned EDIT button."""
    left, right = st.columns([1, 0.18])
    with left:
        st.markdown(f"<h4 style='margin-bottom:0'>{title}</h4>", unsafe_allow_html=True)
    with right:
        is_clicked = st.button("✏️ EDIT", help=help, key=f"edit_{target_step}")
    if is_clicked:
        st.session_state["step"] = target_step
        st.session_state["scroll_to_top"] = True
        # Streamlit reruns automatically after button click


# ----------------------------------------------------------------------
# Review page
# ----------------------------------------------------------------------
def review_information():
    """
    Render the review page with section headers and edit buttons.
    """

    # --- Project Name ---
    project_name = st.session_state.get("proj_name", "")
    awp_proj_name = st.session_state.get("awp_proj_name", "—")
    display_name = project_name if project_name else awp_proj_name
    st.markdown(f"<h3>{display_name}</h3>", unsafe_allow_html=True)


    # --- Map of Location ---
    header_with_edit("PROJECT LOCATION", target_step=4, help="Edit Project Loaction")
    if "selected_point" in st.session_state and st.session_state["selected_point"]:
        lat, lon = st.session_state["selected_point"]
        m = folium.Map(location=[lat, lon], zoom_start=12)
        folium.Marker(location=[lat, lon]).add_to(m)
        st_folium(m, width=700, height=400)

    elif "selected_route" in st.session_state and st.session_state["selected_route"]:
        BLUE = "#3388ff"
        coords = st.session_state['selected_route']
        bounds = set_bounds_route(coords)
        m = folium.Map(location=[coords[0][1], coords[0][0]], zoom_start=set_zoom(bounds))
        folium.PolyLine(
            coords,
            color=BLUE,
            weight=8,
            opacity=1
        ).add_to(m)
        m.fit_bounds(set_bounds_route( bounds))
        st_folium(m, width=700, height=400)

    else:
        st.info("No location data available to display a map.")


    st.write("")
    st.write("")

    # --- Project Information ---
    header_with_edit("PROJECT INFORMATION", target_step=2, help="Edit all project information")

    # Identification
    with st.expander("Identification", expanded=True):
        st.markdown(f"**Project Name:** {st.session_state.get('proj_name','')}")
        col1, col2 = st.columns(2)
        col1.markdown(f"**Construction Year:** {st.session_state.get('construction_year','')}")
        col2.markdown(f"**Phase:** {st.session_state.get('phase','')}")
        col1.markdown(f"**IRIS:** {st.session_state.get('iris','')}")
        col2.markdown(f"**STIP:** {st.session_state.get('stip','')}")
        col1.markdown(f"**Federal Project Number:** {st.session_state.get('fed_proj_num','')}")
        col2.markdown(f"**Practice:** {st.session_state.get('proj_prac','')}")
        
    # Timeline
    with st.expander("Timeline", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**Anticipated Start:** {st.session_state.get('anticipated_start','')}")
        col2.markdown(f"**Anticipated End:** {st.session_state.get('anticipated_end','')}")

    # Funding
    with st.expander("Funding", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**Fund Type:** {st.session_state.get('fund_type','')}")
        col2.markdown(f"**Fund Amount:** {st.session_state.get('fund_amount','')}")
        col1.markdown(f"**Awarded:** {st.session_state.get('awarded','')}")
        col2.markdown(f"**Award Fiscal Year:** {st.session_state.get('award_fiscal_year','')}")
        col1.markdown(f"**Award Date:** {st.session_state.get('award_date','')}")
        col2.markdown(f"**Contractor:** {st.session_state.get('contractor','')}")
        col1.markdown(
            "**Awarded Amount:** "
            + (("${:,.0f}".format(float(st.session_state.get("awarded_amount", 0))))
               if st.session_state.get("awarded_amount") not in (None, "") else "")
        )
        col2.markdown(
            "**Current Contract Amount:** "
            + (("${:,.0f}".format(float(st.session_state.get("current_contract_amount", 0))))
               if st.session_state.get("current_contract_amount") not in (None, "") else "")
        )
        col1.markdown(
            "**Amount Paid to Date:** "
            + (("${:,.0f}".format(float(st.session_state.get("amount_paid_to_date", 0))))
               if st.session_state.get("amount_paid_to_date") not in (None, "") else "")
        )
        col2.markdown(f"**Tenative Advertise Date:** {st.session_state.get('tenadd','')}")


    # Narrative
    with st.expander("Purpose, Description & Impact", expanded=True):
        
        if st.session_state.get("info_option") == "AASHTOWare Database":
            st.markdown(f"**AASHTOWare Description:**\n\n{st.session_state.get('awp_proj_desc','')}")
            st.markdown(f"**Public Project Description:**\n\n{st.session_state.get('proj_desc','')}")
        else:
            st.markdown(f"**Project Description:**\n\n{st.session_state.get('proj_desc','')}")
        st.markdown(f"**Project Purpose:**\n\n{st.session_state.get('proj_purp','')}")
        st.markdown(f"**Current Traffic Impact:**\n\n{st.session_state.get('proj_impact','')}")


    # Status & Links
    with st.expander("Links", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**Project Website:** {st.session_state.get('proj_web','—')}")
        col2.markdown(f"**APEX Mapper Link:** {st.session_state.get('apex_mapper_link','—')}")
        col1.markdown(f"**APEX Info Sheet:** {st.session_state.get('apex_infosheet','—')}")

    
     # Geography
    with st.expander("Geography", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**House Districts:** {st.session_state.get('house_string','')}")
        col2.markdown(f"**Senate Districts:** {st.session_state.get('senate_string','')}")
        col1.markdown(f"**Borough/Census Area:** {st.session_state.get('borough_string','')}")
        col2.markdown(f"**DOT&PF Region:** {st.session_state.get('region_string','')}")

    # Routes
    if st.session_state['selected_route']:
        with st.expander("Routes", expanded=True):
            st.markdown(f"**Route IDs:** {st.session_state.get('route_ids','')}")
            st.markdown(f"**Route Names:** {st.session_state.get('route_names','')}")
            

    # Impacted Communities
    with st.expander("Impacted Communities", expanded=True):
        impact_comm = st.session_state.get("impact_comm_names", "")
        if isinstance(impact_comm, list):
            impact_comm_display = ", ".join(str(item) for item in impact_comm) if impact_comm else ""
        else:
            impact_comm_display = impact_comm
        st.markdown(f"**Communities:** {impact_comm_display}")

    

    st.write("")
    st.write("")

    # --- Contacts ---
    header_with_edit("CONTACTS", target_step=3, help="Edit project contacts")
    contacts = st.session_state.get("contacts", [])
    if contacts:
        if isinstance(contacts[0], dict):
            st.table(contacts)
        else:
            for contact in contacts:
                st.write(contact)
    else:
        st.write("— No contacts provided —")

    st.write("")
    st.write("")

    # # --- Submit button ---
    # if st.button("SUBMIT PROJECT", type="primary"):
    #     st.session_state["show_confirm_dialog"] = True
        
    #     confirm_submit_dialog()
