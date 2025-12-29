
import streamlit as st
from streamlit_folium import st_folium
from streamlit_scroll_to_top import scroll_to_here
import folium
from folium.plugins import Draw, Geocoder, Search
import geopandas as gpd
import tempfile
import zipfile
import time

from map import add_small_geocoder
from shapefile_upload import point_shapefile, polyline_shapefile
from enter_value_upload import enter_latlng, enter_mileposts
from draw_upload import draw_point, draw_line
from details_form import project_details_form
from aashtoware import aashtoware_project, aashtoware_point
from contacts import contacts_list
from instructions import instructions
from review import review_information
from district_queries import run_district_queries
from payloads import project_payload, communities_payload, geometry_payload, contacts_payload, geography_payload
from agol_util import AGOLDataLoader, format_guid, delete_project


st.set_page_config(page_title="Alaska DOT&PF - APEX Project Creator", page_icon="📝", layout="centered")

# Base overview map
m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)
add_small_geocoder(m)


# Initialize session state
defaults = {
    "step": 1,
    "selected_point": None,
    "selected_route": None,
    "project_type": None,
    "geo_option": None,
    "info_option": None,
    "aashto_id": "",
    "project_name": "",
    "project_description": "",
    "project_category": None,
    "project_contacts": None,
    'details_complete': False
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

import streamlit as st
from streamlit_scroll_to_top import scroll_to_here

TOTAL_STEPS = 6
if "step" not in st.session_state:
    st.session_state.step = 1

# --- Initialize scroll flags ---
if "scroll_to_top" not in st.session_state:
    st.session_state.scroll_to_top = False

# --- Handle scroll action ---
if st.session_state.scroll_to_top:
    scroll_to_here(0, key="top")  # 0 = instant scroll
    st.session_state.scroll_to_top = False  # reset after scrolling

# --- Navigation functions ---
def next_step():
    if st.session_state.step < TOTAL_STEPS:
        st.session_state.step += 1
    st.session_state.scroll_to_top = True  # trigger scroll

def prev_step():
    if st.session_state.step > 1:
        st.session_state.step -= 1
    st.session_state.scroll_to_top = True  # trigger scroll



# Header and progress
st.title("📝 ADD NEW APEX PROJECT")
st.markdown("##### COMPLETE STEPS TO ADD A NEW PROJECT TO THE APEX DATABASE")
st.progress(st.session_state.step / TOTAL_STEPS)
st.caption(f"Step {st.session_state.step} of {TOTAL_STEPS}")
st.write("")

# Step content
if st.session_state.step == 1:
    st.header("Welcome")
    st.write("""
        ##### Alaska DOT&PF APEX Project Creator

        Follow these steps to create a new project in the system:

        **Step 1: Enter Project Information**  
        Provide project details either by pulling data from the AASHTOWare database or entering them manually.  
        Review and complete all required fields to ensure accuracy.

        ---

        **Step 2: Add Project Contacts**  
        Assign roles to project contacts and enter available details such as name, email, and phone.  
        Use **Add Contact** to build a list of contacts, and remove any entries if needed.  
        Confirm that all necessary contacts are included before continuing.

        ---

        **Step 3: Upload Geospatial Data**  
        Select the project type (**Site** or **Route**) and upload or create the corresponding geometry.  
        Choose the upload method that best matches your data (shapefile, coordinates, or map input).  
        Verify that the geometry is correct and reflects your project scope.

        ---

        **Step 4: Review and Confirm**  
        Check all project information, contacts, and geospatial data for completeness and accuracy.  
        Make any adjustments before finalizing.

        ---

        **Step 5: Submit Project**  
        Click **Submit** to validate the data.  
        Once approved, the project will be saved to the database and you can proceed to the next workflow stage.
        """)

    st.info("Click **Next** to begin.")

elif st.session_state.step == 2:
    st.markdown("### PROJECT INFORMATION 📄")
    st.write(
    "Choose either the AASHTOWare source or User Input to provide project details. "
    "Complete the form, then click **Submit** to save and continue."
    )

    instructions("Project Information")

    st.write("")
    st.write("")

    project_details_form()


elif st.session_state.step == 3:
    st.markdown("### ADD CONTACTS 👥")
    st.write(
    "Complete the contact form by adding all available project contacts. "
    "Once the list is finalized, proceed to the next step."
    )

    instructions("Contacts")

    st.write("")
    st.write("")

    st.markdown("<h5>Contact Information</h5>", unsafe_allow_html=True)
    contacts_list()



elif st.session_state.step == 4:
    st.markdown("### LOAD GEOMETRY 📍")
    st.write(
        "Select the project type and provide its geometry. "
        "After choosing a type, you will see the available upload methods. "
        "Review the instructions below for detailed guidance before continuing."
    )

    instructions("Load Geometry")

    st.write("")
    st.write("")

    # --- Choose Site or Route ---
    st.markdown("<h5>Choose Project Type</h5>", unsafe_allow_html=True)
    st.session_state['project_type'] = st.segmented_control(
        "Select Project Type:",
        ["Site Project", "Route Project"],
        default=st.session_state.get('project_type', None)  # persist previous choice
    )

    # If project_type changed, clear all district values and geometry
    if st.session_state.get("prev_project_type") != st.session_state['project_type']:
        st.session_state.house_string = ""
        st.session_state.senate_string = ""
        st.session_state.borough_string = ""
        st.session_state.region_string = ""
        st.session_state.selected_point = None
        st.session_state.selected_route = None
        st.session_state['option'] = None
        st.session_state.prev_project_type = st.session_state['project_type']

    st.write("")
    if st.session_state['project_type']:
        st.markdown("<h5>Upload Geospatial Data</h5>", unsafe_allow_html=True)

        show_awp_option = (
        st.session_state['project_type'].startswith("Site")
        and st.session_state.get("aashto_selected_project")
        and st.session_state.get("awp_dcml_latitude")
        and st.session_state.get("awp_dcml_longitude")
    )

        # --- Site Project ---
        if st.session_state['project_type'].startswith("Site"):
            options = ["Upload Shapefile", "Enter Latitude/Longitude", "Select Point on Map"]
            if show_awp_option:
                options.append("AASHTOWare")

            # Ensure default is valid
            prev_option = st.session_state.get('option')
            if prev_option not in options:
                prev_option = options[0]

            st.session_state['option'] = st.segmented_control(
                "Choose Upload Method:",
                options,
                default=prev_option
            )
            option = st.session_state['option']

            if st.session_state.get("geo_option") != option:
                st.session_state.selected_point = None
                st.session_state.selected_route = None
            st.session_state.geo_option = option

            if option == "AASHTOWare":
                aashtoware_point(st.session_state.get("awp_dcml_latitude"), st.session_state.get("awp_dcml_longitude"))
                st.session_state.selected_route = None
            elif option == "Upload Shapefile":
                point_shapefile()
                st.session_state.selected_route = None
            elif option == "Select Point on Map":
                draw_point()
                st.session_state.selected_route = None
            elif option == "Enter Latitude/Longitude":
                enter_latlng()
                st.session_state.selected_route = None

        # --- Route Project ---
        else:
            options = ["Upload Shapefile", "Enter Mileposts", "Draw Route on Map"]

            # Ensure default is valid
            prev_option = st.session_state.get('option')
            if prev_option not in options:
                prev_option = options[0]

            st.session_state['option'] = st.segmented_control(
                "Choose Upload Method:",
                options,
                default=prev_option
            )
            option = st.session_state['option']

            if st.session_state.get("geo_option") != option:
                st.session_state.selected_point = None
                st.session_state.selected_route = None
            st.session_state.geo_option = option

            if option == "Upload Shapefile":
                polyline_shapefile()
                st.session_state.selected_point = None
            elif option == "Enter Mileposts":
                enter_mileposts()
                st.session_state.selected_point = None
            elif option == "Draw Route on Map":
                draw_line()
                st.session_state.selected_point = None

        # --- Track previous values ---
        if "prev_selected_point" not in st.session_state:
            st.session_state.prev_selected_point = None
        if "prev_selected_route" not in st.session_state:
            st.session_state.prev_selected_route = None

        point_val = st.session_state.get("selected_point")
        route_val = st.session_state.get("selected_route")

        point_changed = point_val is not None and point_val != st.session_state.prev_selected_point
        route_changed = route_val is not None and route_val != st.session_state.prev_selected_route

        if point_changed or route_changed:
            run_district_queries()
            st.session_state.prev_selected_point = point_val
            st.session_state.prev_selected_route = route_val

        # --- Collect values ---
        house_val = st.session_state.get('house_string')
        senate_val = st.session_state.get('senate_string')
        borough_val = st.session_state.get('borough_string')
        region_val = st.session_state.get('region_string')
        route_ids = st.session_state.get('route_ids', None)
        route_names = st.session_state.get('route_names', None)

        # --- Show expander if geometry has content ---
        if st.session_state['project_type'].startswith("Site") and point_val is not None and any([house_val, senate_val, borough_val, region_val]):
            with st.expander("PROJECT GEOGRAPHIES", expanded=True):
                col1, col2 = st.columns(2)
                col1.markdown(f"**House Districts:** {house_val or '—'}")
                col2.markdown(f"**Senate Districts:** {senate_val or '—'}")
                col1.markdown(f"**Boroughs:** {borough_val or '—'}")
                col2.markdown(f"**Regions:** {region_val or '—'}")

        elif st.session_state['project_type'].startswith("Route") and route_val is not None and any([house_val, senate_val, borough_val, region_val]):
            with st.expander("PROJECT GEOGRAPHIES", expanded=True):
                col1, col2 = st.columns(2)
                col1.markdown(f"**House Districts:** {house_val or '—'}")
                col2.markdown(f"**Senate Districts:** {senate_val or '—'}")
                col1.markdown(f"**Boroughs:** {borough_val or '—'}")
                col2.markdown(f"**Regions:** {region_val or '—'}")
                st.markdown(f"**Route IDs:** {route_ids}")
                st.markdown(f"**Route Names:** {route_names} ")



elif st.session_state.step == 5:
    st.markdown("### REVIEW & SUBMIT ✔️")
    st.write(
    "Review all submitted project information carefully. "
    "Confirm details are correct before pressing Submit. "
    "Once submitted, the project will be loaded into the APEX Database.")

    instructions("Review")

    st.write("")
    st.write("")

    review_information()

    st.write("")
    



elif st.session_state.step == 6:
    st.markdown("### UPLOAD PROJECT🚀")
    st.write(
        "Select your name from the dropdown. If not listed, choose **Other** and enter it in the text box. "
        "Then click **UPLOAD TO APEX** to transfer your project data. "
        "Each step shows a success message if completed, or errors to fix if it fails. "
        "Once all steps succeed, your project will be stored in the APEX Database."
    )


    instructions("Upload Project")

    st.write("")
    st.write("")

    st.markdown("<h5>Submitter Name</h5>", unsafe_allow_html=True)
    # 🔽 Dropdown list of names 
    names = ["",
             "Christopher Butrico",
             "Riley Conley", 
             "Casey DunnGossin",
             "Caitlin Frye", 
             "Jennifer Gross",
             "Alexander Hutcherson",
             "Karin McGillivray", 
             "Charles Ross",
             "Andrew Tuell",
             "Callan VanNuys",
             "Malia Walters",
             "Sara Wazir",
             "Gretchen WeissBrooks",
             "Hannah White", 
             "Lauren Winkler", 
             "Other"] 
    selected_name = st.selectbox("Submitted by:", names, index=0)

    # If "Other" is chosen, show a text box to override 
    if selected_name == "Other": 
        custom_name = st.text_input("Please type your name:") 
        
        if custom_name.strip(): 
            st.session_state['submitted_by'] = custom_name

    else: st.session_state['submitted_by'] = selected_name

    st.write("")
    st.markdown("<h5>Upload Project</h5>", unsafe_allow_html=True)
    # ✅ Back + Upload buttons appear together BEFORE upload starts
    col_back, col_gap, col_upload, _ = st.columns([1.5, 0.2, 3, 6])   # wider upload column

    if not st.session_state.get("upload_clicked", False):

        # Back button (left)
        with col_back:
            st.button("⬅️ Back", on_click=prev_step, key="step6_back_btn")

        # Upload button (right) — now inside the SAME row
        with col_upload:
            if st.button("UPLOAD TO APEX", type="primary", key="step6_upload_btn"):
                st.session_state.upload_clicked = True
                st.rerun()

    else:
        # ✅ After upload starts → hide both buttons
        with col_back:
            st.empty()
        with col_upload:
            st.empty()



    # --- Upload Button Logic (unchanged) ---
    if st.session_state.get("upload_clicked", False):

        apex_url = "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/service_0d036ae7c0a7424088ee565727d1bb66/FeatureServer"
        spinner_container = st.empty()

        # --- Upload Project ---
        with spinner_container, st.spinner("Loading Project to APEX..."):
            try:
                payload_project = project_payload()
                projects_layer = 0
                load_project = (
                    AGOLDataLoader(url=apex_url, layer=projects_layer).add_features(payload_project)
                    if payload_project
                    else {"success": False, "message": "Failed to Load Project to APEX DB"}
                )
            except Exception as e:
                load_project = {"success": False, "message": f"Project payload error: {e}"}

        spinner_container.empty()

        if load_project.get("success"):
            st.session_state["apex_globalid"] = format_guid(load_project["globalids"])
            st.success("LOAD PROJECT: SUCCESS ✅")
        else:
            st.error(f"LOAD PROJECT: FAILURE ❌ {load_project.get('message')}")
            st.session_state.setdefault("step_failures", []).append(load_project.get("message"))

        # --- Upload Geometry ---
        with spinner_container, st.spinner("Loading Project Geometry to APEX..."):
            try:
                payload_geometry = geometry_payload(st.session_state.get("apex_globalid"))

                if st.session_state.get("selected_point"):
                    geometry_layer = 1
                elif st.session_state.get("selected_route"):
                    geometry_layer = 2

                load_geometry = (
                    AGOLDataLoader(url=apex_url, layer=geometry_layer).add_features(payload_geometry)
                    if payload_geometry
                    else {"success": False, "message": "Failed to Load Project geometry to APEX DB"}
                )
            except Exception as e:
                load_geometry = {"success": False, "message": f"Project Geometry payload error: {e}"}

        spinner_container.empty()

        if load_geometry.get("success"):
            st.success("LOAD GEOMETRY: SUCCESS ✅")
        else:
            st.error(f"LOAD GEOMETRY: FAILURE ❌  {load_geometry.get('message')}")
            st.session_state.setdefault("step_failures", []).append(load_geometry.get("message"))

        # --- Upload Communities ---
        with spinner_container, st.spinner("Loading Communities to APEX..."):
            try:
                payload_communities = communities_payload(st.session_state.get("apex_globalid"))
                communities_layer = 3

                if payload_communities is None:
                    load_communities = None
                else:
                    load_communities = AGOLDataLoader(
                        url=apex_url, layer=communities_layer
                    ).add_features(payload_communities)

            except Exception as e:
                load_communities = {"success": False, "message": f"Communities payload error: {e}"}

        spinner_container.empty()

        if load_communities is not None:
            if load_communities.get("success"):
                st.success("LOAD COMMUNITIES: SUCCESS ✅")
            else:
                st.error(f"LOAD COMMUNITIES: FAILURE ❌  {load_communities.get('message')}")
                st.session_state.setdefault("step_failures", []).append(load_communities.get("message"))

        # --- Upload Contacts ---
        with spinner_container, st.spinner("Loading Contacts to APEX..."):
            try:
                payload_contacts = contacts_payload(st.session_state.get("apex_globalid"))
                contacts_layer = 9

                if payload_contacts is None:
                    load_contacts = None
                else:
                    load_contacts = AGOLDataLoader(
                        url=apex_url, layer=contacts_layer
                    ).add_features(payload_contacts)

            except Exception as e:
                load_contacts = {"success": False, "message": f"Contacts payload error: {e}"}

        spinner_container.empty()

        if load_contacts is not None:
            if load_contacts.get("success"):
                st.success("LOAD CONTACTS: SUCCESS ✅")
            else:
                st.error(f"LOAD CONTACTS: FAILURE ❌  {load_contacts.get('message')}")
                st.session_state.setdefault("step_failures", []).append(load_contacts.get("message"))

        # --- Upload Geography ---
        with spinner_container, st.spinner("Loading Geography to APEX..."):
            geography_layers = {
                "region": 4,
                "borough": 5,
                "senate": 6,
                "house": 7
            }

            if st.session_state['selected_route']:
                geography_layers["route"] = 8   

            load_results = {}

            try:
                for name, layer_id in geography_layers.items():
                    if f"{name}_list" in st.session_state:
                        
                        payload = geography_payload(
                            st.session_state.get("apex_globalid"),
                            name
                        )

                        if payload is None:
                            load_results[name] = None
                        else:
                            load_results[name] = AGOLDataLoader(
                                url=apex_url, layer=layer_id
                            ).add_features(payload)

            except Exception as e:
                load_results["error"] = {"success": False, "message": f"Geography payload error: {e}"}

        spinner_container.empty()

        failed_layers = []
        fail_messages = []

        for name, result in load_results.items():
            if result is not None and not result.get("success", True):
                failed_layers.append(name.upper())
                fail_messages.append(result.get("message"))

        if failed_layers:
            st.error(f"LOAD GEOGRAPHIES: FAILURE ❌\nFailed layers: {', '.join(failed_layers)}\nMessages: {', '.join(fail_messages)}")
            st.session_state.setdefault("step_failures", []).extend(fail_messages)
        else:
            st.success("LOAD GEOGRAPHIES: SUCCESS ✅")


        # --- Final check ---
        if st.session_state.get("step_failures"):
            # Case 1: No GlobalID → project never loaded
            if not st.session_state.get("apex_globalid"):
                st.error("UPLOAD FAILED ❌ Project did not load into APEX. Please reset the application and try again.")
            else:
                # Case 2: GlobalID exists → run backend cleanup silently
                try:
                    if delete_project(apex_url, 0, st.session_state["apex_globalid"]):
                        st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
                    else:
                        st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
                except Exception:
                    st.error("UPLOAD FAILED ❌ Please reset the application and try again.")
        else:
            st.session_state['upload_complete'] = True
            st.write("")
            st.write("")
            st.markdown(
                """ <h5 style="font-size:20px; font-weight:600;">
                ✅ Upload Finished! Refresh the page to <span style="font-weight:700;">add a new project</span>.
                </h5> """,
                unsafe_allow_html=True
            )








# -------------------------------------------------------------------------
# Navigation controls
# -------------------------------------------------------------------------
st.write("")
cols = st.columns([1, 1, 4])

step = st.session_state.step

# ✅ ALL STEPS EXCEPT STEP 6
if step != 6:

    # Back button
    with cols[0]:
        st.button("⬅️ Back", on_click=prev_step, disabled=step == 1)

    # Next button logic
    with cols[1]:
        can_proceed = False

        if step == 1:
            can_proceed = True
        elif step == 2:
            can_proceed = st.session_state.get("details_complete", False)
        elif step == 3:
            can_proceed = True
        elif step == 4:
            if st.session_state.project_type:
                if st.session_state.project_type.startswith("Site"):
                    can_proceed = st.session_state.selected_point is not None
                else:
                    can_proceed = st.session_state.selected_route is not None
        elif step == 5:
            can_proceed = True

        if step < TOTAL_STEPS:
            st.button("Next ➡️", on_click=next_step, disabled=not can_proceed)

    st.caption("Use Back and Next to navigate. Refresh will reset this session.")




