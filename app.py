import streamlit as st

from shop_scheduler.adapters import CSVAdapter
from shop_scheduler.adapters.storage import OverlayStorage
from shop_scheduler.models import Job
from shop_scheduler.parsing import RoutingTextParser
from shop_scheduler.scheduling import Scheduler, CapacityCalculator

# UI modules
from shop_scheduler.ui import set_page_config, show_header, show_footer
from shop_scheduler.ui.import_page import show_import_page
from shop_scheduler.ui.jobs_page import show_jobs_page
from shop_scheduler.ui.job_detail_page import show_job_detail_page
from shop_scheduler.ui.capacity_page import show_capacity_page
from shop_scheduler.ui.schedule_page import show_schedule_page
from shop_scheduler.ui.settings_page import show_settings_page


def init_session_state():
    """Initialize Streamlit session state."""
    if "storage" not in st.session_state:
        st.session_state["storage"] = OverlayStorage()

    if "csv_adapter" not in st.session_state:
        st.session_state["csv_adapter"] = CSVAdapter()
    if "parser" not in st.session_state:
        st.session_state["parser"] = RoutingTextParser()
    if "scheduler" not in st.session_state:
        st.session_state["scheduler"] = None

    # Load jobs from storage if not already in session state
    if "jobs" not in st.session_state:
        storage = st.session_state["storage"]
        if storage.has_saved_jobs():
            st.session_state["jobs"] = storage.get_jobs()
        else:
            st.session_state["jobs"] = []

    if "work_centers" not in st.session_state:
        st.session_state["work_centers"] = []

    # Initialize work centers from loaded jobs
    jobs = st.session_state.get("jobs", [])
    if jobs and not st.session_state.get("work_centers"):
        work_centers = set()
        for job in jobs:
            for op in job.operations:
                work_centers.add(op.work_center_code)
        st.session_state["work_centers"] = sorted(work_centers)

    # Reinitialize scheduler with capacity calculator
    employees = st.session_state["storage"].get_employees()
    absences = st.session_state["storage"].get_absences()
    capacity_calc = CapacityCalculator(employees, absences)
    st.session_state["scheduler"] = Scheduler(capacity_calculator=capacity_calc)


def on_csv_loaded(jobs):
    """Callback when CSV is successfully loaded."""
    st.session_state["jobs"] = jobs
    # Get work centers from jobs
    work_centers = set()
    for job in jobs:
        for op in job.operations:
            work_centers.add(op.work_center_code)
    st.session_state["work_centers"] = sorted(work_centers)
    # Reinitialize scheduler with capacity calculator
    employees = st.session_state["storage"].get_employees()
    absences = st.session_state["storage"].get_absences()
    capacity_calc = CapacityCalculator(employees, absences)
    st.session_state["scheduler"] = Scheduler(capacity_calculator=capacity_calc)
    # Save jobs to storage for persistence across restarts
    st.session_state["storage"].save_jobs(jobs)


def on_clear_data():
    """Callback when all data is cleared."""
    st.session_state["jobs"] = []
    st.session_state["work_centers"] = []
    st.session_state["scheduler"] = None
    st.session_state["storage"].clear_jobs()


def get_work_centers():
    """Get list of work centers from loaded jobs."""
    if "work_centers" in st.session_state:
        return st.session_state.work_centers
    return []


def main():
    """Main application entry point."""
    set_page_config()
    init_session_state()
    show_header()

    st.sidebar.title("Navigation")

    page = st.sidebar.radio(
        "Go to",
        options=[
            "Import & Preview",
            "Jobs Summary",
            "Job Detail",
            "Capacity & Staffing",
            "Schedule",
            "Settings & Debug",
        ]
    )

    if page == "Import & Preview":
        show_import_page(
            on_csv_loaded=on_csv_loaded,
            csv_adapter=st.session_state["csv_adapter"]
        )

    elif page == "Jobs Summary":
        show_jobs_page(
            jobs=st.session_state["jobs"],
            storage=st.session_state["storage"]
        )

    elif page == "Job Detail":
        show_job_detail_page(
            jobs=st.session_state["jobs"],
            storage=st.session_state["storage"],
            parser=st.session_state["parser"]
        )

    elif page == "Capacity & Staffing":
        show_capacity_page(
            storage=st.session_state["storage"],
            work_centers=get_work_centers()
        )

    elif page == "Schedule":
        show_schedule_page(
            jobs=st.session_state["jobs"],
            storage=st.session_state["storage"],
            scheduler=st.session_state["scheduler"]
        )

    elif page == "Settings & Debug":
        show_settings_page(
            storage=st.session_state["storage"],
            on_clear_data=on_clear_data
        )

    show_footer()


if __name__ == "__main__":
    main()
