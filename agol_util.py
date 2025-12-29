import json
import requests
import streamlit as st
import logging

# import os
# from dotenv import load_dotenv
# load_dotenv()
# agol_username = os.getenv("AGOL_USERNAME")
# agol_password = os.getenv("AGOL_PASSWORD")

agol_username = st.secrets["AGOL_USERNAME"]
agol_password = st.secrets["AGOL_PASSWORD"]


aashtoware = 'https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AWP_PROJECTS_EXPORT_XYTableToPoint_ExportFeatures/FeatureServer'
mileposts = 'https://services.arcgis.com/r4A0V7UzH9fcLVvv/arcgis/rest/services/AKDOT_Routes_Mileposts/FeatureServer'


def format_guid(value) -> str:
    """
    Ensures a GUID/GlobalID value is in the correct ArcGIS format.
    Accepts either a string or a single-element list of strings.
    """
    # If it's a list, take the first element
    if isinstance(value, list):
        if not value:  # empty list
            return None
        value = value[0]

    if not value or not isinstance(value, str):
        return None

    clean_value = value.strip().lstrip("{").rstrip("}")
    parts = clean_value.split("-")
    if len(parts) != 5 or not all(parts):
        return None

    return f"{{{clean_value}}}"


def get_agol_token() -> str:
    """
    Generates an authentication token for ArcGIS Online using a username and password.

    Args:
        username (str): The ArcGIS Online account username.
        password (str): The corresponding account password.

    Returns:
        str: A valid authentication token used to make authorized API requests.

    Raises:
        ValueError: If authentication fails or the token is not found in the response.
        ConnectionError: If there is a network issue preventing communication with the API.
    """
    
    # ArcGIS Online token generation URL
    url = "https://www.arcgis.com/sharing/rest/generateToken"

    # Payload required for authentication request
    data = {
        "username": agol_username,
        "password": agol_password,
        "referer": "https://www.arcgis.com",  # Required reference for token generation
        "f": "json"  # Request response format
    }
    
    try:
        # Send authentication request
        response = requests.post(url, data=data)

        # Validate HTTP response status
        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        # Parse JSON response
        token_data = response.json()

        # Extract token if authentication is successful
        if "token" in token_data:
            return token_data["token"]
        elif "error" in token_data:
            raise ValueError(f"Authentication failed: {token_data['error']['message']}")
        else:
            raise ValueError("Unexpected response format: Token not found.")

    except requests.exceptions.RequestException as e:
        # Handle network-related errors
        raise ConnectionError(f"Failed to connect to ArcGIS Online: {e}")
    


def get_unique_field_values(
    url: str,
    layer: str,
    field: str,
    where: str = "1=1",
    sort_type: str = None,   # "alpha" or "numeric"
    sort_order: str = "asc"  # "asc" or "desc"
) -> list:
    """
    Queries an ArcGIS REST API layer to retrieve all unique values from a specified field,
    with optional sorting.

    Args:
        url (str): The base URL of the ArcGIS REST API service.
        layer (str): The layer ID or name to query.
        field (str): The field name to retrieve unique values from.
        where (str, optional): SQL-style filter expression. Defaults to "1=1" (all records).
        sort_type (str, optional): "alpha" for alphabetical or "numeric" for numerical sorting.
        sort_order (str, optional): "asc" for ascending or "desc" for descending. Defaults to "asc".

    Returns:
        list: A list of unique values from the specified field, optionally sorted.

    Raises:
        ValueError: If authentication fails or the field does not exist.
        Exception: If the API request fails or returns an error message.
    """

    try:
        # Authenticate and get API token (ensure agol_username and agol_password are defined)
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # Construct query parameters
        params = {
            "where": where,
            "outFields": field,
            "returnDistinctValues": "true",  # ensures unique values
            "returnGeometry": "false",       # no geometry needed
            "f": "json",
            "token": token
        }

        # Formulate the query URL and execute the request
        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)

        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        # Validate that requested field exists
        available_fields = {field_info["name"] for field_info in data.get("fields", [])}
        if field not in available_fields:
            raise ValueError(f"Field '{field}' does not exist. Available fields: {available_fields}")

        # Extract unique values
        unique_values = []
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            if field in attributes and attributes[field] not in unique_values:
                unique_values.append(attributes[field])

        # Apply sorting if requested
        if sort_type:
            reverse = sort_order.lower() == "desc"

            if sort_type.lower() == "alpha":
                unique_values.sort(key=lambda x: str(x).lower(), reverse=reverse)
            elif sort_type.lower() == "numeric":
                try:
                    unique_values.sort(key=lambda x: float(x), reverse=reverse)
                except ValueError:
                    raise ValueError("Numeric sorting failed: field contains non-numeric values.")

        return unique_values

    except requests.exceptions.RequestException as req_error:
        raise Exception(f"Network error occurred: {req_error}")
    except ValueError as val_error:
        raise ValueError(val_error)
    except Exception as gen_error:
        raise Exception(gen_error)
    




def get_multiple_fields(url: str, layer: int = 0, fields: list = None) -> list:
    """
    Queries an ArcGIS REST API table layer to retrieve records with specified fields.

    Args:
        url (str): The base URL of the ArcGIS REST API service.
        layer (int): The layer ID to query. Defaults to 0.
        fields (list): A list of field names to request from the service.

    Returns:
        list: A list of dictionaries with keys based on the feature attributes returned.
    """
    try:
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # If no fields provided, request all
        out_fields = ",".join(fields) if fields else "*"

        params = {
            "where": "1=1",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
            "token": token
        }

        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)

        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        results = []
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            # Directly use the returned attribute names as dictionary keys
            results.append({k: v for k, v in attributes.items()})

        return results

    except Exception as e:
        raise Exception(f"Error retrieving project records: {e}")




def select_record(url: str, layer: int, id_field: str, id_value: str, fields = "*", return_geometry = False):
    """
    Queries an ArcGIS REST API table layer to retrieve a single record by ID field.

    Args:
        url (str): The base URL of the ArcGIS REST API service.
        layer (int): The layer ID to query.
        id_field (str): The name of the field to filter by (e.g., 'GlobalID', 'ProposalId').
        id_value (str): The value to match in the ID field.

    Returns:
        list: A list of matching feature dictionaries.
    """
    try:
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        params = {
            "where": f"{id_field}='{id_value}'",
            "outFields": fields,
            "returnGeometry": str(return_geometry).lower(),
            "outSR": 4326,
            "f": "json",
            "token": token
        }

        query_url = f"{url}/{layer}/query"
        response = requests.get(query_url, params=params)

        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        return data.get("features", [])

    except Exception as e:
        raise Exception(f"Error retrieving project record: {e}")
    


def delete_project(url: str, layer: int, globalid: str) -> bool:
    """
    Delete a project from an ArcGIS Feature Service using its GlobalID.

    This function calls the ArcGIS REST API `deleteFeatures` endpoint to remove
    a feature from the specified layer. It uses a `where` clause to match the
    provided GlobalID.

    Args:
        url (str): Base URL of the Feature Service (ending with /FeatureServer).
        layer (int): Layer index within the Feature Service where the project resides.
        globalid (str): The GlobalID of the project to delete.

    Returns:
        bool: True if the project was successfully deleted, False otherwise.

    Raises:
        ValueError: If authentication fails or no token is retrieved.
    """

    try:
        # Retrieve authentication token
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")

        # Parameters for the deleteFeatures request
        params = {
            "where": f"GlobalID='{globalid}'",  # Filter by GlobalID
            "f": "json",                        # Response format
            "token": token                      # Authentication token
        }

        # Construct deleteFeatures endpoint URL
        delete_url = f"{url}/{layer}/deleteFeatures"

        # Send POST request to ArcGIS REST API
        response = requests.post(delete_url, data=params)
        result = response.json()

        # Check response for deleteResults
        if "deleteResults" in result:
            success = all(r.get("success", False) for r in result["deleteResults"])
            return True
        else:
            print("Unexpected response:", result)
            return False

    except Exception as e:
        # Catch any errors (network, JSON parsing, etc.)
        print(f"Error deleting project: {e}")
        return False






class AGOLQueryIntersect:
    def __init__(self, url, layer, geometry, fields="*", return_geometry=False,
                 list_values=None, string_values=None):
        self.url = url
        self.layer = layer
        self.geometry = self._swap_coords(geometry)  # swap coords if needed
        self.fields = fields
        self.return_geometry = return_geometry
        self.list_values_field = list_values
        self.string_values_field = string_values
        self.token = self._authenticate()

        # Run query immediately on initialization
        self.results = self._execute_query()

        # If list_values is provided, store unique values in a list
        self.list_values = []
        if self.list_values_field:
            self.list_values = self._extract_unique_values(self.list_values_field)

        # If string_values is provided, store unique values in a comma-separated string
        self.string_values = ""
        if self.string_values_field:
            unique_list = self._extract_unique_values(self.string_values_field)
            self.string_values = ",".join(map(str, unique_list))

    def _authenticate(self):
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")
        return token

    def _swap_coords(self, geometry):
        """Swap coordinates from [lat, lon] to [lon, lat] if needed."""
        if isinstance(geometry, list):
            # Point
            if len(geometry) == 2 and all(isinstance(coord, (int, float)) for coord in geometry):
                return [geometry[1], geometry[0]]  # swap
            # Line
            elif all(isinstance(coord, list) and len(coord) == 2 for coord in geometry):
                return [[pt[1], pt[0]] for pt in geometry]  # swap each pair
        return geometry

    def _build_geometry(self):
        if isinstance(self.geometry, list):
            # Point
            if len(self.geometry) == 2 and all(isinstance(coord, (int, float)) for coord in self.geometry):
                geometry_dict = {
                    "x": self.geometry[0],
                    "y": self.geometry[1],
                    "spatialReference": {"wkid": 4326}
                }
                geometry_type_str = "esriGeometryPoint"

            # Line
            elif all(
                isinstance(coord, list) and len(coord) == 2 and
                all(isinstance(val, (int, float)) for val in coord)
                for coord in self.geometry
            ):
                if len(self.geometry) >= 2:
                    geometry_dict = {
                        "paths": [self.geometry],
                        "spatialReference": {"wkid": 4326}
                    }
                    geometry_type_str = "esriGeometryPolyline"
                else:
                    raise ValueError("Invalid geometry: A line must have at least two coordinate pairs.")
            else:
                raise ValueError("Invalid geometry format.")
        else:
            raise ValueError("Invalid geometry: Geometry must be a list.")

        return geometry_dict, geometry_type_str

    def _execute_query(self):
        geometry_dict, geometry_type_str = self._build_geometry()

        params = {
            "geometry": json.dumps(geometry_dict),
            "geometryType": geometry_type_str,
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "where": "1=1",
            "outFields": self.fields,
            "returnGeometry": self.return_geometry,
            "outSR": 4326,
            "f": "json",
            "token": self.token
        }

        query_url = f"{self.url}/{self.layer}/query"
        response = requests.get(query_url, params=params)

        if response.status_code != 200:
            raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

        data = response.json()
        if "error" in data:
            raise Exception(f"API Error: {data['error']['message']} - {data['error'].get('details', [])}")

        results = []
        requested_fields = [f.strip() for f in self.fields.split(",") if f.strip()]
        for feature in data.get("features", []):
            attributes = feature.get("attributes", {})
            filtered_attrs = {f: attributes.get(f) for f in requested_fields} if self.fields != "*" else attributes
            feature_package = {"attributes": filtered_attrs}
            if self.return_geometry:
                feature_package["geometry"] = feature.get("geometry", {})
            results.append(feature_package)

        return results

    def _extract_unique_values(self, field_name):
        """Return a unique list of values for the specified field. Blank if no results."""
        if not self.results:
            return []  # no features returned
        available_fields = {f for feature in self.results for f in feature["attributes"].keys()}
        if field_name not in available_fields:
            return []  # gracefully return blank list if field not found
        values = [feature["attributes"].get(field_name) for feature in self.results if feature["attributes"].get(field_name) is not None]
        return list(set(values))
    



class AGOLDataLoader:
    def __init__(self, url: str, layer: int):
        """
        Initialize the loader with AGOL service URL and layer ID.
        Token is retrieved via _authenticate().
        """
        self.url = url.rstrip("/")
        self.layer = layer
        self.token = self._authenticate()
        self.success = False
        self.message = None
        self.globalids = []
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("AGOLDataLoader")

    def _authenticate(self):
        """
        Authenticate with AGOL and return a valid token.
        """
        token = get_agol_token()
        if not token:
            raise ValueError("Authentication failed: Invalid token.")
        return token

    def add_features(self, payload: dict):
        """
        Add features to the AGOL feature layer using applyEdits.
        Logs stages and sets success/message/globalids.
        Rolls back if unsuccessful.
        """
        endpoint = f"{self.url}/{self.layer}/applyEdits"
        self.logger.info("Starting add_features process...")

        try:
            # Use data= and json.dumps for adds
            resp = requests.post(
                endpoint,
                data={
                    "f": "json",
                    "token": self.token,
                    "adds": json.dumps(payload["adds"])
                }
            )
            self.logger.info("Raw response text: %s", resp.text)
            result = resp.json()

            if "addResults" in result:
                add_results = result["addResults"]
                failures = [r for r in add_results if not r.get("success")]

                if failures:
                    self.success = False
                    error_messages = []
                    for r in failures:
                        err = r.get("error")
                        if err:
                            error_messages.append(
                                f"Code {err.get('code')}: {err.get('description')}"
                            )
                    self.message = (
                        f"Failed to add {len(failures)} feature(s). "
                        f"Errors: {', '.join(error_messages)}"
                    )
                    self.logger.error(self.message)
                else:
                    self.success = True
                    self.message = "All features added successfully."
                    self.globalids = [
                        r.get("globalId") for r in add_results if r.get("success")
                    ]
                    self.logger.info(self.message)
            else:
                self.success = False
                self.message = f"Unexpected response: {result}"
                self.logger.error(self.message)

        except Exception as e:
            self.success = False
            self.message = f"Error during add_features: {str(e)}"
            self.logger.exception(self.message)

        return {
            "success": self.success,
            "message": self.message,
            "globalids": self.globalids
        }