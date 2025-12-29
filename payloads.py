import streamlit as st
from shapely.geometry import LineString, Point
import datetime
from agol_util import select_record

def clean_payload(payload: dict) -> dict:
    """
    Remove any attributes set to None, 0, or ''.
    """
    cleaned = dict(payload)
    new_adds = []

    for add in payload.get("adds", []):
        attrs = add.get("attributes", {})
        filtered_attrs = {
            k: v for k, v in attrs.items()
            if v is not None and v != 0 and v != ""
        }
        new_add = dict(add)
        new_add["attributes"] = filtered_attrs
        new_adds.append(new_add)

    cleaned["adds"] = new_adds
    return cleaned

def to_date_string(value):
    """
    Convert a datetime.date or datetime.datetime to a string.
    - If value is "REMOVE", return "REMOVE".
    - If value is None or not a valid date/datetime, return "REMOVE".
    - Otherwise return an ISO 8601 string (YYYY-MM-DD).
    """
    if value is None:
        return None

    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        # Promote date to datetime at midnight
        value = datetime.datetime.combine(value, datetime.time())

    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d")

    # Anything else is invalid
    return 


def get_line_center(line_geom):
    """
    Given a Shapely LineString or a list of coordinates,
    return the center point (midpoint along its length).
    """
    # If input is a list of coordinates, convert to LineString
    if isinstance(line_geom, list):
        line_geom = LineString(line_geom)
    
    if not isinstance(line_geom, LineString):
        raise ValueError("Geometry must be a LineString or list of coordinates")
    
    # Find halfway distance along the line
    midpoint_distance = line_geom.length / 2.0
    center_point = line_geom.interpolate(midpoint_distance)
    
    # Return as a tuple (lon, lat)
    return (center_point.x, center_point.y)



def clean_payloads(payloads: dict) -> dict:
    """
    Remove any attribute entries marked as 'REMOVE'.
    """
    cleaned = {}
    for key, payload in payloads.items():
        new_payload = payload.copy()
        new_adds = []
        for add in payload.get("payload", {}).get("adds", []):
            attrs = add.get("attributes", {})
            filtered_attrs = {k: v for k, v in attrs.items() if v != "REMOVE"}
            # preserve geometry if present
            new_add = {"attributes": filtered_attrs}
            if "geometry" in add:
                new_add["geometry"] = add["geometry"]
            new_adds.append(new_add)
        new_payload["payload"] = {"adds": new_adds}
        cleaned[key] = new_payload
    return cleaned



def project_payload():
    try:
        # Determine center based on selected geometry
        center = None
        if st.session_state.get("selected_point"):
            pt = st.session_state["selected_point"]
            center = (pt.x, pt.y) if isinstance(pt, Point) else (pt[0], pt[1])
            proj_type = "Site"
        elif st.session_state.get("selected_route"):
            route = st.session_state["selected_route"]
            center = get_line_center(route)
            proj_type = "Route"

        # Build payload with .get() and default None
        payload = {
            "adds": [
                {
                    "attributes": {
                        "Proj_Type": proj_type,
                        "AWP_Proj_Name": st.session_state.get("awp_proj_name", None),
                        "Proj_Name": st.session_state.get("proj_name", None),
                        "IRIS": st.session_state.get("iris", None),
                        "STIP": st.session_state.get("stip", None),
                        "Fed_Proj_Num": st.session_state.get("fed_proj_num", None),
                        "AWP_Proj_Desc": st.session_state.get("awp_proj_desc", None),
                        "Proj_Desc": st.session_state.get("proj_desc", None),
                        "Proj_Purp": st.session_state.get("proj_purp", None),
                        "Proj_Impact": st.session_state.get("proj_impact", None),
                        "Proj_Prac": st.session_state.get("proj_prac", None),
                        "Phase": st.session_state.get("phase", None),
                        "Fund_Type": st.session_state.get("fund_type", None),
                        "TenAdd": to_date_string(st.session_state.get("tenadd", None)),
                        "Awarded": "Yes" if st.session_state.get("contractor") else "No",
                        "Award_Date": to_date_string(st.session_state.get("award_date", None)),
                        "Award_Fiscal_Year": st.session_state.get("award_fiscal_year", None),
                        "Contractor": st.session_state.get("contractor", None),
                        "Awarded_Amount": st.session_state.get("awarded_amount", None),
                        "Current_Contract_Amount": st.session_state.get("current_contract_amount", None),
                        "Amount_Paid_to_Date": st.session_state.get("amount_paid_to_date", None),
                        "Anticipated_Start": st.session_state.get("anticipated_start", None),
                        "Anticipated_End": st.session_state.get("anticipated_end", None),
                        "Construction_Year": st.session_state.get("construction_year", None),
                        "New_Continuing": st.session_state.get("new_continuing", None),
                        "Route_ID": st.session_state.get("route_ids", None),
                        "Route_Name": st.session_state.get("route_names", None),
                        "Impact_Comm": st.session_state.get("impact_comm_names", None),
                        "DOT_PF_Region": st.session_state.get("region_string", None),
                        "Borough_Census_Area": st.session_state.get("borough_string", None),
                        "Senate_District": st.session_state.get("senate_string", None),
                        "House_District": st.session_state.get("house_string", None),
                        "Proj_Web": st.session_state.get("proj_web", None),
                        "APEX_Mapper_Link": st.session_state.get("apex_mapper_link", None),
                        'Submitted_By': st.session_state.get('submitted_by', None),
                        "Database_Status": "Review: Awaiting Review",
                        "Database_Status_Notes": st.session_state.get("database_status_notes", None),
                        "AWP_GUID": st.session_state.get("awp_globalid", None),
                    },
                    "geometry": {
                        "x": center[1] if center else None,  # longitude
                        "y": center[0] if center else None,  # latitude
                        "spatialReference": {"wkid": 4326}
                    }
                }
            ]
        }

        return clean_payload(payload)

    except Exception as e:
        # Bubble up error so caller can handle with st.error
        raise RuntimeError(f"Error building project payload: {e}")
    




def geometry_payload(globalid: str):
    try:
        # Point case
        if st.session_state.get("selected_point"):
            pt = st.session_state["selected_point"]
            payload = {
                "adds": [
                    {
                        "attributes": { 
                            "Site_AWP_Proj_Name": st.session_state.get("awp_proj_name", None),
                            "Site_Proj_Name": st.session_state.get("proj_name", None),
                            "Site_DOT_PF_Region": st.session_state.get("region_string", None),
                            "Site_Borough_Census_Area": st.session_state.get("borough_string", None),
                            "Site_Senate_District": st.session_state.get("senate_string", None),
                            "Site_House_District": st.session_state.get("house_string", None),
                            "parentglobalid": globalid

                        },
                        "geometry": {
                            "x": pt[1] if isinstance(pt, (list, tuple)) else pt.get("x"),
                            "y": pt[0] if isinstance(pt, (list, tuple)) else pt.get("y"),
                            "spatialReference": {"wkid": 4326}
                        }
                    }
                ]
            }
            return payload

        # Route case
        elif st.session_state.get("selected_route"):
            route = st.session_state["selected_route"]
            payload = {
                "adds": [
                    {
                        "attributes": { 
                            "Route_AWP_Proj_Name": st.session_state.get("awp_proj_name", None),
                            "Route_Proj_Name": st.session_state.get("proj_name", None),
                            "Route_DOT_PF_Region": st.session_state.get("region_string", None),
                            "Route_Borough_Census_Area": st.session_state.get("borough_string", None),
                            "Route_Senate_District": st.session_state.get("senate_string", None),
                            "Route_House_District": st.session_state.get("house_string", None),
                            "parentglobalid": globalid

                        },
                        "geometry": {
                            "paths": [
                                [
                                    [pt[1], pt[0]] if isinstance(pt, (list, tuple)) else [pt.get("x"), pt.get("y")]
                                    for pt in route
                                ]
                            ],
                            "spatialReference": {"wkid": 4326}
                        }
                    }
                ]
            }
            return clean_payload(payload)

        else:
            return None

    except Exception as e:
        st.error(f"Error building geometry payload: {e}")
        return None
    



def communities_payload(globalid: str):
    """
    Build an ArcGIS applyEdits payload for impacted communities.
    Returns None if no impacted communities exist or no valid records are found.
    """
    try:
        comm_list = st.session_state.get("impact_comm_ids", None)
        if not comm_list:
            # Valid case: nothing to add
            return None

        payload = {"adds": []}
        comms_url = (
            "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/"
            "All_Alaska_Communities_Baker/FeatureServer"
        )

        
        for comm_id in comm_list:
            comms_data = select_record(
                comms_url,
                7,
                "DCCED_CommunityId",
                str(comm_id),
                fields="OverallName,Latitude,Longitude"
            )

            if not comms_data:
                # Skip silently if no record found
                continue

            attrs = comms_data[0].get("attributes", {})
            name = attrs.get("OverallName")
            y = attrs.get("Latitude")
            x = attrs.get("Longitude")

            if name and y is not None and x is not None:
                payload["adds"].append({
                    "attributes": {
                        "Community_Name": name,
                        "parentglobalid": globalid
                    },
                    "geometry": {
                        "x": x,
                        "y": y,
                        "spatialReference": {"wkid": 4326}
                    }
                })
            # If required fields are missing, skip this community instead of raising

        if not payload["adds"]:
            # Valid case: no usable community records
            return None

        return clean_payload(payload)

    except Exception as e:
        st.error(f"Error building communities payload: {e}")
        return 
    


def contacts_payload(globalid: str):
    try: 
        contact_list = st.session_state.get("contacts", None)
        if not contact_list:
            return None

        payload = {"adds": []}

        # Add contacts to payload
        for contact in contact_list:
            payload["adds"].append({
                "attributes": {
                    "Contact_Role": contact.get("Role", ""),
                    "Contact_Name": contact.get("Name", ""),
                    "Contact_Email": contact.get("Email", ""),
                    "Contact_Phone": contact.get("Phone", ""),
                    "parentglobalid": globalid
                }
            })

        return clean_payload(payload)

    except Exception as e:
        st.error(f"Error building contacts payload: {e}")
        return




def geography_payload(globalid: str, name: str):
    """
    Build a payload containing attributes and geometry for a given geography type.

    Parameters
    ----------
    globalid : str
        The parent GlobalID to associate with the payload.
    name : str
        The geography type to process. Must be one of:
        'region', 'borough', 'senate', or 'house'.

    Returns
    -------
    dict
        A cleaned payload dictionary containing 'adds' entries with
        attributes and geometry for the specified geography type.
    """

    # Dictionary of services keyed by geography name, with base URL and layer index
    geography_dict = {
        "region": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_DOT_PF_Regions/FeatureServer",
            "layer": 0
        },
        "borough": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_BoroughCensus/FeatureServer",
            "layer": 0
        },
        "senate": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_SenateDistricts/FeatureServer",
            "layer": 0
        },
        "house": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/STIP_HouseDistricts/FeatureServer",
            "layer": 0
        },
        "route": {
            "url": "https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AKDOT_Routes_Mileposts/FeatureServer",
            "layer": 0
        }
    }

    payload = {}

    # REGION
    if name == 'region':
        id_list = st.session_state.get(f"{name}_list")
        service_info = geography_dict.get(name)
        if not id_list or not service_info:
            print(None)
        payload = {"adds": []}
        for item_id in id_list:
            # Query record from AGOL service
            data = select_record(service_info["url"], service_info["layer"],
                                 "GlobalID", str(item_id), fields="*", return_geometry=True)
            if not data:
                continue
            attrs = data[0].get("attributes", {})
            geom = data[0].get("geometry", {})
            region_name = attrs.get("NameAlt")
            payload["adds"].append({
                "attributes": {
                    "Region_Name": region_name,
                    "parentglobalid": globalid,
                },
                "geometry": geom
            })

    # BOROUGH
    if name == 'borough':
        id_list = st.session_state.get(f"{name}_list")
        service_info = geography_dict.get(name)
        if not id_list or not service_info:
            print(None)
        payload = {"adds": []}
        for item_id in id_list:
            data = select_record(service_info["url"], service_info["layer"],
                                 "GlobalID", str(item_id), fields="*", return_geometry=True)
            if not data:
                continue
            attrs = data[0].get("attributes", {})
            geom = data[0].get("geometry", {})
            fips = attrs.get('FIPS')
            borough_name = attrs.get("NameAlt")
            payload["adds"].append({
                "attributes": {
                    "Bor_FIPS": fips,
                    "Bor_Name": borough_name,
                    "parentglobalid": globalid,
                },
                "geometry": geom
            })

    # SENATE
    if name == 'senate':
        id_list = st.session_state.get(f"{name}_list")
        service_info = geography_dict.get(name)
        if not id_list or not service_info:
            print(None)
        payload = {"adds": []}
        for item_id in id_list:
            data = select_record(service_info["url"], service_info["layer"],
                                 "GlobalID", str(item_id), fields="*", return_geometry=True)
            if not data:
                continue
            attrs = data[0].get("attributes", {})
            geom = data[0].get("geometry", {})
            district = attrs.get("DISTRICT")
            payload["adds"].append({
                "attributes": {
                    "Senate_District_Name": district,
                    "parentglobalid": globalid,
                },
                "geometry": geom
            })

    # HOUSE
    if name == 'house':
        id_list = st.session_state.get(f"{name}_list")
        service_info = geography_dict.get(name)
        if not id_list or not service_info:
            print(None)
        payload = {"adds": []}
        for item_id in id_list:
            data = select_record(service_info["url"], service_info["layer"],
                                 "GlobalID", str(item_id), fields="*", return_geometry=True)
            if not data:
                continue
            attrs = data[0].get("attributes", {})
            geom = data[0].get("geometry", {})
            house_num = attrs.get("DISTRICT")
            house_name = attrs.get("HOUSE_NAME")
            senate = attrs.get("SENATE_DISTRICT")
            payload["adds"].append({
                "attributes": {
                    "House_District_Num": house_num,
                    "House_District_Name": house_name,
                    "House_Senate_District": senate,
                    "parentglobalid": globalid,
                },
                "geometry": geom
            })


    # routes
    if name == 'route':
        id_list = st.session_state.get(f"{name}_list")
        service_info = geography_dict.get(name)
        if not id_list or not service_info:
            print(None)
        payload = {"adds": []}
        for item_id in id_list:
            data = select_record(service_info["url"], service_info["layer"],
                                "Route_ID", str(item_id), fields="*", return_geometry=True)
            if not data:
                continue
            attrs = data[0].get("attributes", {})
            geom = data[0].get("geometry", {})
            route_id = attrs.get("Route_ID")
            route_name = attrs.get("Route_Name")
            payload["adds"].append({
                "attributes": {
                    "Impacted_Route_ID": route_id,
                    "Impacted_Route_Name": route_name,
                    "parentglobalid": globalid,
                },
                "geometry": geom
            })



    # Return cleaned payload
    if payload == {}:
        return None
    
    else:
        return clean_payload(payload)
