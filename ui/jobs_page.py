"""Jobs Summary page for the Shop Scheduler."""

import pandas as pd
import streamlit as st

from shop_scheduler.models import Job
from shop_scheduler.adapters.storage import OverlayStorage


def show_jobs_page(
    jobs: list[Job],
    storage: OverlayStorage
) -> None:
    """Show the Jobs Summary page."""
    st.header("Jobs Summary")

    if not jobs:
        st.warning("No jobs loaded. Please import a CSV file first.")
        return

    # Load overlays
    priorities = storage.get_all_priorities()
    blocked_jobs = storage.get_open_shortage_job_numbers()

    # Build dataframe for display
    job_data = []
    for job in jobs:
        manual_prio = priorities.get(job.job_number)
        display_priority = manual_prio if manual_prio is not None else 100

        is_blocked = job.job_number in blocked_jobs
        days_until_due = (job.due_date - pd.Timestamp.today().date()).days
        total_hours = job.total_production_hours

        job_data.append({
            "Job #": job.job_number,
            "Part #": job.part_number,
            "Qty": job.quantity,
            "Due Date": job.due_date,
            "Days Until Due": days_until_due,
            "Priority": display_priority,
            "Total Hours": total_hours,
            "Status": job.status.value,
            "Blocked": is_blocked,
            "Operations": len(job.operations),
        })

    df = pd.DataFrame(job_data)

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_filter = st.multiselect(
            "Status",
            options=["RELEASED", "OPEN", "COMPLETED", "CANCELLED"],
            default=["RELEASED", "OPEN"]
        )
    with col2:
        blocked_filter = st.selectbox(
            "Blocked Status",
            options=["All", "Blocked Only", "Not Blocked"]
        )
    with col3:
        sort_by = st.selectbox(
            "Sort By",
            options=["Due Date", "Priority", "Job Number", "Total Hours"]
        )
    with col4:
        show_late_only = st.checkbox("Show Overdue Only")

    # Apply filters
    filtered_df = df.copy()

    if status_filter:
        filtered_df = filtered_df[filtered_df["Status"].isin(status_filter)]

    if blocked_filter == "Blocked Only":
        filtered_df = filtered_df[filtered_df["Blocked"] == True]
    elif blocked_filter == "Not Blocked":
        filtered_df = filtered_df[filtered_df["Blocked"] == False]

    if show_late_only:
        filtered_df = filtered_df[filtered_df["Days Until Due"] < 0]

    # Sort
    if sort_by == "Due Date":
        filtered_df = filtered_df.sort_values("Due Date")
    elif sort_by == "Priority":
        filtered_df = filtered_df.sort_values("Priority")
    elif sort_by == "Job Number":
        filtered_df = filtered_df.sort_values("Job #")
    elif sort_by == "Total Hours":
        filtered_df = filtered_df.sort_values("Total Hours", ascending=False)

    # Metrics
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Total Jobs", len(filtered_df))
    with col_m2:
        blocked_count = filtered_df["Blocked"].sum()
        st.metric("Blocked Jobs", blocked_count, delta_color="inverse")
    with col_m3:
        overdue_count = (filtered_df["Days Until Due"] < 0).sum()
        st.metric("Overdue Jobs", overdue_count, delta_color="inverse")
    with col_m4:
        avg_hours = filtered_df["Total Hours"].mean()
        st.metric("Avg Hours/Job", f"{avg_hours:.1f}")

    # Priority editor
    with st.expander("Edit Job Priorities"):
        st.markdown("Lower number = higher priority (1 = highest)")
        selected_job = st.selectbox(
            "Select Job",
            options=filtered_df["Job #"].tolist()
        )
        if selected_job:
            current_prio = priorities.get(selected_job, 100)
            new_prio = st.number_input(
                "New Priority",
                min_value=1,
                max_value=200,
                value=current_prio,
                step=5
            )
            if new_prio != current_prio:
                if new_prio == 100:
                    storage.remove_job_priority(selected_job)
                else:
                    storage.set_job_priority(selected_job, new_prio)
                st.success(f"Priority updated for job {selected_job}")
                st.rerun()

    # Job table
    st.subheader(f"Jobs ({len(filtered_df)})")

    display_df = filtered_df.copy()
    display_df["Due Date"] = display_df["Due Date"].apply(lambda x: x.strftime("%Y-%m-%d"))
    display_df["Priority"] = display_df["Priority"].apply(
        lambda x: f"HIGH {x}" if x < 50 else f"MED {x}" if x < 100 else str(x)
    )
    display_df["Blocked"] = display_df["Blocked"].apply(
        lambda x: "BLOCKED" if x else ""
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Late jobs detail
    late_jobs = filtered_df[filtered_df["Days Until Due"] < 0]
    if len(late_jobs) > 0:
        with st.expander(f"Late Jobs ({len(late_jobs)})"):
            for _, row in late_jobs.iterrows():
                st.markdown(f"""
                **{row["Job #"]}** - {row["Part #"]} | Due: {row["Due Date"]} | {row["Days Until Due"]} days late
                """)
