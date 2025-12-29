import streamlit as st
import json
import requests
from agol_util import AGOLQueryIntersect

def run_district_queries():
    """
    Decide which geometry to use from session_state and run
    intersect queries for House, Senate, Borough, and Region.
    Store string_values and list_values into session_state.
    Defaults are blank if nothing is returned.
    """

    # Decide which geometry to use
    if st.session_state.get('selected_point'):
        st.session_state['project_geometry'] = st.session_state['selected_point']
    elif st.session_state.get('selected_route'):
        st.session_state['project_geometry'] = st.session_state['selected_route']
    else:
        st.session_state['project_geometry'] = None

    # Initialize defaults (blank)
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

    # Only run queries if we have a geometry
    if st.session_state['project_geometry'] is not None:

        # Temporary info message
        info_placeholder = st.empty()
        info_placeholder.info("Querying against geography layers...")

        # House Districts
        house = AGOLQueryIntersect(
            url="https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_HouseDistricts/FeatureServer",
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,DISTRICT",
            return_geometry=False,
            list_values="GlobalID",
            string_values="DISTRICT"
        )
        st.session_state['house_list'] = house.list_values or []
        st.session_state['house_string'] = house.string_values or ""

        # Senate Districts
        senate = AGOLQueryIntersect(
            url="https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_SenateDistricts/FeatureServer",
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,DISTRICT",
            return_geometry=False,
            list_values="GlobalID",
            string_values="DISTRICT"
        )
        st.session_state['senate_list'] = senate.list_values or []
        st.session_state['senate_string'] = senate.string_values or ""

        # Boroughs
        borough = AGOLQueryIntersect(
            url="https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_BoroughCensus/FeatureServer",
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,NameAlt",
            return_geometry=False,
            list_values="GlobalID",
            string_values="NameAlt"
        )
        st.session_state['borough_list'] = borough.list_values or []
        st.session_state['borough_string'] = borough.string_values or ""

        # Regions
        region = AGOLQueryIntersect(
            url="https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_DOT_PF_Regions/FeatureServer",
            layer=0,
            geometry=st.session_state['project_geometry'],
            fields="GlobalID,NameAlt",
            return_geometry=False,
            list_values="GlobalID",
            string_values="NameAlt"
        )
        st.session_state['region_list'] = region.list_values or []
        st.session_state['region_string'] = region.string_values or ""


        # If Routes, Intersect Route Layer
        if st.session_state['selected_route']:
            route = AGOLQueryIntersect(
                url="https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AKDOT_Routes_Mileposts/FeatureServer",
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