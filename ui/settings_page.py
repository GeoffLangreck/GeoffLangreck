"""Settings & Debug page for the Shop Scheduler."""

import json
import streamlit as st
from typing import Callable, Optional

from shop_scheduler.adapters.storage import OverlayStorage


def show_settings_page(
    storage: OverlayStorage,
    on_clear_data: Optional[Callable] = None
) -> None:
    """Show the Settings & Debug page."""
    st.header("Settings & Debug")

    # Storage stats
    st.subheader("Storage Statistics")
    stats = storage.get_storage_stats()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Job Priorities", stats["priorities_count"])
    with col2:
        st.metric("Shortages", stats["shortages_count"])
    with col3:
        st.metric("Employees", stats["employees_count"])
    with col4:
        st.metric("Absences", stats["absences_count"])

    st.caption(f"Storage Directory: {stats['storage_directory']}")

    # Data viewer
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Priorities", "Shortages", "Employees", "Absences"]
    )

    with tab1:
        _show_priorities(storage)

    with tab2:
        _show_shortages(storage)

    with tab3:
        _show_employees(storage)

    with tab4:
        _show_absences(storage)

    # Data management
    st.markdown("---")
    st.subheader("Data Management")

    col_a, col_b = st.columns(2)

    with col_a:
        # FIX: st.confirm() does not exist in Streamlit.
        # Use a checkbox as a confirmation gate instead.
        confirm_clear = st.checkbox(
            "I understand this will delete all job priorities, shortages, employees, and absences.",
            key="confirm_clear_all"
        )
        if st.button("Clear All Overlays", type="secondary", disabled=not confirm_clear):
            storage.clear_all_data()
            st.success("All overlays cleared!")
            if on_clear_data:
                on_clear_data()
            st.rerun()

    with col_b:
        st.info("All data is stored locally in JSON files in the 'shop_data' directory.")

    # Debug section
    st.markdown("---")
    with st.expander("Debug Information"):
        st.markdown("### Debug Data")

        debug_info = {
            "storage_stats": stats,
        }

        st.json(debug_info)


def _show_priorities(storage: OverlayStorage) -> None:
    """Show job priorities."""
    priorities = storage.get_all_priorities()

    if priorities:
        st.markdown(f"**Total Priorities:** {len(priorities)}")
        priority_data = [{"Job #": k, "Priority": v} for k, v in priorities.items()]
        st.table(priority_data)
    else:
        st.info("No job priorities set.")


def _show_shortages(storage: OverlayStorage) -> None:
    """Show shortages."""
    shortages = storage.get_shortages()

    if shortages:
        st.markdown(f"**Total Shortages:** {len(shortages)}")

        shortage_data = []
        for s in shortages:
            shortage_data.append({
                "ID": s.id,
                "Job": s.job_number,
                "Description": s.description,
                "Part": s.part or "-",
                "Qty": s.quantity or "-",
                "Status": s.status.value,
                "Date": s.date_added,
            })

        st.table(shortage_data)
    else:
        st.info("No shortages recorded.")


def _show_employees(storage: OverlayStorage) -> None:
    """Show employees."""
    employees = storage.get_employees()

    if employees:
        st.markdown(f"**Total Employees:** {len(employees)}")

        emp_data = []
        for e in employees:
            emp_data.append({
                "ID": e.id,
                "Name": e.name,
                "Daily Hours": e.default_daily_hours,
                "Work Centers": ", ".join(e.work_centers) if e.work_centers else "All",
            })

        st.table(emp_data)
    else:
        st.info("No employees added.")


def _show_absences(storage: OverlayStorage) -> None:
    """Show absences."""
    absences = storage.get_absences()

    if absences:
        st.markdown(f"**Total Absence Records:** {len(absences)}")

        absence_data = []
        for a in absences:
            emp = storage.get_employee(a.employee_id)
            emp_name = emp.name if emp else "Unknown"

            absence_data.append({
                "Employee": emp_name,
                "Date": a.date,
                "Hours Lost": a.hours_lost,
                "Reason": a.reason or "-",
            })

        st.table(absence_data)
    else:
        st.info("No absence records.")
