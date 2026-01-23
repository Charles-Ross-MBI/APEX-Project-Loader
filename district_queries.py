
"""
===============================================================================
DISTRICT QUERIES (STREAMLIT) — GEOGRAPHY INTERSECTS (HOUSE / SENATE / BOROUGH / REGION)
===============================================================================

Purpose:
    Runs ArcGIS Online (AGOL) spatial-intersect queries against reference
    geography layers (House districts, Senate districts, Borough/Census areas,
    and DOT&PF Regions) based on the currently selected project geometry in
    Streamlit session_state.

    Optionally, when a route or boundary geometry is used, it also intersects
    against a route reference layer to derive impacted Route IDs and names.

Key behaviors:
    - Geometry selection precedence:
        1) selected_point
        2) selected_route
        3) selected_boundary
      The selected geometry is stored into st.session_state['project_geometry'].

    - Default initialization:
      Always initializes list/string session_state outputs to blank values
      so downstream renderers can safely display “no data” states.

    - Query execution:
      Uses AGOLQueryIntersect to:
        * intersect against a service/layer
        * return list_values (IDs) and string_values (human-readable labels)
      Results are stored in session_state as both list and string representations.

Session-state dependencies (expected at runtime):
    Input geometry (one of):
      - 'selected_point'    : list[[lat, lon], ...]
      - 'selected_route'    : list[list[[lat, lon], ...], ...]
      - 'selected_boundary' : list[list[[lat, lon], ...], ...]

    Outputs (always written/initialized):
      - 'project_geometry'
      - 'house_list', 'house_string'
      - 'senate_list', 'senate_string'
      - 'borough_list', 'borough_string'
      - 'region_list', 'region_string'
      - Route outputs (set when route/boundary is selected):
          'route_list', 'route_ids', 'route_names'
      - Legacy/unused placeholders:
          'route_id', 'route_name'

Notes:
    - This module is intentionally stateful and performs side effects only
      (writes to st.session_state and shows/clears a temporary info message).
    - The underlying intersect/query behavior (coordinate swapping, geometry type
      selection) is implemented in agol_util.AGOLQueryIntersect.

===============================================================================
"""

import streamlit as st
import json
import requests
from agol_util import AGOLQueryIntersect


# =============================================================================
# ENTRYPOINT: RUN ALL DISTRICT/GEOGRAPHY QUERIES
# =============================================================================
# run_district_queries():
#   - Determines which geometry is active in session_state
#   - Initializes blank output keys to safe defaults
#   - Runs intersect queries for:
#       * House districts
#       * Senate districts
#       * Borough/Census areas
#       * DOT&PF Regions
#     plus route intersects when route/boundary is selected
# =============================================================================
def run_district_queries():
    """
    Decide which geometry to use from session_state and run
    intersect queries for House, Senate, Borough, and Region.
    Store string_values and list_values into session_state.
    Defaults are blank if nothing is returned.
    """

    # -------------------------------------------------------------------------
    # 1) Determine which geometry to use
    # -------------------------------------------------------------------------
    # Precedence matches the app’s selection workflow:
    #   selected_point > selected_route > selected_boundary
    if st.session_state.get('selected_point'):
        st.session_state['project_geometry'] = st.session_state['selected_point']
    elif st.session_state.get('selected_route'):
        st.session_state['project_geometry'] = st.session_state['selected_route']
    elif st.session_state.get('selected_boundary'):
        st.session_state['project_geometry'] = st.session_state['selected_boundary']
    else:
        st.session_state['project_geometry'] = None

    # -------------------------------------------------------------------------
    # 2) Initialize defaults (blank)
    # -------------------------------------------------------------------------
    # IMPORTANT:
    # These are always set so downstream pages can read keys safely, even when
    # no geometry exists or no intersect results are returned.
    st.session_state['house_list'] = []
    st.session_state['house_string'] = ""
    st.session_state['senate_list'] = []
    st.session_state['senate_string'] = ""
    st.session_state['borough_list'] = []
    st.session_state['borough_string'] = ""
    st.session_state['region_list'] = []
    st.session_state['region_string'] = ""
    st.session_state['route_id'] = ""
    st.session_state['route_name'] = ""

    # -------------------------------------------------------------------------
    # 3) Only run queries if we have a geometry
    # -------------------------------------------------------------------------
    if st.session_state['project_geometry'] is not None:

        # Temporary info message (provides user feedback during network calls)
        info_placeholder = st.empty()
        info_placeholder.info("Querying against geography layers...")

        # ---------------------------------------------------------------------
        # House Districts
        # ---------------------------------------------------------------------
        house = AGOLQueryIntersect(
            url=st.session_state['house_intersect'],
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,DISTRICT",
            return_geometry=False,
            list_values="GlobalID",
            string_values="DISTRICT"
        )
        st.session_state['house_list'] = house.list_values or []
        st.session_state['house_string'] = house.string_values or ""

        # ---------------------------------------------------------------------
        # Senate Districts
        # ---------------------------------------------------------------------
        senate = AGOLQueryIntersect(
            url=st.session_state['senate_intersect'],
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,DISTRICT",
            return_geometry=False,
            list_values="GlobalID",
            string_values="DISTRICT"
        )
        st.session_state['senate_list'] = senate.list_values or []
        st.session_state['senate_string'] = senate.string_values or ""

        # ---------------------------------------------------------------------
        # Boroughs / Census Areas
        # ---------------------------------------------------------------------
        borough = AGOLQueryIntersect(
            url=st.session_state['bor_intersect'],
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,NameAlt",
            return_geometry=False,
            list_values="GlobalID",
            string_values="NameAlt"
        )
        st.session_state['borough_list'] = borough.list_values or []
        st.session_state['borough_string'] = borough.string_values or ""

        # ---------------------------------------------------------------------
        # DOT&PF Regions
        # ---------------------------------------------------------------------
        region = AGOLQueryIntersect(
            url=st.session_state['region_intersect'],
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,NameAlt",
            return_geometry=False,
            list_values="GlobalID",
            string_values="NameAlt"
        )
        st.session_state['region_list'] = region.list_values or []
        st.session_state['region_string'] = region.string_values or ""

        # ---------------------------------------------------------------------
        # Routes (conditional)
        # ---------------------------------------------------------------------
        # Only apply route intersection when geometry implies a route context:
        #   - selected_route (polyline)
        #   - selected_boundary (area that may overlap multiple routes)
        if st.session_state['selected_route'] or st.session_state['selected_boundary']:
            route = AGOLQueryIntersect(
                url=st.session_state['route_intersect'],
                layer=0,
                geometry=st.session_state['project_geometry'],
                fields="Route_ID,Route_Name_Unique",
                return_geometry=False,
                list_values="Route_ID",
                string_values="Route_Name_Unique"
            )
            st.session_state['route_list'] = route.list_values
            st.session_state['route_ids'] = ",".join(route.list_values) or ""
            st.session_state['route_names'] = route.string_values or ""

        # Clear the info message once complete
        info_placeholder.empty()
