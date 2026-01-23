
import streamlit as st
from streamlit_folium import st_folium
from streamlit_scroll_to_top import scroll_to_here
import folium
from folium.plugins import Draw, Geocoder, Search
import geopandas as gpd
import tempfile
import zipfile
import time

from init_session import init_session_state
from map_util import add_small_geocoder
from details_form import project_details_form
from contacts import contacts_list
from instructions import instructions
from review import review_information
from district_queries import run_district_queries
from load_project import load_project_apex
from load_geometry import load_geometry_app


st.set_page_config(page_title="Alaska DOT&PF - APEX Project Loader", page_icon="📝", layout="centered")

# Base overview map
m = folium.Map(location=[64.2008, -149.4937], zoom_start=4)
add_small_geocoder(m)


# Initialize Session State
init_session_state()


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
    "Complete the form, then click **Submit Information**, this will check to see if all required values are present.  If"
    " all information is present and in the correct format, you will be able to continue"
    )

    instructions("Project Information")

    st.write('')

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
    
    load_geometry_app
    



elif st.session_state.step == 5:
    st.markdown("### REVIEW PROJECT ✔️")
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

    # Display Drop Down of Uploaders
    st.markdown("<h5>Submitter Name</h5>", unsafe_allow_html=True)
    selected_name = st.selectbox("Submitted by:", st.session_state['uploaders'], index=0)

    # If "Other" is chosen, show a text box to override 
    if selected_name == "Other": 
        custom_name = st.text_input("Please type your name:") 
        
        if custom_name.strip(): 
            st.session_state['submitted_by'] = custom_name

    else: 
        st.session_state['submitted_by'] = selected_name


    st.write("")

    # Upload Project Option Once Submitter Loaded
    st.markdown("<h5>Upload Project</h5>", unsafe_allow_html=True)
    
    # ✅ Back + Upload buttons appear together BEFORE upload starts
    col_back, col_gap, col_upload, _ = st.columns([1.5, 0.2, 3, 6])   # wider upload column

    if not st.session_state.get("upload_clicked", False):

        # Back button (left)
        with col_back:
            st.button("⬅️ Back", on_click=prev_step, key="step6_back_btn")

        # Upload button (right) — now inside the SAME row
        if st.session_state['submitted_by']:
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
            
            #Run Upload Process
            load_project_apex()




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
                elif st.session_state.project_type.startswith("Route"):
                    can_proceed = st.session_state.selected_route is not None
                elif st.session_state.project_type.startswith("Boundary"):
                    can_proceed = st.session_state.selected_boundary is not None
                else:
                    can_proceed = st.session_state.selected_route is not None
                
        elif step == 5:
            can_proceed = True

        if step < TOTAL_STEPS:
            st.button("Next ➡️", on_click=next_step, disabled=not can_proceed)

    st.caption("Use Back and Next to navigate. Refresh will reset this session.")




