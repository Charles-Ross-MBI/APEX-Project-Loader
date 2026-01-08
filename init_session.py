import os
import streamlit as st
from agol_util import select_record


def init_session_state():
    """Initialize all session state values."""

    if "all_widget_prefixes" not in st.session_state:
        st.session_state["all_widget_prefixes"] = set()


    # ---------------------------------------------------------
    # DEFAULTS
    # ---------------------------------------------------------
    defaults = {
        "step": 1,
        "selected_point": None,
        "selected_route": None,
        'selected_boundary':None,
        "project_type": None,
        "geo_option": None,
        "info_option": None,
        "aashto_id": "",
        "project_name": "",
        "project_description": "",
        "project_category": None,
        "project_contacts": [],
        'details_complete': False
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
        for key, value in defaults.items():
            st.session_state.setdefault(key, value)



    # ---------------------------------------------------------
    # DICTIONARIES
    # ---------------------------------------------------------
    dicts = {
        'project_phases' : {
            49: "Project Definition",
            50: "Project Design & Review",
            51: "Assigned to Letting",
            52: "Advertising",
            91: "Import Xtab File from BidX",
            53: "Award Processing",
            54: "Add Alt Analysis",
            55: "Awarded",
            56: "Active Contract"
        }
    }

    for key, value in dicts.items():
        st.session_state.setdefault(key, value)



    # ---------------------------------------------------------
    # VALUES
    # ---------------------------------------------------------
    value_lists = {
        'construction_years': [
            "",
            "CY2025", 
            "CY2026", 
            "CY2027", 
            "CY2028", 
            "CY2029", 
            "CY2030"
        ],
        'phase_list': [
            "",
            "Project Definition",
            "Project Design & Review",
            "Assigned to Letting",
            "Advertising",
            "Import Xtab File from BidX",
            "Award Processing",
            "Add Alt Analysis",
            "Awarded",
            "Active Contract"
        ],
        'funding_list': [
            "",
            "FHWY", 
            "FHWA", 
            "FAA", 
            "STATE", 
            "OTHER"
        ],
        'practice_list': [
            "",
            'Highways', 
            "Aviation", 
            "Facilities", 
            "Marine Highway", 
            "Other"
        ],
        'years': [
            "",
            "2020", 
            "2021", 
            "2022", 
            "2023", 
            "2024", 
            "2025", 
            "2026", 
            "2027", 
            "2028", 
            "2029", 
            "2030"
        ]
    }

    for key, value in value_lists.items():
        st.session_state.setdefault(key, value)


    # ---------------------------------------------------------
    # URL PARAMETERS
    # ---------------------------------------------------------
    url_params = {
        "guid": None,
        "version": None
    }
    for key, value in url_params.items():
        st.session_state.setdefault(key, value)



    # ---------------------------------------------------------
    # AGOL URLS
    # ---------------------------------------------------------

    # Main APEX URL
    apex_url = 'https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/service_4c8488c7bb7b4f15a381cb3786da94e6/FeatureServer'

    apex_layers = {
        "projects": 0,
        "sites": 1,
        "routes": 2,
        "boundaries": 3,
        "impact_comms": 4,
        "region": 5,
        "bor": 6,
        "senate": 7,
        "house": 8,
        "impact_routes": 9,
        "contacts": 10, 
    }
    
    agol_urls = {
        'apex_url': apex_url,
        "projects_url": f"{apex_url}/0",
        "sites_url": f"{apex_url}/1",
        "routes_url": f"{apex_url}/2",
        "boundaries_url": f"{apex_url}/3",
        "impact_comms_url": f"{apex_url}/4",
        "region_url": f"{apex_url}/5",
        "bor_url": f"{apex_url}/6",
        "senate_url": f"{apex_url}/7",
        "house_url": f"{apex_url}/8",
        "impact_routes_url": f"{apex_url}/9",
        "contacts_url": f"{apex_url}/10",
        "aashtoware_url": f"https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AWP_PROJECTS_EXPORT_XYTableToPoint_ExportFeatures/FeatureServer",
        "mileposts": f"https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AKDOT_Routes_Mileposts/FeatureServer"
    }
    
    for key, value in agol_urls.items():
        st.session_state.setdefault(key, value)

    for key, value in apex_layers.items():
        st.session_state.setdefault(key, value)



    # ---------------------------------------------------------
    # AGOL CREDENTIALS
    # ---------------------------------------------------------

    # 1. Check if a .env file exists
    env_file_exists = os.path.exists(".env")

    env_user = None
    env_pass = None

    if env_file_exists:
        from dotenv import load_dotenv
        load_dotenv()
        agol_username = os.getenv("AGOL_USERNAME")
        agol_password = os.getenv("AGOL_PASSWORD")

    else:
        # 2. Check secrets (may or may not exist)
        agol_username = st.secrets.get("AGOL_USERNAME") if hasattr(st, "secrets") else None
        agol_password = st.secrets.get("AGOL_PASSWORD") if hasattr(st, "secrets") else None


    # 4. Store in session_state safely
    st.session_state.setdefault("AGOL_USERNAME", agol_username)
    st.session_state.setdefault("AGOL_PASSWORD", agol_password)


# --------------------------------------------------------- 
# RUN AUTOMATICALLY WHEN IMPORTED 
# --------------------------------------------------------- 
init_session_state()
