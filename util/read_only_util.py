import streamlit as st
import datetime
import html



# =============================================================================
# READ-ONLY DISPLAY LAYER (CSS)
# =============================================================================
# This CSS supports the "read-only widget" pattern:
# - ro()        : single-line boxed field
# - ro_textarea(): multi-line boxed field
# - ro_widget() : stores to session_state + renders ro/ro_textarea
#
# This keeps AASHTOWare mode visually read-only but still behaves like widgets.
# =============================================================================
_RO_CSS = """
<style>
.ro-field { margin-bottom: 0.75rem; }
.ro-label { font-size: 0.875rem; color: #6b7280; margin-bottom: 0.25rem; }
.ro-box {
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  color: #111827;
  font-size: 0.95rem;
  min-height: 38px;
  display: flex; align-items: center;
  word-break: break-word;
}
.ro-box.mono { font-variant-numeric: tabular-nums; }
.ro-box .placeholder { color: #9ca3af; }
.ro-box-textarea {
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  color: #111827;
  font-size: 0.95rem;
  min-height: 160px;
  white-space: pre-wrap;
  word-break: break-word;
  display: block;
}
.ro-box-textarea .placeholder { color: #9ca3af; }
</style>
"""

    

# =============================================================================
# READ-ONLY FIELD RENDERERS
# =============================================================================
# These helpers render read-only fields using HTML/CSS and are used in AWP mode.
# =============================================================================
def ro(label, value, mono=False):
    
    # Inject read‑only CSS globally (no extra spacing)
    st.html(_RO_CSS)

    # Render a single-line read-only field with label.
    safe_value = value if value not in (None, "") else '<span class="placeholder">—</span>'
    st.markdown(
        f"""
        <div class="ro-field">
          <div class="ro-label">{label}</div>
          <div class="ro-box{' mono' if mono else ''}">{safe_value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ro_cols(specs):
    # Convenience renderer for column-based layouts:
    # specs = [(col, label, value, mono), ...]
    for col, label, value, mono in specs:
        with col:
            ro(label, value, mono)


def ro_textarea(label, value):
    # Render a multi-line read-only field with label.
    safe_value = value if value not in (None, "") else '<span class="placeholder">—</span>'
    st.markdown(
        f"""
        <div class="ro-field">
          <div class="ro-label">{label}</div>
          <div class="ro-box-textarea">{safe_value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ro_widget(key, label, value, mono=False, textarea=False):
    """
    Read-only widget wrapper:
      - Writes value into st.session_state[key] (like a real widget)
      - Renders the value using ro() or ro_textarea()

    This keeps downstream logic consistent regardless of source mode.
    """
    # Persist value exactly like a widget
    st.session_state[key] = value

    # Render using your existing components
    if textarea:
        ro_textarea(label, value)
    else:
        ro(label, value, mono)



        