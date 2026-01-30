"""UI module for the Shop Scheduler application."""

import streamlit as st


def set_page_config():
    """Configure the Streamlit page."""
    st.set_page_config(
        page_title="Shop Scheduler",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def show_header():
    """Show the application header."""
    st.title("Shop Scheduling & Visibility System")
    st.markdown("""
    **Manufacturing job scheduling with due-date awareness and capacity planning.**

    This system imports Made2Manage routing exports and helps schedule jobs
    to maximize on-time completion while respecting work center capacity.
    """)


def show_footer():
    """Show the application footer."""
    st.markdown("---")
    st.markdown(
        "*Shop Scheduler - Built for the manufacturing floor*",
        help="Data is stored locally. No server connection required."
    )
