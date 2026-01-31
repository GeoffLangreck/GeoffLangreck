"""Job Detail page for the Shop Scheduler."""

import streamlit as st

from shop_scheduler.models import Job, Shortage, ShortageStatus
from shop_scheduler.parsing import RoutingTextParser
from shop_scheduler.adapters.storage import OverlayStorage


def show_job_detail_page(
    jobs: list[Job],
    storage: OverlayStorage,
    parser: RoutingTextParser
) -> None:
    """Show the Job Detail page."""
    st.header("Job Detail")

    if not jobs:
        st.warning("No jobs loaded. Please import a CSV file first.")
        return

    job_numbers = [j.job_number for j in jobs]
    selected_job_no = st.selectbox("Select Job", options=job_numbers)

    if not selected_job_no:
        return

    job = next((j for j in jobs if j.job_number == selected_job_no), None)
    if not job:
        return

    shortages = storage.get_shortages_for_job(selected_job_no)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Job:** {job.job_number}")
    with col2:
        st.markdown(f"**Part:** {job.part_number}")
    with col3:
        st.markdown(f"**Quantity:** {job.quantity}")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown(f"**Due Date:** {job.due_date}")
    with col5:
        st.markdown(f"**Status:** {job.status.value}")
    with col6:
        total_hours = job.total_production_hours
        st.markdown(f"**Total Hours:** {total_hours:.1f}")

    if shortages:
        open_shortages = [s for s in shortages if s.status == ShortageStatus.OPEN]
        if open_shortages:
            st.error(f"JOB BLOCKED - {len(open_shortages)} open shortage(s)")

    tab1, tab2, tab3, tab4 = st.tabs(["Routing", "Kit/Material", "Shortages", "Operations"])

    with tab1:
        _show_routing_overview(job, parser)

    with tab2:
        _show_kit_requirements(job, parser)

    with tab3:
        _show_shortages(job, storage, shortages)

    with tab4:
        _show_operations_detail(job)


def _show_routing_overview(job: Job, parser: RoutingTextParser) -> None:
    """Show routing overview for a job."""
    st.subheader(f"Routing Sequence for {job.job_number}")

    routing_data = []
    for op in job.operations:
        summary = parser.summarize(op.operation_memo, max_lines=2)
        routing_data.append({
            "Op #": op.operation_number,
            "Work Center": op.work_center_name,
            "Qty": op.quantity,
            "Hours": f"{op.production_hours:.1f}",
            "Notes": summary[:50] + "..." if len(summary) > 50 else summary,
        })

    if routing_data:
        st.table(routing_data)


def _show_kit_requirements(job: Job, parser: RoutingTextParser) -> None:
    """Show kit and material requirements."""
    st.subheader("Kit & Material Requirements")

    all_requirements = []

    for op in job.operations:
        if op.operation_memo:
            reqs = parser.parse_kit_requirements(op.operation_memo, job.quantity)
            for req in reqs:
                req["Operation"] = f"Op {op.operation_number} @ {op.work_center_name}"
                all_requirements.append(req)

    if all_requirements:
        req_df = []
        for req in all_requirements:
            delivery = req.get("delivery_to", "")
            req_df.append({
                "Part #": req["part_number"],
                "Description": req["description"],
                "Per Job": req["per_job_qty"],
                "Total Qty": req["total_qty"],
                "Delivery": delivery if delivery else "-",
                "Operation": req["Operation"],
            })

        st.table(req_df)

        st.markdown("### Delivery Instructions Summary")
        deliveries = [(r["part_number"], r.get("delivery_to", ""), r["total_qty"])
                      for r in all_requirements if r.get("delivery_to")]

        if deliveries:
            for part, target, qty in deliveries:
                st.markdown(f"- **{part}** -> **{target}**: {qty} units")
    else:
        st.info("No kit or material requirements found in routing text.")


def _show_shortages(job: Job, storage: OverlayStorage, shortages: list[Shortage]) -> None:
    """Show and manage shortages for a job."""
    st.subheader("Shortages & Blockers")

    with st.expander("Add Shortage"):
        with st.form("add_shortage_form"):
            desc = st.text_input("Description *", placeholder="Missing part or material")
            part = st.text_input("Part Number (optional)")
            qty = st.number_input("Quantity (optional)", min_value=1, value=1)
            notes = st.text_area("Notes (optional)")

            submitted = st.form_submit_button("Add Shortage")
            if submitted and desc:
                new_shortage = Shortage(
                    job_number=job.job_number,
                    description=desc,
                    part=part if part else None,
                    quantity=qty if part else None,
                    notes=notes,
                )
                storage.add_shortage(new_shortage)
                st.success("Shortage added!")
                st.rerun()

    if shortages:
        st.markdown(f"**Total Shortages:** {len(shortages)}")

        for shortage in shortages:
            status_text = shortage.status.value

            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.markdown(f"[{status_text}] **{shortage.description}**")
                with col2:
                    if shortage.part:
                        st.caption(f"Part: {shortage.part}")
                with col3:
                    if shortage.quantity:
                        st.caption(f"Qty: {shortage.quantity}")
                with col4:
                    if shortage.status == ShortageStatus.OPEN:
                        if st.button("Resolve", key=f"resolve_{shortage.id}"):
                            storage.resolve_shortage(shortage.id)
                            st.rerun()

                if shortage.notes:
                    st.caption(f"Notes: {shortage.notes}")
                st.caption(f"Added: {shortage.date_added}")
                st.divider()
    else:
        st.success("No shortages recorded for this job.")


def _show_operations_detail(job: Job) -> None:
    """Show detailed operations view."""
    st.subheader("Operations Detail")

    for i, op in enumerate(job.operations):
        with st.expander(f"Op {op.operation_number}: {op.work_center_name}"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f"**Work Center:** {op.work_center_code}")
            with col2:
                st.markdown(f"**Quantity:** {op.quantity}")
            with col3:
                st.markdown(f"**Unit Time:** {op.unit_production_time_hours} hrs")
            with col4:
                st.markdown(f"**Total Hours:** {op.production_hours:.1f}")

            if op.operation_memo:
                st.markdown("### Routing Text")
                st.text(op.operation_memo)
