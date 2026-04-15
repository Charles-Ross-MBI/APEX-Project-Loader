# =============================================================================
# FOOTPRINT MANAGEMENT TAB
# =============================================================================
import streamlit as st
from streamlit_folium import st_folium
import folium
from shapely.geometry import LineString, Point
import json
from agol.agol_util import (
    select_record,
    AGOLDataLoader
)
from agol.agol_payloads import (
    manage_footprint_project_payload,
    manage_footprint_deletes_payload,
    location_payload,
    geometry_payload,
    geography_payload,
)
from util.map_util import (
    add_small_geocoder,
    set_bounds_point,
    set_bounds_route,
    set_bounds_boundary,
    set_zoom,
    geometry_to_folium
)
from util.read_only_util import ro_widget
from util.input_util import (
    fmt_string,
    fmt_date,
    fmt_agol_date,
    fmt_currency,
    fmt_int,
    fmt_int_or_none,
    fmt_date_or_none,
    widget_key,
)
# ⬇️ also import aashtoware_project so we can render the selector
from util.streamlit_util import session_selectbox, aashtoware_project
from typing import Optional, Dict, Any, List

from util.geometry_util import (
    point_shapefile,
    polyline_shapefile,
    polygon_shapefile,
    enter_latlng,
    draw_point,
    draw_line,
    draw_boundary,
    aashtoware_point,
    aashtoware_path,
)
from util.streamlit_util import (
    segmented_with_safe_default,
    handle_project_type_change,
    handle_upload_method_change,
    run_queries_if_geometry_changed,
    render_geographies_expander,
)
from agol.agol_util import aashtoware_geometry  # (kept for side effects elsewhere if needed)
from agol.agol_district_queries import run_district_queries  # noqa: F401 (referenced in utilities)
from steps.load_geometry import load_geometry_app

# -----------------------------------------------------------------------------
# Initialize Keys
# -----------------------------------------------------------------------------
if "update_footprint_mode" not in st.session_state:
    st.session_state["update_footprint_mode"] = False

# -----------------------------------------------------------------------------
# Initialize AWP Session Keys
# -----------------------------------------------------------------------------
if "is_awp" not in st.session_state:
    st.session_state["is_awp"] = False
if "awp_id" not in st.session_state:
    st.session_state["awp_id"] = None
if "awp_geometry_points" not in st.session_state:
    st.session_state["awp_geometry_points"] = None

# -----------------------------------------------------------------------------
# Helper: validate AWP Contract ID
# -----------------------------------------------------------------------------
def _is_valid_awp_contract_id(value: Any) -> bool:
    """Return True when an AWP Contract ID value is present/usable."""
    if value is None:
        return False
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return False
        if s.upper() in {"N/A", "NA", "NONE", "NULL"}:
            return False
        return True
    if isinstance(value, (int, float)):
        return value != 0
    return True



# -----------------------------------------------------------------------------
# Helper: fetch active project record
# -----------------------------------------------------------------------------
def _get_project_record():
    apex_guid = st.session_state.get("apex_guid")
    url = st.session_state.get("apex_url")
    layer = st.session_state.get("projects_layer")
    if not (apex_guid and url and layer is not None):
        return None
    recs = select_record(
        url=url,
        layer=layer,
        id_field="globalid",
        id_value=apex_guid,
        fields="*",
        return_geometry=False,
    )
    return recs[0]["attributes"] if recs else None


def _normalize_features(maybe_rec: Any) -> List[Dict[str, Any]]:
    """Normalize a select_record() return value into a plain list of feature dicts."""
    if maybe_rec is None:
        return []
    if isinstance(maybe_rec, dict) and isinstance(maybe_rec.get("features"), list):
        return maybe_rec.get("features") or []
    if isinstance(maybe_rec, list):
        return maybe_rec
    if isinstance(maybe_rec, dict) and ("attributes" in maybe_rec or "geometry" in maybe_rec):
        return [maybe_rec]
    return []


def _get_objectid_from_attributes(attrs: Dict[str, Any]) -> Optional[int]:
    """Return an OBJECTID (int) from an attributes dict, handling common casing variants."""
    if not isinstance(attrs, dict):
        return None
    for k in ("OBJECTID", "objectid", "objectId", "ObjectId", "ObjectID"):
        if k in attrs and attrs.get(k) is not None:
            try:
                return int(attrs.get(k))
            except Exception:
                return None
    return None


def _ensure_objectid_key(attrs: Dict[str, Any]) -> None:
    """Ensure attrs contains an 'OBJECTID' key when any objectid variant is present."""
    if not isinstance(attrs, dict):
        return
    if "OBJECTID" in attrs and attrs.get("OBJECTID") is not None:
        return
    for k in ("objectid", "objectId", "ObjectId", "ObjectID"):
        if k in attrs and attrs.get(k) is not None:
            attrs["OBJECTID"] = attrs.get(k)
            return


def _collect_objectids_from_features(features: List[Dict[str, Any]]) -> List[int]:
    """Collect OBJECTIDs from feature list; also normalizes OBJECTID key in-place."""
    out: List[int] = []
    for feat in features or []:
        attrs = (feat or {}).get("attributes") or {}
        _ensure_objectid_key(attrs)
        oid = _get_objectid_from_attributes(attrs)
        if oid is not None:
            out.append(oid)
    return out


def _resolve_new_project_type() -> Optional[str]:
    """Resolve the *new* project type based on which geometry selector is active."""
    if st.session_state.get("selected_point") is not None:
        return "Site"
    if st.session_state.get("selected_route") is not None:
        return "Route"
    if st.session_state.get("selected_boundary") is not None:
        return "Boundary"
    return None


def _project_type_to_footprint_layer(proj_type: Optional[str]) -> Optional[int]:
    """Map a project type to its configured footprint layer index."""
    if proj_type == "Site":
        return st.session_state.get("sites_layer")
    if proj_type == "Route":
        return st.session_state.get("routes_layer")
    if proj_type == "Boundary":
        return st.session_state.get("boundaries_layer")
    return None



def _first_nonempty(mapping: dict, keys: list):
    """Return first non-empty value from mapping for any key in keys."""
    for k in keys:
        if k in mapping:
            v = mapping.get(k)
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return v
    return None


def _as_list(value):
    """Normalize a value into a list (for *_list session keys)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v is not None and (not isinstance(v, str) or v.strip())]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # support comma-delimited or JSON-like list strings
        if ',' in s:
            return [p.strip() for p in s.split(',') if p.strip()]
        return [s]
    return [value]


def _seed_payload_builder_state_from_project(project_rec: dict) -> None:
    """
    Seed st.session_state keys expected by geometry_payload/location_payload/geography_payload
    from the parent Projects record (project_rec).
    """
    if not isinstance(project_rec, dict) or not project_rec:
        return

    # parent globalid used by child layers as parentglobalid
    if st.session_state.get("apex_globalid") is None:
        st.session_state["apex_globalid"] = (
            project_rec.get("globalid")
            or project_rec.get("GlobalID")
            or st.session_state.get("apex_guid")
        )

    # names
    if st.session_state.get("proj_name") is None:
        st.session_state["proj_name"] = _first_nonempty(project_rec, [
            "Proj_Name", "Project_Name", "ProjectName", "proj_name", "project_name", "Name", "Title"
        ])

    if st.session_state.get("awp_proj_name") is None:
        st.session_state["awp_proj_name"] = _first_nonempty(project_rec, [
            "AWP_Proj_Name", "Awp_Proj_Name", "awp_proj_name", "AWP_Project_Name", "ContractID", "awp_id"
        ])

    # admin strings used by geometry/location payloads
    if st.session_state.get("region_string") is None:
        st.session_state["region_string"] = _first_nonempty(project_rec, [
            "DOT_PF_Region", "Proj_DOT_PF_Region", "Region", "region_string"
        ])

    if st.session_state.get("borough_string") is None:
        st.session_state["borough_string"] = _first_nonempty(project_rec, [
            "Borough_Census_Area", "Proj_Borough_Census_Area", "Borough", "borough_string"
        ])

    if st.session_state.get("senate_string") is None:
        st.session_state["senate_string"] = _first_nonempty(project_rec, [
            "Senate_District", "Proj_Senate_District", "senate_string"
        ])

    if st.session_state.get("house_string") is None:
        st.session_state["house_string"] = _first_nonempty(project_rec, [
            "House_District", "Proj_House_District", "house_string"
        ])

    # geography_payload(...) expects {name}_list keys: region_list, borough_list, senate_list, house_list
    # Prefer the explicit list fields already present in your project record.
    if st.session_state.get("region_list") is None:
        st.session_state["region_list"] = _as_list(_first_nonempty(project_rec, ["List_DOT_PF_Region", "region_list"]))

    if st.session_state.get("borough_list") is None:
        st.session_state["borough_list"] = _as_list(_first_nonempty(project_rec, ["List_Borough_Census_Area", "borough_list"]))

    if st.session_state.get("senate_list") is None:
        st.session_state["senate_list"] = _as_list(_first_nonempty(project_rec, ["List_Senate_District", "senate_list"]))

    if st.session_state.get("house_list") is None:
        st.session_state["house_list"] = _as_list(_first_nonempty(project_rec, ["List_House_District", "house_list"]))



def _clear_footprint_and_load_geometry_state():
    """Clear session_state keys created by footprint.py and by load_geometry step."""
    keys_to_clear = {
        # --- footprint.py-created keys ---
        "update_footprint_mode",
        "is_awp",
        "awp_id",
        "awp_geometry_points",
        "footprint_item",
        "deploy_objectids",
        "last_footprint_deploy_result",
        "locations_raw_record",
        "locations_records",
        "geography_raw_records",
        "geography_records",
        "house_records",
        "senate_records",
        "region_records",
        "borough_records",
        "List_House_District",
        "List_Senate_District",
        "List_DOT_PF_Region",
        "List_Borough_Census_Area",

        # --- payload-builder seed keys (manager context) ---
        "apex_globalid",
        "proj_name",
        "awp_proj_name",
        "region_list",
        "borough_list",
        "senate_list",
        "house_list",
        "center",

        # --- load_geometry-created keys (from load_geometry step) ---
        "footprint_submitted",
        "just_submitted_geometry",
        "project_geometry",
        "project_geom_type",
        "project_geom",
        "selected_point",
        "selected_route",
        "selected_boundary",
        "option",
        "prev_geometry_option",
        "prev_geometry_project_type",
        "submitted_geom_sig",
        "submitted_option",
        "submitted_project_type",
        "geometry_form_version",
        "project_type",
        "geom_type",
        "house_string",
        "senate_string",
        "region_string",
        "borough_string",
    }

    for k in keys_to_clear:
        st.session_state.pop(k, None)



def _reset_to_fresh_run_after_deploy():
    """Clear state and rerun the script from the top (fresh first run)."""
    _clear_footprint_and_load_geometry_state()
    st.rerun()


def build_project_update_payload(project_rec: Dict[str, Any], new_proj_type: str) -> Dict[str, Any]:
    """Build the applyEdits update payload for the main Projects layer."""
    if not project_rec:
        return {"updates": []}

    # NOTE: Keep this minimal on purpose. We'll add additional attributes later.
    # Requires OBJECTID so AGOL can target the correct feature for update.
    attrs = {
        "OBJECTID": project_rec.get("OBJECTID") or project_rec.get("objectId") or project_rec.get("objectid"),
        "Proj_Type": new_proj_type,
    }
    attrs = {k: v for k, v in attrs.items() if v is not None}

    return {"updates": [{"attributes": attrs}]}


def build_delete_payload_from_rec(maybe_rec: Any) -> Dict[str, Any]:
    """Build an applyEdits deletes payload from a select_record() return value."""
    features = _normalize_features(maybe_rec)
    oids = _collect_objectids_from_features(features)
    return {"deletes": oids}


def build_footprint_add_payload(apex_guid: str, esri_geom: Dict[str, Any]) -> Dict[str, Any]:
    """Build the applyEdits adds payload for the *new* footprint geometry."""
    if not apex_guid or not esri_geom:
        return {"adds": []}

    # NOTE: Keep this minimal on purpose. We'll add additional attributes later.
    attrs = {"parentglobalid": apex_guid}

    return {"adds": [{"attributes": attrs, "geometry": esri_geom}]}


def build_geography_add_payloads(apex_guid: str) -> Dict[str, Dict[str, Any]]:
    """Build placeholder add payloads for House/Senate/Region/Borough layers."""
    return {
        "house": {"adds": []},
        "senate": {"adds": []},
        "region": {"adds": []},
        "borough": {"adds": []},
    }


def deploy_to_agol_footprint_update(
    *,
    project_payload: Dict[str, Any],
    old_footprint_layer: Optional[int],
    old_footprint_delete_payload: Dict[str, Any],
    locations_delete_payload: Dict[str, Any],
    new_footprint_layer: Optional[int],
    new_footprint_add_payload: Any,
    new_locations_add_payload: Any,
    geo_delete_payloads: Dict[str, Dict[str, Any]],
    geo_add_payloads: Dict[str, Any],
    progress_placeholder: Optional[st.delta_generator.DeltaGenerator] = None,
) -> Dict[str, Any]:
    """Deploy helper for UPDATE FOOTPRINT flow.

    Executes AGOL applyEdits operations in an ordered sequence using AGOLDataLoader:
      1) Update main project (projects_layer)
      2) Delete old footprint records (old footprint layer)
      3) Delete old locations records (locations_layer)
      4) Delete old geography records (house/senate/borough/region layers)
      5) Add new locations records (locations_layer)
      6) Add new footprint records (new footprint layer)
      7) Add new geography records (house/senate/borough/region layers)

    NOTE on add payload format:
      - Add payloads may be provided as a single applyEdits payload dict:
          {"adds": [ {"attributes": {...}, "geometry": {...}}, ... ]}
      - OR as a list of applyEdits payload dicts (multiple payloads):
          [ {"adds": [...]}, {"adds": [...]}, ... ]
      Whatever the payload creator returns is treated as canonical and will be passed through.

    All operations use st.session_state['apex_url'] for the service URL.
    Empty delete/add payloads are treated as no-ops (success).

    Returns:
        dict: { success, message, stages: { ... } }
    """

    base_url = st.session_state.get("apex_url")
    projects_layer = st.session_state.get("projects_layer")
    locations_layer = st.session_state.get("locations_layer")

    if base_url is None or projects_layer is None:
        return {"success": False, "message": "AGOL Projects layer is not configured."}

    def _progress(frac: float, text: str):
        if progress_placeholder is not None:
            progress_placeholder.progress(frac, text=text)
        else:
            st.progress(frac, text=text)

    def _as_oid_list(maybe_payload: Any) -> List[int]:
        """Extract OBJECTIDs from either {'deletes': [...]} or {'updates': [...]} payloads."""
        if not isinstance(maybe_payload, dict):
            return []

        if "deletes" in maybe_payload:
            deletes_val = maybe_payload.get("deletes")
            if deletes_val is None:
                return []
            if isinstance(deletes_val, str):
                out: List[int] = []
                for part in [p.strip() for p in deletes_val.split(",") if p.strip()]:
                    try:
                        out.append(int(part))
                    except Exception:
                        pass
                return out
            if isinstance(deletes_val, list):
                out: List[int] = []
                for v in deletes_val:
                    try:
                        out.append(int(v))
                    except Exception:
                        pass
                return out
            return []

        if "updates" in maybe_payload and isinstance(maybe_payload.get("updates"), list):
            out: List[int] = []
            for feat in maybe_payload.get("updates") or []:
                attrs = (feat or {}).get("attributes") or {}
                oid = attrs.get("OBJECTID")
                if oid is None:
                    continue
                try:
                    out.append(int(oid))
                except Exception:
                    continue
            return out

        return []

    def _validate_adds_payload(payload: Any, *, require_nonempty: bool = False) -> Dict[str, Any]:
        """Validate AGOL 'adds' payload.

        Accepts either:
          - dict with key 'adds' -> list
          - list of dicts each with key 'adds' -> list

        Returns:
          { ok: bool, count: int, message: str }
        """
        # Treat None/empty dict/empty list as empty (caller decides if that's allowed)
        if payload is None or payload == {} or payload == []:
            if require_nonempty:
                return {"ok": False, "count": 0, "message": "Add payload is missing/empty."}
            return {"ok": True, "count": 0, "message": "No features to add."}

        def _count_adds_dict(d: Dict[str, Any]) -> int:
            adds = d.get("adds")
            if not isinstance(adds, list):
                return -1
            return len(adds)

        # Single payload dict
        if isinstance(payload, dict):
            cnt = _count_adds_dict(payload)
            if cnt < 0:
                return {"ok": False, "count": 0, "message": "Add payload must be a dict with an 'adds' list."}
            if require_nonempty and cnt == 0:
                return {"ok": False, "count": 0, "message": "Add payload has no 'adds' features."}
            return {"ok": True, "count": cnt, "message": "OK"}

        # Multiple payload dicts
        if isinstance(payload, list):
            total = 0
            for i, item in enumerate(payload):
                if not isinstance(item, dict):
                    return {"ok": False, "count": 0, "message": f"Add payload list item {i} is not a dict."}
                cnt = _count_adds_dict(item)
                if cnt < 0:
                    return {"ok": False, "count": 0, "message": f"Add payload list item {i} must contain an 'adds' list."}
                total += cnt
            if require_nonempty and total == 0:
                return {"ok": False, "count": 0, "message": "Add payload list contains no 'adds' features."}
            return {"ok": True, "count": total, "message": "OK"}

        return {"ok": False, "count": 0, "message": "Add payload must be a dict or a list of dict payloads."}

    def _delete_with_loader(layer: Optional[int], delete_payload: Dict[str, Any]) -> Dict[str, Any]:
        if layer is None:
            return {"success": True, "message": "No layer resolved; skip deletes.", "objectids": []}

        oids = _as_oid_list(delete_payload)
        if not oids:
            return {"success": True, "message": "No records to delete.", "objectids": []}

        loader = AGOLDataLoader(base_url, layer)
        coerced = {"updates": [{"attributes": {"OBJECTID": oid}} for oid in oids]}
        return loader.delete_features(coerced)

    def _add_with_loader(layer: Optional[int], add_payload: Any) -> Dict[str, Any]:
        if layer is None:
            return {"success": False, "message": "Layer not resolved for adds.", "globalids": []}

        v = _validate_adds_payload(add_payload, require_nonempty=False)
        if not v["ok"]:
            return {"success": False, "message": v["message"], "globalids": []}
        if v["count"] == 0:
            return {"success": True, "message": "No features to add.", "globalids": []}

        loader = AGOLDataLoader(base_url, layer)

        # Pass through canonical format from payload creator.
        if isinstance(add_payload, dict):
            return loader.add_features(add_payload)

        # Multiple payloads: apply each payload exactly as provided.
        stage_results: List[Dict[str, Any]] = []
        globalids: List[Any] = []
        for item in add_payload:
            # Skip empty adds blocks (allowed)
            if isinstance(item, dict) and isinstance(item.get("adds"), list) and len(item.get("adds")) == 0:
                continue
            r = loader.add_features(item)
            stage_results.append(r)
            if isinstance(r, dict):
                gids = r.get("globalids") or r.get("globalIds") or []
                if isinstance(gids, list):
                    globalids.extend(gids)
            if not (isinstance(r, dict) and r.get("success")):
                return {
                    "success": False,
                    "message": (r or {}).get("message", "Add features failed."),
                    "results": stage_results,
                    "globalids": globalids,
                }

        return {"success": True, "message": "Add features completed.", "results": stage_results, "globalids": globalids}

    def _update_with_loader(layer: Optional[int], update_payload: Dict[str, Any]) -> Dict[str, Any]:
        if layer is None:
            return {"success": False, "message": "Layer not resolved for updates.", "globalids": []}
        if not isinstance(update_payload, dict) or not isinstance(update_payload.get("updates"), list) or not update_payload.get("updates"):
            return {"success": False, "message": "Update payload is missing/empty.", "globalids": []}
        loader = AGOLDataLoader(base_url, layer)
        return loader.update_features(update_payload)

    # ------------------------------------------------------------------
    # Validate essentials
    # ------------------------------------------------------------------
    _progress(0.0, "Preparing deployment…")

    if not isinstance(project_payload, dict) or not project_payload.get("updates"):
        return {"success": False, "message": "Project update payload is missing/empty."}

    if new_footprint_layer is None:
        return {"success": False, "message": "New footprint layer is not resolved."}

    v_fp = _validate_adds_payload(new_footprint_add_payload, require_nonempty=True)
    if not v_fp["ok"]:
        return {"success": False, "message": f"New footprint add payload invalid: {v_fp['message']}"}

    # ------------------------------------------------------------------
    # Execute stages
    # ------------------------------------------------------------------
    results: Dict[str, Any] = {"success": False, "stages": {}}

    # 1) Update Project
    _progress(0.10, "Stage 1/7: Updating project…")
    r_project = _update_with_loader(projects_layer, project_payload)
    results["stages"]["project_update"] = r_project
    if not r_project.get("success"):
        results["message"] = f"Project update failed: {r_project.get('message')}"
        _progress(1.0, "Deployment failed.")
        return results

    # 2) Delete old footprint
    _progress(0.25, "Stage 2/7: Deleting old footprint records…")
    r_fp_del = _delete_with_loader(old_footprint_layer, old_footprint_delete_payload)
    results["stages"]["old_footprint_deletes"] = r_fp_del
    if not r_fp_del.get("success"):
        results["message"] = f"Old footprint deletes failed: {r_fp_del.get('message')}"
        _progress(1.0, "Deployment failed.")
        return results

    # 3) Delete old locations
    _progress(0.35, "Stage 3/7: Deleting old locations records…")
    r_loc_del = _delete_with_loader(locations_layer, locations_delete_payload)
    results["stages"]["locations_deletes"] = r_loc_del
    if not r_loc_del.get("success"):
        results["message"] = f"Locations deletes failed: {r_loc_del.get('message')}"
        _progress(1.0, "Deployment failed.")
        return results

    # 4) Delete geography
    _progress(0.45, "Stage 4/7: Deleting old geography records…")
    geo_layer_map = {
        "house": st.session_state.get("house_layer"),
        "senate": st.session_state.get("senate_layer"),
        "borough": st.session_state.get("bor_layer"),
        "region": st.session_state.get("region_layer"),
    }

    geo_del_results: Dict[str, Any] = {}
    for name, layer in geo_layer_map.items():
        payload = (geo_delete_payloads or {}).get(name) or {}
        geo_del_results[name] = _delete_with_loader(layer, payload)
        if not geo_del_results[name].get("success"):
            results["stages"]["geography_deletes"] = geo_del_results
            results["message"] = f"Geography deletes failed ({name}): {geo_del_results[name].get('message')}"
            _progress(1.0, "Deployment failed.")
            return results

    results["stages"]["geography_deletes"] = geo_del_results

    # 5) Add locations
    _progress(0.60, "Stage 5/7: Adding new locations records…")
    r_loc_add = _add_with_loader(locations_layer, new_locations_add_payload)
    results["stages"]["locations_adds"] = r_loc_add
    if not r_loc_add.get("success"):
        results["message"] = f"Locations adds failed: {r_loc_add.get('message')}"
        _progress(1.0, "Deployment failed.")
        return results

    # 6) Add footprint
    _progress(0.75, "Stage 6/7: Adding new footprint geometry…")
    r_fp_add = _add_with_loader(new_footprint_layer, new_footprint_add_payload)
    results["stages"]["new_footprint_adds"] = r_fp_add
    if not r_fp_add.get("success"):
        results["message"] = f"Footprint adds failed: {r_fp_add.get('message')}"
        _progress(1.0, "Deployment failed.")
        return results

    # 7) Add geography
    _progress(0.90, "Stage 7/7: Adding new geography records…")
    geo_add_results: Dict[str, Any] = {}
    for name, layer in geo_layer_map.items():
        payload = (geo_add_payloads or {}).get(name) or {}
        geo_add_results[name] = _add_with_loader(layer, payload)
        if not geo_add_results[name].get("success"):
            results["stages"]["geography_adds"] = geo_add_results
            results["message"] = f"Geography adds failed ({name}): {geo_add_results[name].get('message')}"
            _progress(1.0, "Deployment failed.")
            return results

    results["stages"]["geography_adds"] = geo_add_results

    results["success"] = True
    results["message"] = "Deployment completed successfully."
    _progress(1.0, "Deployment complete.")
    return results
def manage_footprint():

    st.markdown("##### MANAGE PROJECT FOOTPRINT")
    st.caption("This tab displays the existing footprint for the selected project and allows users to review it for accuracy. "
    "Users may update the footprint as needed to reflect current project conditions or scope."
    )

    # APEX URL
    base_url = st.session_state.get("apex_url")

    # Projects Layer
    projects_layer = st.session_state.get('projects_layer')

    # Footprint Layers
    sites_layer = st.session_state.get("sites_layer")
    routes_layer = st.session_state.get("routes_layer")
    boundaries_layer = st.session_state.get("boundaries_layer")

    # Geography Layers
    region_layer = st.session_state.get("region_layer")
    bor_layer = st.session_state.get("bor_layer")
    senate_layer = st.session_state.get("senate_layer")
    house_layer = st.session_state.get("house_layer")
    
    if base_url is None or projects_layer is None:
        st.error("AGOL Projects layer is not configured (missing apex_url or projects_layer).")
    
    if sites_layer is None or routes_layer is None or boundaries_layer is None:
        st.error("AGOL Footprints layers are not configured (UPDATE THIS).")
        
    if region_layer is None or bor_layer is None or senate_layer is None or house_layer is None:
        st.error("AGOL Geospatial layers are not configured (UPDATE THIS).")
        

    # Pull Footprint Information from Project Record
    rec = _get_project_record()

    # --------------------------------------------------------------
    # AWP: if project has a valid AWP_Contract_ID, pull AWP geometry
    # --------------------------------------------------------------
    awp_id = rec.get("AWP_Contract_ID") if rec else None
    st.session_state["awp_id"] = awp_id
    if _is_valid_awp_contract_id(awp_id):
        st.session_state["is_awp"] = True
        st.session_state["awp_geometry_points"] = aashtoware_geometry(awp_id)
    else:
        st.session_state["is_awp"] = False
        st.session_state["awp_geometry_points"] = None

    # --------------------------------------------------------------
    # PROJ TYPE: Determine Project Type from Rec
    # --------------------------------------------------------------
    proj_type = rec.get("Proj_Type")

    # Pull Footprint Information
    footprint_rec = None
    if proj_type == "Site":
        footprint_rec = select_record(
            url = base_url,
            layer = sites_layer,
            id_field = 'parentglobalid',
            id_value = st.session_state['apex_guid'],
            fields = '*',
            return_geometry=True
        )
    elif proj_type == 'Route':
        footprint_rec = select_record(
            url = base_url,
            layer = routes_layer,
            id_field = 'parentglobalid',
            id_value = st.session_state['apex_guid'],
            fields = '*',
            return_geometry=True
        )
    elif proj_type == 'Boundary':
        footprint_rec = select_record(
            url = base_url,
            layer = boundaries_layer,
            id_field = 'parentglobalid',
            id_value = st.session_state['apex_guid'],
            fields = '*',
            return_geometry=True
        )

    # --------------------------------------------------------------
    # PROJ TYPE: Determine Project Type from Rec
    # --------------------------------------------------------------
    st.session_state['List_House_District'] = rec.get("List_House_District")
    st.session_state['List_Senate_District'] = rec.get("List_Senate_District")
    st.session_state['List_Borough_Census_Area'] = rec.get("List_Borough_Census_Area")
    st.session_state['List_DOT_PF_Region'] = rec.get("List_DOT_PF_Region")


    # ------------------------------------------------------------------
    # Pull Geography Records (stored geography layers) by Project GUID
    # - These are NOT the intersect services; these are the APEX geography layers
    # - Filter field is parentglobalid (matches footprint lookup behavior)
    # ------------------------------------------------------------------
    apex_guid = st.session_state.get("apex_guid")
    geography_raw = {"region": None, "borough": None, "senate": None, "house": None}
    if apex_guid:
        geography_raw["region"] = select_record(
            url=base_url,
            layer=region_layer,
            id_field="parentglobalid",
            id_value=apex_guid,
            fields="*",
            return_geometry=False
        )
        geography_raw["borough"] = select_record(
            url=base_url,
            layer=bor_layer,
            id_field="parentglobalid",
            id_value=apex_guid,
            fields="*",
            return_geometry=False
        )
        geography_raw["senate"] = select_record(
            url=base_url,
            layer=senate_layer,
            id_field="parentglobalid",
            id_value=apex_guid,
            fields="*",
            return_geometry=False
        )
        geography_raw["house"] = select_record(
            url=base_url,
            layer=house_layer,
            id_field="parentglobalid",
            id_value=apex_guid,
            fields="*",
            return_geometry=False
        )

    # Store raw + normalized feature lists for downstream payload/deletes
    st.session_state["geography_raw_records"] = geography_raw
    st.session_state["geography_records"] = {k: _normalize_features(v) for k, v in geography_raw.items()}
    st.session_state["region_records"] = st.session_state["geography_records"]["region"]
    st.session_state["borough_records"] = st.session_state["geography_records"]["borough"]
    st.session_state["senate_records"] = st.session_state["geography_records"]["senate"]
    st.session_state["house_records"] = st.session_state["geography_records"]["house"]

    # ------------------------------------------------------------------
    # Pull Location Records (stored locations layer) by Project GUID
    # - Filter field is parentglobalid (matches footprint/geography lookup behavior)
    # ------------------------------------------------------------------
    locations_rec = None
    locations_layer = st.session_state.get('locations_layer')
    if apex_guid and locations_layer is not None:
        locations_rec = select_record(
            url=base_url,
            layer=locations_layer,
            id_field='parentglobalid',
            id_value=apex_guid,
            fields='*',
            return_geometry=False
        )

    # Store raw + normalized feature list for downstream payload/deletes
    st.session_state['locations_raw_record'] = locations_rec
    st.session_state['locations_records'] = _normalize_features(locations_rec)
    # ------------------------------------------------------------------
    # Package footprint coordinates into a single item (by project type)
    # - Site      -> points   -> [x, y]
    # - Route     -> lines    -> flattened list of [x, y] vertices
    # - Boundary  -> polygons -> flattened list of [x, y] vertices
    # ------------------------------------------------------------------
    geom_type_map = {
        "Site": "point",
        "Route": "line",
        "Boundary": "polygon",
    }
    packed_geom_type = geom_type_map.get(proj_type)

    def _extract_geometries(geom: Dict[str, Any]):
        """Return geometry coordinate sets from an Esri geometry object.

        All geometry is normalized to a *list* of distinct geometries so downstream
        code can treat it consistently:

        - point/multipoint -> [[[x, y], ...]]      (ONE geometry: list-of-points)
        - polyline         -> [[[x, y], ...], ...] (one geometry per path)
        - polygon          -> [[[x, y], ...], ...] (one geometry per ring)

        Key rule for Sites:
        * A single point OR a list-of-one-point is converted to [[x, y]]
            so geometry_to_folium(feature_type="point") works with the existing
            `for geom_coords in geoms:` loop.

        Notes:
        * ArcGIS may return point geometry as {x,y} OR multipoint as {points:[...]}
        * Sometimes geometry is serialized JSON; we handle that too.
        """
        out: List[Any] = []

        # ArcGIS can sometimes hand us geometry as a JSON string
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except Exception:
                return out

        # Defensive: if geom is already a coordinate container (non-dict)
        # - [x, y]
        # - [[x, y]]
        # - [[x, y], [x, y], ...]
        if not isinstance(geom, dict):
            if isinstance(geom, (list, tuple)) and len(geom) > 0:
                # case: [x, y]
                if len(geom) >= 2 and all(isinstance(v, (int, float)) for v in geom[:2]):
                    x, y = geom[0], geom[1]
                    out.append([[x, y]])  # <-- convert to list-of-points
                    return out

                # case: [[x, y], ...]
                if all(isinstance(pt, (list, tuple)) and len(pt) >= 2 for pt in geom):
                    pts: List[List[float]] = []
                    for pt in geom:
                        x, y = pt[0], pt[1]
                        if x is not None and y is not None:
                            pts.append([x, y])
                    if pts:
                        out.append(pts)  # <-- ONE geometry: list-of-points
                    return out

            return out

        # Point: {x, y} -> [[[x, y]]]
        if "x" in geom and "y" in geom:
            x = geom.get("x")
            y = geom.get("y")
            if x is not None and y is not None:
                out.append([[x, y]])  # <-- ONE geometry: list-of-points
            return out

        # Multipoint: {points:[[x,y],...]} -> [[[x,y],[x,y],...]]
        pts = geom.get("points")
        if isinstance(pts, list):
            gathered: List[List[float]] = []
            for pt in pts:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    x, y = pt[0], pt[1]
                    if x is not None and y is not None:
                        gathered.append([x, y])

            # If list-of-one-point, this becomes [[x,y]] as required.
            if gathered:
                out.append(gathered)  # <-- ONE geometry: list-of-points
            return out

        # Polyline: {paths:[[[x,y],...], ...]} -> one geometry per path
        paths = geom.get("paths")
        if isinstance(paths, list):
            for path in paths:
                if not isinstance(path, list):
                    continue
                coords: List[List[float]] = []
                for pt in path:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        coords.append([pt[0], pt[1]])
                if coords:
                    out.append(coords)
            return out

        # Polygon: {rings:[[[x,y],...], ...]} -> one geometry per ring
        rings = geom.get("rings")
        if isinstance(rings, list):
            for ring in rings:
                if not isinstance(ring, list):
                    continue
                coords: List[List[float]] = []
                for pt in ring:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        coords.append([pt[0], pt[1]])
                if coords:
                    out.append(coords)
            return out

        return out

    geometries = []
    if footprint_rec is not None:
        # select_record may return:
        #   - a list of feature dicts
        #   - a single feature dict
        #   - a dict with a 'features' list
        if isinstance(footprint_rec, dict) and isinstance(footprint_rec.get('features'), list):
            features = footprint_rec.get('features') or []
        else:
            features = footprint_rec if isinstance(footprint_rec, list) else [footprint_rec]

        for feat in features:
            geom = (feat or {}).get('geometry')
            if geom is not None:
                geometries.extend(_extract_geometries(geom))

    footprint_item = {
        'type': proj_type,
        'geometry_type': packed_geom_type,
        'geometries': geometries,
    }

    # Store packaged footprint so the map section can read it on this rerun
    st.session_state['footprint_item'] = footprint_item
    st.write('')


    footprint_container = st.container(border=False)
    with footprint_container:
        # When UPDATE FOOTPRINT is selected, replace the container content with the placeholder message
        if st.session_state.get("update_footprint_mode", False):
            with st.container(border = False):
                load_geometry_app()
                st.write('')
        else:
        
            st.markdown("###### CONSTRUCTION FOOTPRINT")
            with st.container(border = True):
                # Prefer the freshly-built item; fall back to session_state if needed
                item = footprint_item or (st.session_state.get("footprint_item") or {})
                geom_kind = item.get("geometry_type")
                geoms = item.get("geometries", [])

                if geoms:
                    m = folium.Map(
                        location=[63.833333, -152.0],  # Alaska center (fixed anchor)
                        zoom_start=4,
                        control_scale=True,
                    )

                    for geom_coords in geoms:
                        layer = geometry_to_folium(
                            geom_coords,
                            feature_type={
                                "point": "point",
                                "line": "polyline",
                                "polygon": "polygon",
                            }.get(geom_kind),
                            color="#00bcd4",
                            weight=6,
                            opacity=0.85,
                            fill=(geom_kind == "polygon"),
                            fill_color="#00bcd4",
                            fill_opacity=0.25,
                            point_shape="circle",
                            point_radius=8,
                            point_color="#00bcd4",
                            point_weight=3,
                            point_fill_color="#00bcd4",
                            point_fill_opacity=0.85,
                        )
                        layer.add_to(m)

                    # Fit bounds based on geometry type
                    def _fallback_bounds_from_geoms(_geom_kind, _geoms):
                        pts = []
                        for g in _geoms or []:
                            if _geom_kind == 'point':
                                if isinstance(g, (list, tuple)) and len(g) >= 2:
                                    x, y = g[0], g[1]
                                    if x is not None and y is not None:
                                        pts.append((y, x))  # (lat, lon)
                            else:
                                if isinstance(g, list):
                                    for pt in g:
                                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                            x, y = pt[0], pt[1]
                                            if x is not None and y is not None:
                                                pts.append((y, x))  # (lat, lon)
                        if not pts:
                            return None
                        lats = [p[0] for p in pts]
                        lons = [p[1] for p in pts]
                        return [[min(lats), min(lons)], [max(lats), max(lons)]]

                    bounds = None
                    try:
                        if geom_kind == 'point':
                            bounds = set_bounds_point(geoms)
                        elif geom_kind == 'line':
                            bounds = set_bounds_route(geoms)
                        elif geom_kind == 'polygon':
                            bounds = set_bounds_boundary(geoms)
                    except TypeError:
                        # Some implementations may expect the map instance as the first argument
                        try:
                            if geom_kind == 'point':
                                bounds = set_bounds_point(m, geoms)
                            elif geom_kind == 'line':
                                bounds = set_bounds_route(m, geoms)
                            elif geom_kind == 'polygon':
                                bounds = set_bounds_boundary(m, geoms)
                        except Exception:
                            bounds = None

                    if not bounds:
                        bounds = _fallback_bounds_from_geoms(geom_kind, geoms)

                    if bounds:
                        try:
                            m.fit_bounds(bounds)
                        except Exception:
                            pass

                    st_folium(
                        m,
                        height=420,
                        width=None,
                        returned_objects=[],  # prevent reruns on pan/zoom
                        key='footprint_map',
                    )

                else:
                    st.caption("No footprint geometry is available for this project.")


            st.write('')
                
            st.markdown("###### LEGISLATIVE AND ADMINISTRATIVE BOUNDARIES")
            with st.container(border = True):
                
                house_val =  st.session_state['List_House_District']
                senate_val =  st.session_state['List_Senate_District']
                borough_val =  st.session_state['List_Borough_Census_Area']
                region_val =  st.session_state['List_DOT_PF_Region']

                col1, col2 = st.columns(2)
                col1.markdown(f"**House Districts:** {house_val or '—'}")
                col2.markdown(f"**Senate Districts:** {senate_val or '—'}")
                col1.markdown(f"**Boroughs:** {borough_val or '—'}")
                col2.markdown(f"**Regions:** {region_val or '—'}")


    def _reset_load_geometry_state():
        # Reset load_geometry session state so the UI behaves like a fresh loader run
        st.session_state["footprint_submitted"] = False
        st.session_state["just_submitted_geometry"] = False

        # Clear previously-submitted geometry
        st.session_state["project_geometry"] = None
        st.session_state["project_geom_type"] = None
        st.session_state["project_geom"] = None

        # Clear selections / widget-tracking state (used by load_geometry_app)
        st.session_state["selected_point"] = None
        st.session_state["selected_route"] = None
        st.session_state["selected_boundary"] = None
        st.session_state["option"] = None
        st.session_state["prev_geometry_option"] = None
        st.session_state["prev_geometry_project_type"] = None
        st.session_state["submitted_geom_sig"] = None
        st.session_state["submitted_option"] = None
        st.session_state["submitted_project_type"] = None

        # Bump the version so any widget keys inside load_geometry_app are forced to rebuild
        st.session_state["geometry_form_version"] = int(st.session_state.get("geometry_form_version", 0)) + 1

        def _clear_footprint_and_load_geometry_state():
            """Clear session_state keys created by footprint.py and by load_geometry step."""
            keys_to_clear = {
                # --- footprint.py-created keys ---
                "update_footprint_mode",
                "is_awp",
                "awp_id",
                "awp_geometry_points",
                "footprint_item",
                "deploy_objectids",
                "last_footprint_deploy_result",
                "locations_raw_record",
                "locations_records",
                "geography_raw_records",
                "geography_records",
                "house_records",
                "senate_records",
                "region_records",
                "borough_records",
                "List_House_District",
                "List_Senate_District",
                "List_DOT_PF_Region",
                "List_Borough_Census_Area",

                # --- load_geometry-created keys (from load_geometry step) ---
                "footprint_submitted",
                "just_submitted_geometry",
                "project_geometry",
                "project_geom_type",
                "project_geom",
                "selected_point",
                "selected_route",
                "selected_boundary",
                "option",
                "prev_geometry_option",
                "prev_geometry_project_type",
                "submitted_geom_sig",
                "submitted_option",
                "submitted_project_type",
                "geometry_form_version",
                "project_type",
                "geom_type",
                "house_string",
                "senate_string",
                "region_string",
                "borough_string",
            }

            for k in keys_to_clear:
                st.session_state.pop(k, None)


    def _reset_to_fresh_run_after_deploy():
        """Clear state and rerun the script from the top (fresh first run)."""
        _clear_footprint_and_load_geometry_state()
        st.rerun()


    def _enter_update_footprint_mode():
        st.session_state["update_footprint_mode"] = True
        _reset_load_geometry_state()

    def _deploy_footprint_update(
        progress_placeholder: st.delta_generator.DeltaGenerator,
        project_rec: Dict[str, Any],
        footprint_rec_any: Any,
        locations_rec_any: Any,
    ) -> None:
        """Build staged payloads and run the staged deploy helper.

        For now: stages + payload creation only (no AGOL writes).

        Active (staged) payloads:
          - Project payload
          - Old footprint deletes payload
          - Locations deletes payload
          - Geography deletes payloads (house/senate/borough/region)

        Also captures and persists OBJECTIDs for project + footprint + locations + geography.
        """

        apex_guid = st.session_state.get("apex_guid")

        old_proj_type = (project_rec or {}).get("Proj_Type")
        new_proj_type = _resolve_new_project_type() or old_proj_type

        old_footprint_layer = _project_type_to_footprint_layer(old_proj_type)
        new_footprint_layer = _project_type_to_footprint_layer(new_proj_type)

        # ---------------------------------------------------------------------
        # OBJECTID CAPTURE (ACTIVE)
        # ---------------------------------------------------------------------
        project_objectid = _get_objectid_from_attributes(project_rec or {})

        footprint_features = _normalize_features(footprint_rec_any)
        footprint_objectids = _collect_objectids_from_features(footprint_features)

        locations_features = _normalize_features(locations_rec_any)
        locations_objectids = _collect_objectids_from_features(locations_features)

        geo_records = st.session_state.get("geography_records") or {}
        if not isinstance(geo_records, dict) or not geo_records:
            geo_records = {
                "house": st.session_state.get("house_records"),
                "senate": st.session_state.get("senate_records"),
                "region": st.session_state.get("region_records"),
                "borough": st.session_state.get("borough_records"),
            }

        geography_objectids: Dict[str, List[int]] = {}
        for layer in ("house", "senate", "borough", "region"):
            feats = _normalize_features(geo_records.get(layer))
            geography_objectids[layer] = _collect_objectids_from_features(feats)

        geography_objectids_all = (
            geography_objectids.get("house", [])
            + geography_objectids.get("senate", [])
            + geography_objectids.get("borough", [])
            + geography_objectids.get("region", [])
        )

        st.session_state["deploy_objectids"] = {
            "project": project_objectid,
            "footprint": footprint_objectids,
            "locations": locations_objectids,
            "geography": geography_objectids,
            "geography_all": geography_objectids_all,
        }

        # ---------------------------------------------------------------------
        # 1) Project payload (ACTIVE)
        # ---------------------------------------------------------------------
        # ---------------------------------------------------------------------
        # Payloads (ACTIVE)
        # ---------------------------------------------------------------------
        project_payload = manage_footprint_project_payload(project_objectid)

        # Resolve NEW project type from the project payload (preferred)
        proj_type_from_payload = None
        try:
            upd0 = (project_payload.get("updates") or [])[0] if isinstance(project_payload, dict) else {}
            attrs0 = (upd0 or {}).get("attributes") or {}
            proj_type_from_payload = (
                attrs0.get("proj_type")
                or attrs0.get("Proj_Type")
                or attrs0.get("PROJ_TYPE")
                or attrs0.get("ProjType")
            )
        except Exception:
            proj_type_from_payload = None

        if proj_type_from_payload:
            new_proj_type = proj_type_from_payload

        # Re-resolve new footprint layer based on NEW proj_type
        new_footprint_layer = _project_type_to_footprint_layer(new_proj_type)

        # Deletes payloads
        old_footprint_delete_payload = manage_footprint_deletes_payload(footprint_objectids)
        locations_delete_payload = manage_footprint_deletes_payload(locations_objectids)

        geography_delete_payloads: Dict[str, Dict[str, Any]] = {}
        for layer in ("house", "senate", "borough", "region"):
            geography_delete_payloads[layer] = manage_footprint_deletes_payload(
                geography_objectids.get(layer, [])
            )

        
        # Ensure payload-builder session-state keys exist in manager context
        _seed_payload_builder_state_from_project(project_rec)

        # Adds payloads
        new_location_payload = location_payload()
        new_footprint_payload = geometry_payload()

        geography_add_payloads: Dict[str, Dict[str, Any]] = {}
        for layer in ("house", "senate", "borough", "region"):
            geography_add_payloads[layer] = geography_payload(layer)

        # ---------------------------------------------------------------------
        # Deploy (ACTIVE)
        # ---------------------------------------------------------------------
        deploy_result = deploy_to_agol_footprint_update(
            project_payload=project_payload,
            old_footprint_layer=old_footprint_layer,
            old_footprint_delete_payload=old_footprint_delete_payload,
            locations_delete_payload=locations_delete_payload,
            new_footprint_layer=new_footprint_layer,
            new_footprint_add_payload=new_footprint_payload,
            new_locations_add_payload=new_location_payload,
            geo_delete_payloads=geography_delete_payloads,
            geo_add_payloads=geography_add_payloads,
            progress_placeholder=progress_placeholder,
        )

        # Persist last result for review/debug (no payloads printed inline)
        st.session_state["last_footprint_deploy_result"] = {
            **(deploy_result or {}),
            "objectids": st.session_state.get("deploy_objectids"),
            "old_proj_type": old_proj_type,
            "new_proj_type": new_proj_type,
            "old_footprint_layer": old_footprint_layer,
            "new_footprint_layer": new_footprint_layer,
            "apex_guid": apex_guid,
        }

        if deploy_result and deploy_result.get("success") is True:
            _reset_to_fresh_run_after_deploy()
            return

        st.error((deploy_result or {}).get("message", "Deployment failed."))

        with st.expander("Deployment results", expanded=False):
            st.json(st.session_state["last_footprint_deploy_result"])

    

    # ---------------------------------------------------------------------
    # UPDATE BUTTON
    # ---------------------------------------------------------------------
    in_update_mode = bool(st.session_state.get("update_footprint_mode", False))

    has_loaded_geometry = st.session_state.get("project_geometry") is not None

    submitted_ok = (
        bool(st.session_state.get("footprint_submitted")) or
        bool(st.session_state.get("just_submitted_geometry")) or
        bool(st.session_state.get("submitted_geom_sig"))
    )

    can_update = bool(has_loaded_geometry and submitted_ok)

    if not in_update_mode:
        st.button(
            "UPDATE FOOTPRINT",
            key="enter_update_footprint_btn",
            type="primary",
            use_container_width=True,
            on_click=_enter_update_footprint_mode,
        )
    else:
        clicked = st.button(
            "UPDATE FOOTPRINT",
            key="deploy_update_footprint_btn",
            type="primary",
            use_container_width=True,
            disabled=not can_update,
        )

        # ✅ progress bar placeholder is now BELOW the update button
        progress_placeholder = st.empty()

        if clicked and can_update:
            _deploy_footprint_update(progress_placeholder, rec or {}, footprint_rec, locations_rec)

        st.button(
            "CANCEL",
            key="cancel_update_footprint_btn",
            use_container_width=True,
            on_click=lambda: st.session_state.__setitem__("update_footprint_mode", False),
        )
