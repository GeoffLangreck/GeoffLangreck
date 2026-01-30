"""Capacity & Staffing page for the Shop Scheduler."""

from datetime import date, timedelta
import streamlit as st

from shop_scheduler.models import Employee, EmployeeAbsence
from shop_scheduler.adapters.storage import OverlayStorage
from shop_scheduler.scheduling import CapacityCalculator


def show_capacity_page(
    storage: OverlayStorage,
    work_centers: list[str] = None,
    default_daily_hours: float = 8.0
) -> None:
    """Show the Capacity & Staffing page."""
    st.header("Capacity & Staffing")

    employees = storage.get_employees()
    absences = storage.get_absences()
    calc = CapacityCalculator(employees, absences)

    tab1, tab2, tab3 = st.tabs(["Employees", "Absences", "Capacity View"])

    with tab1:
        _show_employee_roster(storage, employees, work_centers)

    with tab2:
        _show_absences(storage, employees, absences)

    with tab3:
        _show_capacity_view(calc, work_centers, employees, absences, default_daily_hours)


def _show_employee_roster(
    storage: OverlayStorage,
    employees: list[Employee],
    work_centers: list[str] = None
) -> None:
    """Show and manage employee roster."""
    st.subheader("Employee Roster")

    with st.expander("Add Employee"):
        with st.form("add_employee_form"):
            name = st.text_input("Name *", placeholder="John Smith")
            daily_hours = st.number_input(
                "Default Daily Hours",
                min_value=0.5,
                max_value=24.0,
                value=8.0,
                step=0.5
            )

            if work_centers:
                wc_options = work_centers
            else:
                wc_options = ["SAW", "BURN", "LASER", "RAD", "LATHE", "MILL",
                              "BRAKE", "BLACKY", "JACKBEND", "WELD", "CLEAN",
                              "PAINT", "ASSEMBLY", "STOCK", "PANEL"]

            work_centers_sel = st.multiselect(
                "Work Centers (can work at)",
                options=wc_options
            )

            submitted = st.form_submit_button("Add Employee")
            if submitted and name:
                new_emp = Employee(
                    name=name,
                    default_daily_hours=daily_hours,
                    work_centers=work_centers_sel
                )
                storage.add_employee(new_emp)
                st.success(f"Employee {name} added!")
                st.rerun()

    if employees:
        st.markdown(f"**Total Employees:** {len(employees)}")

        for emp in employees:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    st.markdown(f"**{emp.name}**")
                with col2:
                    st.caption(f"{emp.default_daily_hours} hrs/day")
                with col3:
                    if emp.work_centers:
                        st.caption(f"WC: {', '.join(emp.work_centers[:3])}")
                    else:
                        st.caption("All WC")
                with col4:
                    if st.button("Delete", key=f"del_emp_{emp.id}"):
                        storage.delete_employee(emp.id)
                        st.rerun()

                st.divider()
    else:
        st.info("No employees added yet. Add employees to enable capacity planning.")


def _show_absences(
    storage: OverlayStorage,
    employees: list[Employee],
    absences: list[EmployeeAbsence]
) -> None:
    """Show and manage employee absences."""
    st.subheader("Absence Calendar")

    with st.expander("Record Absence"):
        with st.form("add_absence_form"):
            emp_options = {e.id: e.name for e in employees}
            emp_id = st.selectbox(
                "Employee",
                options=list(emp_options.keys()),
                format_func=lambda x: emp_options.get(x, "Unknown")
            ) if employees else None

            absence_date = st.date_input("Date", value=date.today())
            hours_lost = st.number_input(
                "Hours Lost",
                min_value=0.0,
                max_value=24.0,
                value=8.0,
                step=0.5
            )
            reason = st.text_input("Reason (optional)", placeholder="Sick, vacation, etc.")

            submitted = st.form_submit_button("Record Absence")
            if submitted and emp_id:
                new_absence = EmployeeAbsence(
                    employee_id=emp_id,
                    date=absence_date,
                    hours_lost=hours_lost,
                    reason=reason
                )
                storage.add_absence(new_absence)
                st.success("Absence recorded!")
                st.rerun()

    if absences:
        absence_by_date: dict[date, list[EmployeeAbsence]] = {}
        for a in absences:
            if a.date not in absence_by_date:
                absence_by_date[a.date] = []
            absence_by_date[a.date].append(a)

        sorted_dates = sorted(absence_by_date.keys(), reverse=True)

        st.markdown(f"**Total Absence Records:** {len(absences)}")

        for d in sorted_dates[:10]:
            day_absences = absence_by_date[d]
            emp_names = [storage.get_employee(a.employee_id).name if storage.get_employee(a.employee_id) else "Unknown"
                        for a in day_absences]

            st.markdown(f"**{d}**: {', '.join(emp_names)}")

            for a in day_absences:
                emp = storage.get_employee(a.employee_id)
                emp_name = emp.name if emp else "Unknown"
                st.caption(f"  - {emp_name}: {a.hours_lost} hrs - {a.reason}")
    else:
        st.info("No absence records. Add absences to adjust capacity.")


def _show_capacity_view(
    calc: CapacityCalculator,
    work_centers: list[str],
    employees: list[Employee],
    absences: list[EmployeeAbsence],
    default_daily_hours: float
) -> None:
    """Show capacity view by work center and date."""
    st.subheader("Daily Capacity View")

    if not work_centers:
        st.warning("No work centers available. Import jobs first.")
        return

    col1, col2 = st.columns(2)
    with col1:
        selected_wc = st.selectbox("Work Center", options=work_centers)
    with col2:
        num_days = st.slider("Days to Show", 7, 30, 14)

    start_date = date.today()

    capacity_data = []
    for i in range(num_days):
        target_date = start_date + timedelta(days=i)
        available = calc.get_capacity_for_work_center(
            selected_wc, target_date, default_daily_hours
        )

        emp_available = 0
        for emp in employees:
            if selected_wc in emp.work_centers or not emp.work_centers:
                is_absent = any(
                    a.employee_id == emp.id and a.date == target_date
                    for a in absences
                )
                if not is_absent:
                    emp_available += 1

        capacity_data.append({
            "Date": target_date,
            "Available Hours": available,
            "Employees Available": emp_available,
        })

    df = []
    for c in capacity_data:
        day_name = c["Date"].strftime("%a")
        df.append({
            "Date": f"{c['Date']} ({day_name})",
            "Hours": c["Available Hours"],
            "Staff": c["Employees Available"],
        })

    st.table(df)

    total_hours = sum(c["Available Hours"] for c in capacity_data)
    st.markdown(f"**Total Capacity ({num_days} days):** {total_hours:.1f} hours")

    st.markdown("### Staff Allocation")
    if employees:
        st.markdown("Employees that can work at this work center:")
        for emp in employees:
            if selected_wc in emp.work_centers or not emp.work_centers:
                st.markdown(f"- **{emp.name}**: {emp.default_daily_hours} hrs/day")
    else:
        st.info("Add employees to see staffing allocation.")
