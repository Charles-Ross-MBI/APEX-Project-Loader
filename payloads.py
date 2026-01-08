import streamlit as st
from shapely.geometry import LineString, Point, Polygon
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


def _average_centers(centers):
    if not centers:
        raise ValueError("No centers provided.")

    xs = [c[0] for c in centers]
    ys = [c[1] for c in centers]

    return (sum(xs) / len(xs), sum(ys) / len(ys))  # (lon, lat)



def get_point_center(points):
    """
    Given:
      - A single point [lat, lon]
      - A list of points [[lat, lon], ...]
      - A list of point groups [[[lat, lon], ...], ...]

    Return:
      - A single (lon, lat) tuple representing the center point.
    """

    # Normalize to flat list of [lat, lon]
    flat_points = []

    # Single point [lat, lon]
    if isinstance(points, (list, tuple)) and len(points) == 2 and \
       all(isinstance(x, (int, float)) for x in points):
        flat_points.append(points)
    else:
        # List or nested list
        for item in points:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                flat_points.append(item)
            elif isinstance(item, (list, tuple)):
                for pt in item:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        flat_points.append(pt)

    if not flat_points:
        raise ValueError("No valid point data found.")

    # If only one point, just return it (as lon, lat)
    if len(flat_points) == 1:
        lat, lon = flat_points[0]
        return (float(lon), float(lat))

    # Multiple points → average center
    lats = [float(pt[0]) for pt in flat_points]
    lons = [float(pt[1]) for pt in flat_points]

    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    return (center_lon, center_lat)  # (lon, lat)



def get_line_center(line_geom):
    """
    Given:
      - A single LineString or list of coordinates
      - A list of LineStrings / coordinate lists

    Return:
      - A single (lon, lat) tuple representing the center of centers.
    """

    def _center_single_line(g):
        if isinstance(g, list):
            g = LineString(g)

        if not isinstance(g, LineString):
            raise ValueError("Geometry must be a LineString or list of coordinates")

        midpoint_distance = g.length / 2.0
        center = g.interpolate(midpoint_distance)
        return (center.x, center.y)  # (lon, lat)

    # Multiple geometries
    if isinstance(line_geom, list) and any(isinstance(x, (list, LineString)) for x in line_geom):
        centers = []
        for g in line_geom:
            centers.append(_center_single_line(g))
        return _average_centers(centers)

    # Single geometry
    return _center_single_line(line_geom)



def get_polygon_center(poly_geom):
    """
    Given:
      - A single Polygon or list of coordinates
      - A list of Polygons / coordinate lists

    Return:
      - A single (lon, lat) tuple representing the center of centers.
    """

    def _center_single_polygon(g):
        if isinstance(g, list):
            g = Polygon(g)

        if not isinstance(g, Polygon):
            raise ValueError("Geometry must be a Polygon or list of coordinates")

        c = g.centroid
        return (c.x, c.y)  # (lon, lat)

    # Multiple geometries
    if isinstance(poly_geom, list) and any(isinstance(x, (list, Polygon)) for x in poly_geom):
        centers = []
        for g in poly_geom:
            centers.append(_center_single_polygon(g))
        return _average_centers(centers)

    # Single geometry
    return _center_single_polygon(poly_geom)






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
            center = get_point_center(pt)
            proj_type = "Site"
        elif st.session_state.get("selected_route"):
            route = st.session_state["selected_route"]
            center = get_line_center(route)
            proj_type = "Route"
        elif st.session_state.get("selected_boundary"):
            boundary = st.session_state["selected_boundary"]
            center = get_polygon_center(boundary)
            proj_type = "Boundary"

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
                        "Email_Signup": st.session_state.get("email_signup", None),
                        'Submitted_By': st.session_state.get('submitted_by', None),
                        "Database_Status": "Review: Awaiting Review",
                        "AWP_GUID": st.session_state.get("awp_globalid", None),
                        "AWP_Update": st.session_state.get("awp_update", None)
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
        payloads = []  # final list of cleaned payloads

        # ---------------------------------------------------------
        # POINT CASE
        # ---------------------------------------------------------
        if st.session_state.get("selected_point"):

            points = st.session_state["selected_point"]

            
            def normalize_points(p):
                """Extract all valid [lat, lon] pairs from any nesting depth."""
                flat = []

                def extract(item):
                    # Case: valid coordinate pair
                    if isinstance(item, (list, tuple)) and len(item) == 2 \
                    and all(isinstance(v, (int, float)) for v in item):
                        flat.append(item)
                        return

                    # Case: any iterable -> search deeper
                    if isinstance(item, (list, tuple)):
                        for sub in item:
                            extract(sub)

                extract(p)
                return flat


            flat_points = normalize_points(points)

            if not flat_points:
                raise ValueError("No valid point geometry found.")

            for lat, lon in flat_points:
                payload = {
                    "adds": [
                        {
                            "attributes": {
                                "Site_AWP_Proj_Name": st.session_state.get("awp_proj_name"),
                                "Site_Proj_Name": st.session_state.get("proj_name"),
                                "Site_DOT_PF_Region": st.session_state.get("region_string"),
                                "Site_Borough_Census_Area": st.session_state.get("borough_string"),
                                "Site_Senate_District": st.session_state.get("senate_string"),
                                "Site_House_District": st.session_state.get("house_string"),
                                "parentglobalid": globalid
                            },
                            "geometry": {
                                "x": float(lon),
                                "y": float(lat),
                                "spatialReference": {"wkid": 4326}
                            }
                        }
                    ]
                }

                payloads.append(clean_payload(payload))

            return payloads


        # ---------------------------------------------------------
        # ROUTE CASE (POLYLINES)
        # ---------------------------------------------------------
        elif st.session_state.get("selected_route"):

            route = st.session_state["selected_route"]

            # --- FIXED NORMALIZER ---
            def normalize_paths(r):
                """
                Ensures the route is a list of paths, each path a list of [lat, lon] pairs.
                Removes extra nesting and enforces correct structure.
                """
                # Case 1: Single path: [[lat, lon], [lat, lon]]
                if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in r):
                    return [r]

                # Case 2: Already list of paths
                cleaned = []
                for item in r:
                    if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in item):
                        cleaned.append(item)
                    else:
                        # Flatten one more level if needed
                        for sub in item:
                            if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in sub):
                                cleaned.append(sub)
                return cleaned

            # Normalize input geometry
            paths_latlon = normalize_paths(route)

            # Build payloads
            for path in paths_latlon:

                # Convert [lat, lon] → [x, y] = [lon, lat]
                agol_path = [[pt[1], pt[0]] for pt in path]

                payload = {
                    "adds": [
                        {
                            "attributes": {
                                "Route_AWP_Proj_Name": st.session_state.get("awp_proj_name"),
                                "Route_Proj_Name": st.session_state.get("proj_name"),
                                "Route_DOT_PF_Region": st.session_state.get("region_string"),
                                "Route_Borough_Census_Area": st.session_state.get("borough_string"),
                                "Route_Senate_District": st.session_state.get("senate_string"),
                                "Route_House_District": st.session_state.get("house_string"),
                                "parentglobalid": globalid
                            },
                            "geometry": {
                                "paths": [agol_path],   # ← now correct, no extra nesting
                                "spatialReference": {"wkid": 4326}
                            }
                        }
                    ]
                }

                st.session_state['debug'] = payload
                payloads.append(clean_payload(payload))

            return payloads



        # ---------------------------------------------------------
        # BOUNDARY CASE (POLYGONS)
        # ---------------------------------------------------------
        elif st.session_state.get("selected_boundary"):

            boundary = st.session_state["selected_boundary"]

            def normalize_to_rings(b):
                if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in b):
                    return [b]
                rings = []
                for item in b:
                    if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in item):
                        rings.append(item)
                    else:
                        for sub in item:
                            if all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in sub):
                                rings.append(sub)
                return rings

            rings_latlon = normalize_to_rings(boundary)

            for ring in rings_latlon:
                converted = [[pt[1], pt[0]] for pt in ring]
                if converted[0] != converted[-1]:
                    converted.append(converted[0])

                payload = {
                    "adds": [
                        {
                            "attributes": {
                                "Boundary_AWP_Proj_Name": st.session_state.get("awp_proj_name"),
                                "Boundary_Proj_Name": st.session_state.get("proj_name"),
                                "Boundary_DOT_PF_Region": st.session_state.get("region_string"),
                                "Boundary_Borough_Census_Area": st.session_state.get("borough_string"),
                                "Boundary_Senate_District": st.session_state.get("senate_string"),
                                "Boundary_House_District": st.session_state.get("house_string"),
                                "parentglobalid": globalid
                            },
                            "geometry": {
                                "rings": [converted],
                                "spatialReference": {"wkid": 4326}
                            }
                        }
                    ]
                }

                payloads.append(clean_payload(payload))

            return payloads


        # ---------------------------------------------------------
        # NOTHING SELECTED
        # ---------------------------------------------------------
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
