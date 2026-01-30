"""Schedule page for the Shop Scheduler."""

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from shop_scheduler.models import Job, Employee, EmployeeAbsence, ScheduleResult
from shop_scheduler.adapters.storage import OverlayStorage
from shop_scheduler.scheduling import Scheduler, CapacityCalculator


def show_schedule_page(
    jobs: list[Job],
    storage: OverlayStorage,
    scheduler: Scheduler = None
) -> None:
    """Show the Schedule page."""
    st.header("Schedule")

    if not jobs:
        st.warning("No jobs loaded. Please import a CSV file first.")
        return

    # Initialize scheduler if not provided
    if scheduler is None:
        employees = storage.get_employees()
        absences = storage.get_absences()
        capacity_calc = CapacityCalculator(employees, absences)
        scheduler = Scheduler(capacity_calculator=capacity_calc)

    # Get blocked jobs
    blocked_jobs = storage.get_open_shortage_job_numbers()

    # Scheduling controls
    st.subheader("Scheduling Parameters")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        start_date = st.date_input(
            "Schedule Start",
            value=date.today(),
            help="First day to schedule from"
        )
    with col2:
        horizon = st.slider(
            "Schedule Horizon (days)",
            min_value=7,
            max_value=180,
            value=60,
            help="How far ahead to schedule"
        )
    with col3:
        default_cap = st.number_input(
            "Default Daily Capacity (hrs)",
            min_value=1.0,
            max_value=24.0,
            value=8.0,
            step=1.0
        )
    with col4:
        include_blocked = st.checkbox(
            "Include Blocked Jobs",
            value=False,
            help="Schedule blocked jobs (they'll be marked as blocked)"
        )

    # Run scheduling
    if st.button("Run Scheduler"):
        blocked_to_use = set() if not include_blocked else blocked_jobs
        result = scheduler.schedule(
            jobs=jobs,
            blocked_job_numbers=blocked_to_use,
            start_date=start_date,
            schedule_horizon_days=horizon
        )
        # Save result
        storage.save_schedule_result(result.to_dict())
        st.success("Scheduling complete!")
        st.rerun()

    # Display results from the current scheduler run or show summary from saved data
    if scheduler.schedule_result:
        _display_schedule_results(scheduler.schedule_result, jobs, blocked_jobs, start_date)
    else:
        # FIX: Don't try to reconstruct ScheduleResult from a saved dict with
        # ScheduleResult(**saved_result) — the dict contains serialized strings/
        # dicts, not actual ScheduledOperation/Operation objects.
        # Instead, just show a summary from the saved dict.
        saved_result = storage.load_schedule_result()
        if saved_result:
            _display_saved_schedule_summary(saved_result)
            st.info("Run the scheduler again to see the full interactive schedule view.")


def _display_saved_schedule_summary(saved: dict) -> None:
    """Display a summary from a previously saved schedule result dict."""
    st.subheader("Last Saved Schedule Summary")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Jobs On Time", saved.get("jobs_on_time", 0))
    with col2:
        st.metric("Jobs Late", saved.get("jobs_late", 0))
    with col3:
        blocked = saved.get("blocked_jobs", [])
        st.metric("Blocked Jobs", len(blocked))

    notes = saved.get("notes", [])
    if notes:
        with st.expander("Schedule Notes"):
            for note in notes:
                st.write(f"- {note}")

    saved_at = saved.get("saved_at", "Unknown")
    st.caption(f"Schedule saved at: {saved_at}")


def _display_schedule_results(
    result: ScheduleResult,
    jobs: list[Job],
    blocked_jobs: set[str],
    start_date: date
) -> None:
    """Display scheduling results."""
    # Summary metrics
    st.subheader("Schedule Summary")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Jobs On Time", result.jobs_on_time)
    with col2:
        st.metric("Jobs Late", result.jobs_late, delta_color="inverse")
    with col3:
        st.metric("Blocked Jobs", len(result.blocked_jobs), delta_color="inverse")
    with col4:
        unsched = len(result.unscheduled_operations)
        st.metric("Unscheduled Ops", unsched, delta_color="inverse" if unsched > 0 else "off")

    # Notes
    if result.notes:
        with st.expander("Schedule Notes"):
            for note in result.notes:
                st.write(f"- {note}")

    # View options
    view_option = st.radio(
        "View By:",
        options=["Work Center", "Job", "Timeline"]
    )

    if view_option == "Work Center":
        _display_by_work_center(result, jobs, blocked_jobs)
    elif view_option == "Job":
        _display_by_job(result, jobs, blocked_jobs)
    elif view_option == "Timeline":
        _display_timeline(result, jobs, blocked_jobs, start_date)


def _display_by_work_center(
    result: ScheduleResult,
    jobs: list[Job],
    blocked_jobs: set[str]
) -> None:
    """Display schedule grouped by work center."""
    wc_ops: dict[str, list] = {}
    for so in result.scheduled_operations:
        wc = so.operation.work_center_code
        if wc not in wc_ops:
            wc_ops[wc] = []
        wc_ops[wc].append(so)

    wc_hours = {wc: sum(so.operation.production_hours for so in ops)
                for wc, ops in wc_ops.items()}
    bottlenecks = sorted(wc_hours.items(), key=lambda x: x[1], reverse=True)[:3]

    if bottlenecks:
        st.subheader("Potential Bottlenecks")
        for wc, hours in bottlenecks:
            st.markdown(f"- **{wc}**: {hours:.1f} total scheduled hours")

    for wc in sorted(wc_ops.keys()):
        with st.expander(f"{wc} ({len(wc_ops[wc])} operations)"):
            ops_data = []
            for so in wc_ops[wc]:
                is_late = so.scheduled_date > so.job.due_date
                status = "LATE" if is_late else "On Time"
                blocked = "BLOCKED" if so.job.job_number in blocked_jobs else ""

                ops_data.append({
                    "Date": so.scheduled_date,
                    "Job": so.job.job_number,
                    "Part": so.job.part_number[:15],
                    "Hours": so.operation.production_hours,
                    "Status": status,
                    "Blocked": blocked,
                })

            if ops_data:
                df = pd.DataFrame(ops_data)
                df = df.sort_values("Date")
                st.table(df)


def _display_by_job(
    result: ScheduleResult,
    jobs: list[Job],
    blocked_jobs: set[str]
) -> None:
    """Display schedule grouped by job."""
    job_ops: dict[str, list] = {}
    for so in result.scheduled_operations:
        jn = so.job.job_number
        if jn not in job_ops:
            job_ops[jn] = []
        job_ops[jn].append(so)

    for jn in sorted(job_ops.keys(), key=lambda x: (
        min(so.scheduled_date for so in job_ops[x])
        if job_ops[x] else date.max
    )):
        job = next((j for j in jobs if j.job_number == jn), None)
        if not job:
            continue

        ops = job_ops[jn]
        completion_date = max(so.scheduled_date for so in ops)
        is_late = completion_date > job.due_date
        is_blocked = jn in blocked_jobs

        if is_blocked:
            status = "BLOCKED"
        elif is_late:
            days_late = (completion_date - job.due_date).days
            status = f"LATE ({days_late} days)"
        else:
            days_before = (job.due_date - completion_date).days
            status = f"On Time ({days_before} days early)"

        with st.expander(f"{jn}: {status}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**Part:** {job.part_number}")
            with col2:
                st.markdown(f"**Qty:** {job.quantity}")
            with col3:
                st.markdown(f"**Due:** {job.due_date}")

            st.markdown("**Operations:**")
            ops_data = []
            for so in sorted(ops, key=lambda x: x.operation.operation_number):
                ops_data.append({
                    "Op": so.operation.operation_number,
                    "WC": so.operation.work_center_code,
                    "Date": so.scheduled_date,
                    "Hours": so.operation.production_hours,
                })

            if ops_data:
                df = pd.DataFrame(ops_data)
                st.table(df)


def _display_timeline(
    result: ScheduleResult,
    jobs: list[Job],
    blocked_jobs: set[str],
    start_date: date
) -> None:
    """Display schedule as a timeline by day."""
    date_ops: dict[date, list] = {}
    for so in result.scheduled_operations:
        if so.scheduled_date not in date_ops:
            date_ops[so.scheduled_date] = []
        date_ops[so.scheduled_date].append(so)

    show_days = 14
    dates_to_show = sorted(d for d in date_ops.keys() if d >= start_date)[:show_days]

    if not dates_to_show:
        st.info("No scheduled operations in the visible date range.")
        return

    for d in dates_to_show:
        ops = date_ops[d]
        day_name = d.strftime("%a")
        total_hours = sum(so.operation.production_hours for so in ops)

        st.markdown(f"### {d} ({day_name}) - {total_hours:.1f} hours")

        for so in sorted(ops, key=lambda x: x.operation.work_center_code):
            is_late = so.scheduled_date > so.job.due_date
            is_blocked = so.job.job_number in blocked_jobs

            if is_late:
                marker = "[LATE]"
            elif is_blocked:
                marker = "[BLOCKED]"
            else:
                marker = ""

            wc = so.operation.work_center_code

            st.markdown(
                f"**{so.job.job_number}** @ {wc}: "
                f"{so.operation.production_hours:.1f}h - {so.job.part_number} {marker}"
            )
