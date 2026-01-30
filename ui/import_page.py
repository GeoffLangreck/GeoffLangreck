"""Import & Preview page for the Shop Scheduler."""

import json
import pandas as pd
import streamlit as st
from datetime import date, datetime
from typing import Callable

from shop_scheduler.adapters import CSVAdapter


def show_import_page(
    on_csv_loaded: Callable,
    csv_adapter: CSVAdapter
) -> None:
    """Show the Import & Preview page.

    Args:
        on_csv_loaded: Callback when CSV is successfully loaded
        csv_adapter: The CSV adapter instance
    """
    st.header("Import & Preview")

    # Check if jobs are already loaded
    if st.session_state.get("jobs"):
        st.success(f"{len(st.session_state['jobs'])} jobs loaded")
        if st.button("Load New CSV"):
            st.session_state["jobs"] = []
            st.session_state["work_centers"] = []
            st.rerun()
        return

    # Import method selection
    import_method = st.radio(
        "Choose import method:",
        ["Standard Import (CSV)", "Quick Import (CSV to JSON)"],
        horizontal=True
    )

    if import_method == "Standard Import (CSV)":
        _show_standard_import(on_csv_loaded, csv_adapter)
    else:
        _show_quick_import(on_csv_loaded, csv_adapter)


def _show_standard_import(
    on_csv_loaded: Callable,
    csv_adapter: CSVAdapter
) -> None:
    """Standard CSV import with preview."""
    st.subheader("Standard Import")
    st.caption("Parse CSV and load into session. Good for previewing data.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Upload M2M Routing Export (CSV)",
        type=["csv"],
        help="Upload a Made2Manage routing export CSV file"
    )

    if uploaded_file is not None:
        try:
            # Read CSV
            df = pd.read_csv(uploaded_file)

            # Import using adapter
            result = csv_adapter.import_dataframe(df)

            # Show results
            _show_import_results(result, df)

            if not result.has_errors():
                # FIX: Use result.jobs which is guaranteed to have the parsed
                # jobs (csv_adapter.jobs is also set now, but result.jobs is
                # the canonical source)
                on_csv_loaded(result.jobs)
                st.rerun()

        except Exception as e:
            st.error(f"Failed to import CSV: {str(e)}")
            st.info("Make sure the file is a valid CSV format.")

    else:
        # Show sample data info
        _show_csv_format_info()


def _show_quick_import(
    on_csv_loaded: Callable,
    csv_adapter: CSVAdapter
) -> None:
    """Quick import - convert CSV to JSON directly for faster loading."""
    st.subheader("Quick Import")
    st.caption("Convert CSV to JSON immediately. Faster subsequent loads.")

    # File uploader
    uploaded_file = st.file_uploader(
        "Upload CSV for Quick Import",
        type=["csv"],
        help="CSV will be converted to JSON and saved for fast loading"
    )

    if uploaded_file is not None:
        try:
            # Show progress
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("Reading CSV file...")
            progress_bar.progress(20)

            # Read CSV
            df = pd.read_csv(uploaded_file)

            status_text.text("Parsing job data...")
            progress_bar.progress(40)

            # Import using adapter
            result = csv_adapter.import_dataframe(df)

            if result.has_errors():
                progress_bar.empty()
                status_text.empty()
                st.error("Import failed with errors")
                for e in result.errors:
                    st.error(f"- {e}")
                return

            # FIX: Use result.jobs — the canonical source of parsed jobs
            parsed_jobs = result.jobs

            status_text.text(f"Converting {len(parsed_jobs)} jobs to JSON...")
            progress_bar.progress(60)

            # Save directly to JSON
            storage = st.session_state.get("storage")
            if storage:
                # Convert jobs to dict and save
                jobs_data = [job.to_dict() for job in parsed_jobs]
                storage._save_json(storage.jobs_file, jobs_data)

                # Update session state directly
                st.session_state["jobs"] = parsed_jobs

                # Get work centers
                work_centers = set()
                for job in parsed_jobs:
                    for op in job.operations:
                        work_centers.add(op.work_center_code)
                st.session_state["work_centers"] = sorted(work_centers)

                progress_bar.progress(100)
                status_text.text("Complete!")

                st.success(f"Converted {len(parsed_jobs)} jobs to JSON")
                st.info(f"Saved to: {storage.jobs_file}")

                # FIX: Removed time.sleep(1) — it blocks the Streamlit thread
                # and the progress bar won't render until after the sleep anyway.
                progress_bar.empty()
                status_text.empty()

                st.rerun()
            else:
                # Fallback to callback if storage not available
                on_csv_loaded(parsed_jobs)

        except Exception as e:
            st.error(f"Failed to import CSV: {str(e)}")

    else:
        st.info("Upload a CSV file to convert it to JSON format.")
        st.markdown("""
        **Quick Import Benefits:**
        - Converts CSV to JSON in one step
        - Faster loading on next app start
        - Data persists until explicitly cleared
        """)


def _show_import_results(result, df: pd.DataFrame) -> None:
    """Show import results."""
    # Status
    if result.has_errors():
        st.error("Import completed with errors")
    else:
        st.success("Import successful")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Rows Processed", result.row_count)
    with col2:
        st.metric("Jobs Loaded", result.jobs_loaded)
    with col3:
        st.metric("Warnings", len(result.warnings), delta_color="off")
    with col4:
        st.metric("Errors", len(result.errors), delta_color="inverse" if result.errors else "off")

    # Column mapping info
    st.subheader("Detected Columns")
    col_info = result.column_mapping

    # Show all columns
    all_cols = col_info.headers
    st.write(f"Total columns: {len(all_cols)}")

    # Show mapping status
    mapped = col_info.column_map
    missing = col_info.missing_columns()

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Mapped Columns:**")
        if mapped:
            for internal, actual in mapped.items():
                st.code(f"{internal}: {actual}")
        else:
            st.write("No columns mapped")

    with col_b:
        st.markdown("**Missing Essential:**")
        if missing:
            for m in missing:
                st.warning(f"- {m}")
        else:
            st.success("All essential columns found")

    # Show warnings
    if result.warnings:
        with st.expander(f"Warnings ({len(result.warnings)})"):
            for w in result.warnings:
                st.write(f"- {w}")

    # Show errors
    if result.errors:
        with st.expander(f"Errors ({len(result.errors)})"):
            for e in result.errors:
                st.error(f"- {e}")

    # Preview data
    with st.expander("Data Preview"):
        st.dataframe(df.head(20), use_container_width=True)


def _show_csv_format_info() -> None:
    """Show information about expected CSV format."""
    st.info("""
    **Expected CSV Format (Made2Manage Routing Export)**

    The system uses intelligent column detection with fallbacks. Key columns:

    | Field | Expected Names |
    |-------|----------------|
    | Job Number | fjobno, jobno, job_number |
    | Part Number | fpartno, partno, part_number |
    | Quantity | fquantity, quantity, qty |
    | Due Date | fddue_date, due_date |
    | Operation # | foperno, operno |
    | Work Center | fpro_id, fcpro_name |
    | Prod Time | fuprodtime |
    | Routing Text | fopermemo |
    """)

    st.markdown("---")
    st.subheader("Sample File Location")
    st.code("shop_scheduler/sample_data/RPJROU.csv")

    st.markdown("""
    *Note: The system is designed to handle column variations and additional columns.
    It will fail loudly only if essential data is missing.*
    """)
