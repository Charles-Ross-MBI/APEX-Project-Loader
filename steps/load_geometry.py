
"""
===============================================================================
GEOMETRY LOAD / SELECTION (STREAMLIT) — PROJECT TYPE + UPLOAD METHOD ROUTER
===============================================================================

Purpose:
    Provides the Streamlit UI that guides users through selecting a project
    geometry for upload (site/route/boundary) using multiple input methods:
      - Shapefile upload (ZIP)
      - Manual entry (lat/lon or milepoints)
      - Draw on map
      - AASHTOWare point (when available for site projects)

    After a geometry is selected/updated, this module triggers district/geography
    intersect queries and displays the resulting House/Senate/Borough/Region
    values (and routes when applicable).

Key behaviors:
    - Project type selection:
        * Site Project / Route Project / Boundary Project
        * Changing project type clears geometry + geography outputs to prevent
          stale results and mismatched state.
    - Upload method routing:
        * Presents different upload method choices based on project type.
        * Switching upload method clears existing geometry selections to avoid
          cross-method bleed (e.g., previously drawn route vs uploaded shapefile).
        * Optionally exposes an "AASHTOWare" method for Site projects when an
          AASHTOWare project is selected and lat/lon fields exist.
    - Geography/district queries:
        * Tracks previous geometry values (prev_selected_*) and runs
          run_district_queries() only when geometry changes.
    - Geography display:
        * Shows a “PROJECT GEOGRAPHIES” expander when geometry exists and any
          intersect results are present.

Session-state dependencies (expected at runtime):
    Inputs:
      - 'project_type' (selected via segmented control)
      - Geometry keys:
          'selected_point', 'selected_route', 'selected_boundary'
      - AASHTOWare keys (for optional Site/AWP option):
          'aashto_selected_project', 'awp_dcml_latitude', 'awp_dcml_longitude'
      - Upload method tracking:
          'option', 'geo_option', 'prev_project_type'

    Outputs (written/cleared here or by downstream queries):
      - Geography strings:
          'house_string', 'senate_string', 'borough_string', 'region_string'
      - Route overlay results:
          'route_ids', 'route_names', 'route_list' (set by district_queries)
      - Previous geometry tracking:
          'prev_selected_point', 'prev_selected_route', 'prev_selected_boundary'

Notes:
    - This module is intentionally stateful: it coordinates multiple UI flows
      by manipulating st.session_state and relies on Streamlit reruns.
    - All geometry capture functions are imported from geometry_util and are
      expected to write into the canonical session_state keys.

===============================================================================

Standard Documentation Additions:
    - Helper function docstrings describe: intent, side effects, inputs/outputs.
    - Comments call out state transitions and why clearing occurs.
    - No executable logic has been changed; only documentation/commenting added.
"""

import streamlit as st
from util.geometry_util import (
    point_shapefile,
    polyline_shapefile,
    polygon_shapefile,
    enter_latlng,
    enter_milepoints,
    draw_point,
    draw_line,
    draw_boundary,
    aashtoware_point,
    aashtoware_path
)
from agol.agol_district_queries import run_district_queries


# =============================================================================
# INTERNAL HELPERS (refactor only; preserves behavior)
# =============================================================================
def _segmented_with_safe_default(label: str, options: list[str], state_key: str) -> str:
    """
    Render a segmented control and persist the selection to session state.

    This helper ensures the selection is always valid for the provided options:
    - If the previous session value is present and still valid, it is reused.
    - Otherwise, the first item in `options` becomes the default selection.

    Args:
        label: UI label displayed above the segmented control.
        options: Allowed option strings presented to the user.
        state_key: Session-state key used to store the selected option.

    Returns:
        The selected option string written to st.session_state[state_key].

    Side Effects:
        - Writes to st.session_state[state_key].
    """
    prev = st.session_state.get(state_key)
    if prev not in options:
        prev = options[0]
    st.session_state[state_key] = st.segmented_control(label, options, default=prev)
    return st.session_state[state_key]


def _clear_geography_outputs() -> None:
    """
    Clear computed geography/district output strings.

    These values are displayed in the "PROJECT GEOGRAPHIES" expander and should
    be reset when the project type changes to avoid stale/mismatched results.

    Side Effects:
        - Sets house_string/senate_string/borough_string/region_string to "".
    """
    st.session_state.house_string = ""
    st.session_state.senate_string = ""
    st.session_state.borough_string = ""
    st.session_state.region_string = ""


def _clear_geometry(*, point=False, route=False, boundary=False) -> None:
    """
    Clear selected geometry values in session state.

    Args:
        point: If True, clears st.session_state.selected_point.
        route: If True, clears st.session_state.selected_route.
        boundary: If True, clears st.session_state.selected_boundary.

    Side Effects:
        - Sets selected_* keys to None depending on flags.
    """
    if point:
        st.session_state.selected_point = None
    if route:
        st.session_state.selected_route = None
    if boundary:
        st.session_state.selected_boundary = None


def _handle_project_type_change() -> None:
    """
    Handle a change in project type.

    When a user switches project types (Site/Route/Boundary), previously selected
    geometry and computed geographies can become invalid. This routine clears:
      - Geography output strings
      - Selected geometry values (point/route/boundary)
      - Upload method selection ("option")
    and updates the tracker key 'prev_project_type'.

    Side Effects:
        - Mutates multiple st.session_state keys.
    """
    if st.session_state.get("prev_project_type") != st.session_state.get("project_type"):
        _clear_geography_outputs()
        _clear_geometry(point=True, route=True, boundary=True)
        st.session_state["option"] = None
        st.session_state.prev_project_type = st.session_state.get("project_type")


def _handle_upload_method_change(option: str, *, clear_boundary: bool = False) -> None:
    """
    Handle a change in upload method.

    Different upload methods write to the same canonical geometry keys
    (selected_point/selected_route/selected_boundary). To prevent cross-method
    bleed (e.g., a previously drawn line persisting when switching to shapefile),
    the prior geometry is cleared when the upload method changes.

    Args:
        option: Newly selected upload method string.
        clear_boundary: If True, also clears selected_boundary (used by Boundary projects).

    Side Effects:
        - Clears selected geometry keys (point/route, and possibly boundary).
        - Writes st.session_state.geo_option to the new option.
    """
    if st.session_state.get("geo_option") != option:
        _clear_geometry(point=True, route=True, boundary=clear_boundary)
        st.session_state.geo_option = option


def _ensure_prev_geometry_trackers() -> None:
    """
    Ensure that "previous geometry" trackers exist in session state.

    These keys are used to detect geometry changes between reruns and avoid
    expensive district queries unless necessary.

    Side Effects:
        - Initializes prev_selected_point/route/boundary to None if absent.
    """
    if "prev_selected_point" not in st.session_state:
        st.session_state.prev_selected_point = None
    if "prev_selected_route" not in st.session_state:
        st.session_state.prev_selected_route = None
    if "prev_selected_boundary" not in st.session_state:
        st.session_state.prev_selected_boundary = None


def _run_queries_if_geometry_changed(point_val, route_val, boundary_val) -> None:
    """
    Run district/geography queries only when the selected geometry changes.

    Query calls may be expensive; this function compares current selected geometry
    to "prev_selected_*" values and triggers run_district_queries() only when:
      - the value is not None, AND
      - the value differs from the previous value.

    Args:
        point_val: Current st.session_state.selected_point value.
        route_val: Current st.session_state.selected_route value.
        boundary_val: Current st.session_state.selected_boundary value.

    Side Effects:
        - May call run_district_queries().
        - Updates prev_selected_point/route/boundary when a change is detected.
    """
    _ensure_prev_geometry_trackers()

    point_changed = point_val is not None and point_val != st.session_state.prev_selected_point
    route_changed = route_val is not None and route_val != st.session_state.prev_selected_route
    boundary_changed = boundary_val is not None and boundary_val != st.session_state.prev_selected_boundary

    if point_changed or route_changed or boundary_changed:
        run_district_queries()
        st.session_state.prev_selected_point = point_val
        st.session_state.prev_selected_route = route_val
        st.session_state.prev_selected_boundary = boundary_val


def _render_geographies_expander(*, show_routes: bool = False) -> None:
    """
    Render the "PROJECT GEOGRAPHIES" expander section.

    This is shown only when:
      - a geometry exists for the selected project type, AND
      - at least one geography output string is present.

    Args:
        show_routes: If True, also display route IDs and names (Route/Boundary flows).

    Side Effects:
        - Renders Streamlit UI elements (expander, columns, markdown).
    """
    house_val = st.session_state.get("house_string")
    senate_val = st.session_state.get("senate_string")
    borough_val = st.session_state.get("borough_string")
    region_val = st.session_state.get("region_string")

    with st.expander("PROJECT GEOGRAPHIES", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**House Districts:** {house_val or '—'}")
        col2.markdown(f"**Senate Districts:** {senate_val or '—'}")
        col1.markdown(f"**Boroughs:** {borough_val or '—'}")
        col2.markdown(f"**Regions:** {region_val or '—'}")

        if show_routes:
            route_ids = st.session_state.get("route_ids", None)
            route_names = st.session_state.get("route_names", None)
            st.markdown(f"**Route IDs:** {route_ids}")
            st.markdown(f"**Route Names:** {route_names} ")


# =============================================================================
# ENTRYPOINT: GEOMETRY SELECTION / UPLOAD ROUTER
# =============================================================================
def load_geometry_app():
    """
    Primary Streamlit UI entrypoint for selecting and loading project geometry.

    Responsibilities:
        1) Prompt user to select project type (Site/Route/Boundary).
        2) Present upload method choices based on project type (and AWP availability).
        3) Route user to the selected geometry capture method.
        4) Detect geometry changes and run district queries when needed.
        5) Display resulting geographies (and routes when applicable).

    Session State Contract (high-level):
        Inputs:
            - project_type, option, geo_option, prev_project_type
            - selected_point, selected_route, selected_boundary
            - aashto_selected_project, awp_dcml_latitude, awp_dcml_longitude
        Outputs:
            - house_string, senate_string, borough_string, region_string
            - route_ids, route_names (from district_queries)
            - prev_selected_point, prev_selected_route, prev_selected_boundary
    """
    # -------------------------------------------------------------------------
    # Choose Site / Route / Boundary project type
    # -------------------------------------------------------------------------
    st.markdown("###### Choose Project Type\n", unsafe_allow_html=True)

    # Persist previous project_type choice when possible.
    st.session_state["project_type"] = st.segmented_control(
        "Select Project Type:",
        ["Site Project", "Route Project", "Boundary Project"],
        default=st.session_state.get("project_type", None),  # persist previous choice
    )

    # If project type changed, clear geometry + computed outputs (prevents stale display).
    _handle_project_type_change()

    st.write("")

    # Only render upload options once a project type is selected.
    project_type = st.session_state.get("project_type")
    if not project_type:
        return

    st.markdown("###### Upload Geospatial Data\n", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # Determine whether AASHTOWare upload option should be offered (Site + Route Only)
    # -------------------------------------------------------------------------
    show_awp_point_option = (
        project_type.startswith("Site")
        and st.session_state.get("aashto_selected_project")
        and st.session_state.get("awp_dcml_latitude")
        and st.session_state.get("awp_dcml_longitude")
    )

    show_awp_route_option = (
        project_type.startswith("Route")
        and st.session_state.get("aashto_selected_project")
    )

    # -------------------------------------------------------------------------
    # Project type routing
    # -------------------------------------------------------------------------
    if project_type.startswith("Site"):
        # Site projects use point-based geometry capture.
        options = ["Upload Shapefile", "Enter Latitude/Longitude", "Select Point on Map"]

        if show_awp_point_option:
            # AASHTOWare must be first and preselected when available.
            options = ["AASHTOWare"] + options

            # Force default selection to AASHTOWare whenever it is offered.
            st.session_state["option"] = "AASHTOWare"

        # Choose upload method and clear geometry if method changed.
        option = _segmented_with_safe_default("Choose Upload Method:", options, "option")
        _handle_upload_method_change(option, clear_boundary=False)

        # Route to selected mechanism (each writes canonical geometry keys).
        if option == "AASHTOWare":
            aashtoware_point(
                st.session_state.get("awp_dcml_latitude"),
                st.session_state.get("awp_dcml_longitude"),
            )
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

    elif project_type.startswith("Route"):
        # Route projects use line-based geometry capture.
        options = ["Upload Shapefile", "Enter Milepoints", "Draw Route on Map"]

        if show_awp_route_option:
            # AASHTOWare must be first and preselected when available.
            options = ["AASHTOWare"] + options

            # Force default selection to AASHTOWare whenever it is offered.
            st.session_state["option"] = "AASHTOWare"

        option = _segmented_with_safe_default("Choose Upload Method:", options, "option")
        _handle_upload_method_change(option, clear_boundary=False)

        if option == "AASHTOWare":
            aashtoware_path(
                st.session_state.get('midpoint_PLACEHOLDER'),
                st.session_state.get('endpoint_PLACEHOLDER')
            )
        elif option == "Upload Shapefile":
            polyline_shapefile()
            st.session_state.selected_point = None
        elif option == "Enter Milepoints":
            enter_milepoints()
            st.session_state.selected_point = None
        elif option == "Draw Route on Map":
            draw_line()
            st.session_state.selected_point = None

    elif project_type.startswith("Boundary"):
        # Boundary projects use polygon-based geometry capture.
        options = ["Upload Shapefile", "Draw Boundary on Map"]

        option = _segmented_with_safe_default("Choose Upload Method:", options, "option")
        _handle_upload_method_change(option, clear_boundary=True)

        if option == "Upload Shapefile":
            polygon_shapefile()
            st.session_state.selected_point = None
        elif option == "Draw Boundary on Map":
            draw_boundary()
            st.session_state.selected_point = None

    # -------------------------------------------------------------------------
    # Geometry-change detection + district queries
    # -------------------------------------------------------------------------
    # Read the canonical selected geometry keys (set by geometry_util functions).
    point_val = st.session_state.get("selected_point")
    route_val = st.session_state.get("selected_route")
    boundary_val = st.session_state.get("selected_boundary")

    # Run intersect queries only when the geometry changes (performance optimization).
    _run_queries_if_geometry_changed(point_val, route_val, boundary_val)

    # -------------------------------------------------------------------------
    # Display expander if geometry exists AND any geography result exists
    # -------------------------------------------------------------------------
    house_val = st.session_state.get("house_string")
    senate_val = st.session_state.get("senate_string")
    borough_val = st.session_state.get("borough_string")
    region_val = st.session_state.get("region_string")

    # Expander is only useful if there is at least one populated geography value.
    has_any_geography = any([house_val, senate_val, borough_val, region_val])

    # Only display the expander when the relevant geometry for the project type exists.
    if project_type.startswith("Site") and point_val is not None and has_any_geography:
        _render_geographies_expander(show_routes=False)

    elif project_type.startswith("Route") and route_val is not None and has_any_geography:
        _render_geographies_expander(show_routes=True)

    elif project_type.startswith("Boundary") and boundary_val is not None and has_any_geography:
        _render_geographies_expander(show_routes=True)

    st.write("")
