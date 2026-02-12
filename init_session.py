
"""
===============================================================================
SESSION INITIALIZATION (STREAMLIT) — DEFAULTS, LISTS, URLS, CREDENTIALS
===============================================================================

Purpose:
    Defines and initializes Streamlit session_state keys used across the app.
    This module centralizes:
      - Default session values and wizard state
      - Static lookup dictionaries and value lists (years, phases, etc.)
      - AGOL/APEX service URLs and layer indices
      - AGOL credential sourcing (.env or st.secrets)
      - AWP field mapping dictionary used for AASHTOWare integration
      - Uploader list values (for attribution / metadata)

Key behaviors:
    - Idempotent initialization:
        * Uses `setdefault()` and conditional checks so repeated imports/reruns
          do not overwrite active user inputs.
    - Centralized service definitions:
        * Sets APEX base URL + layer indices and derived per-layer URLs.
        * Sets intersect-service URLs for geography/district queries.
    - Credential sourcing:
        * If a .env file exists, loads via python-dotenv
        * Otherwise tries Streamlit secrets
        * Stores into session_state['AGOL_USERNAME'] / ['AGOL_PASSWORD']

Session-state keys created/initialized (high-level):
    - Wizard/navigation:
        'step', 'geo_option', 'info_option', selection flags, duplication flags
    - Geometry selections:
        'selected_point', 'selected_route', 'selected_boundary'
    - Project/contact scaffolding:
        'project_contacts', 'details_complete', etc.
    - Static lists:
        'construction_years', 'phase_list', 'funding_list', 'practice_list', 'years'
    - AGOL/APEX:
        'apex_url', layer IDs, layer URLs, intersect URLs
    - AWP:
        'awp_fields' mapping dictionary
    - Uploaders:
        'uploaders' list

Notes:
    - This module runs init_session_state() automatically at import time.
      That pattern is intentional for Streamlit apps where scripts rerun often.
    - Values are seeded, not enforced: downstream pages may update session_state
      after this initializer runs.

===============================================================================
"""

import os
import streamlit as st

# =============================================================================
# ENTRYPOINT: SESSION STATE INITIALIZATION
# =============================================================================
# init_session_state():
#   - Creates baseline session_state keys if missing
#   - Populates lookup dictionaries and static lists
#   - Populates AGOL/APEX URLs and layer IDs
#   - Loads credentials from .env or st.secrets and stores them in session_state
#   - Sets AWP field mapping and uploader list
# =============================================================================
def init_session_state():
    """Initialize all session state values."""

    # -------------------------------------------------------------------------
    # Session scaffolding: widget prefix registry (used by other modules)
    # -------------------------------------------------------------------------
    if "all_widget_prefixes" not in st.session_state:
        st.session_state["all_widget_prefixes"] = set()

    # ======================================================
    # DEFAULT
    # ======================================================
    # Core keys used across the wizard. These are seeded once and then updated
    # by page-level logic as the user progresses.
    defaults = {
        "prev_aashto_id": None,
        "prev_awp_name": None,
        "prev_construction_year": None,
        "form_new_continuing_state": "New",
        "show_duplicate_dialog": False,
        "duplicate_found": False,
        "continue_w_duplicate": None,
        "step": 1,
        "selected_point": None,
        "selected_route": None,
        "selected_boundary": None,
        "project_type": None,
        "geo_option": None,
        "info_option": None,
        "aashto_id": "",
        "project_name": "",
        "project_description": "",
        "project_category": None,
        "details_complete": False,
        "duplicate_confirmed": False,
        "awp_geometry_points": {},
        "awp_dcml_mid_latitude": None,
        "awp_dcml_mid_longitude": None,
        "awp_dcml_bop_latitude": None,
        "awp_dcml_bop_longitude": None,
        "awp_dcml_eop_latitude": None,
        "awp_dcml_eop_longitude": None,
    }

    # Seed missing keys (do not overwrite user/session modifications)
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Redundant-but-safe idempotent seeding (kept as-is)
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    # -------------------------------------------------------------------------
    # DICTIONARIES
    # -------------------------------------------------------------------------
    # Lookup dictionaries and code->label mappings used across form fields.
    dicts = {
        'project_phases': {
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

    # -------------------------------------------------------------------------
    # VALUES
    # -------------------------------------------------------------------------
    # Predefined selectbox lists (construction years, funding types, etc.)
    value_lists = {
        'construction_years': [
            "",
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

    # -------------------------------------------------------------------------
    # URL PARAMETERS
    # -------------------------------------------------------------------------
    # Optional URL-driven state (e.g., deep links or versioning)
    url_params = {
        "guid": None,
        "version": None
    }
    for key, value in url_params.items():
        st.session_state.setdefault(key, value)



    # -------------------------------------------------------------------------
    # AGOL URLS
    # -------------------------------------------------------------------------
    agol_urls = {
        'apex_url': "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/service_ed21872369654fcc8d489cd1699c1f42/FeatureServer",
        "aashtoware_url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AWP_to_APEX_Contracts/FeatureServer",
        "milepoints": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/Pavement_Condition_Data_Tenth_Mile_2024/FeatureServer",
        'communities': "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/""All_Alaska_Communities_Baker/FeatureServer"
    }

    aashtoware_layers = {
        'contracts_layer': 0,
        'geometry_layer': 1,
    }


    # Layer indices used by loaders and query helpers
    apex_layers = {
        "projects_layer": 0,
        "sites_layer": 1,
        "routes_layer": 2,
        "boundaries_layer": 3,
        "bop_eop_layer": 4,
        "impact_comms_layer": 5,
        "region_layer": 6,
        "bor_layer": 7,
        "senate_layer": 8,
        "house_layer": 9,
        "impact_routes_layer": 10
    }

    # Geography intersect services (used by district_queries / geography payloads)
    geography_intersects = {
        "region_intersect": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_DOT_PF_Regions/FeatureServer",
            "layer": 0
        },
        "borough_intersect": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_BoroughCensus/FeatureServer",
            "layer": 0
        },
        "senate_intersect": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_SenateDistricts/FeatureServer",
            "layer": 0
        },
        "house_intersect": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_HouseDistricts/FeatureServer",
            "layer": 0
        },
        "route_intersect": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/Roads_AKDOT/FeatureServer",
            "layer": 0
        }
    }

    # Seed layer indices and URLs into session_state
    for key, value in agol_urls.items():
        st.session_state.setdefault(key, value)
    for key, value in apex_layers.items():
        st.session_state.setdefault(key, value)
    for key, value in aashtoware_layers.items():
        st.session_state.setdefault(key, value)
    for key, value in geography_intersects.items():
        st.session_state.setdefault(key, value)

    # -------------------------------------------------------------------------
    # AGOL CREDENTIALS
    # -------------------------------------------------------------------------
    # Credential sourcing precedence:
    #   1) .env file (python-dotenv)
    #   2) Streamlit secrets
    # The resolved credentials are then stored into session_state.
    #
    # NOTE: Variables env_user/env_pass are present but unused; preserved as-is.
    # -------------------------------------------------------------------------
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

    # ======================================================
    # NEW: Central dictionary for AWP mappings
    # ======================================================
    # AWP_FIELDS provides a single place to map UI/session keys to the
    # AASHTOWare-provided session keys.
    AWP_FIELDS = {
        "awp_proj_name": "ProjectName",
        "proj_name": "awp_PublicProjectName",
        "phase": "awp_ProjectPhase",
        "iris": "IRIS",
        "stip": "",
        "fed_proj_num": "FederalProjectNumber",
        "fund_type": "FundingType",
        "proj_prac": "ProjectPractice",
        "anticipated_start": "StartDate",
        "anticipated_end": "EndDate",
        "award_date": "AwardDate",
        "award_fiscal_year": "AwardFederalFiscalYear",
        "contractor": "AwardedContractor",
        "awarded_amount": "AwardedContractAmount",
        "current_contract_amount": "",
        "amount_paid_to_date": "AmountPaidToDate",
        "tenadd": "TentativeAdvertisingDate",
        "awp_proj_desc": "AASTOWARE_Description",
        'route_id': "",
        'route_name': "",
        "contact_name":"ContactName",
        "contact_email":"ContactEmail",
        "contact_phone":"ContactPhone",
        "proj_desc": "PublicDescription",
        "proj_web": "ProjectURL",
    }

   # Build transformed dict in session_state
    st.session_state["awp_fields"] = {}

    for key, value in AWP_FIELDS.items():
        if not value:
            # keep blanks as blank
            st.session_state["awp_fields"][key] = ""
        else:
            v = value.strip().lower()
            if not v.startswith("awp_"):
                v = "awp_" + v
            st.session_state["awp_fields"][key] = v

    # ======================================================
    # DATA UPLOADERS
    # ======================================================
    # Values for attribution / uploader selection UI.
    uploaders = ["",
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
    st.session_state['uploaders'] =uploaders

    
# -----------------------------------------------------------------------------
# RUN AUTOMATICALLY WHEN IMPORTED
# -----------------------------------------------------------------------------
# Streamlit reruns scripts frequently; importing this module should ensure
# session_state is always seeded with required defaults.
# -----------------------------------------------------------------------------
init_session_state()
