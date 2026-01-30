"""Scheduling logic for manufacturing jobs.

This scheduler implements a due-date-aware scheduling algorithm:
1. Maximize jobs completed on or before due date
2. Minimize lateness for jobs that will be late
3. Respect manual priority overrides
4. Account for staffing-based capacity per work center
5. Handle blocked jobs (shortages)
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from shop_scheduler.models import (
    Job, Operation, Employee, EmployeeAbsence, ShortageStatus,
    ScheduledOperation, ScheduleResult, WorkCenterCapacity
)


class CapacityCalculator:
    """Calculates daily capacity per work center based on staffing."""

    def __init__(self, employees: list[Employee], absences: list[EmployeeAbsence]):
        """Initialize with employee roster and absences."""
        self.employees = employees
        self.absences = absences
        self._build_absence_lookup()

    def _build_absence_lookup(self):
        """Build a lookup for absences by employee and date."""
        self.absence_lookup: dict[str, dict[date, EmployeeAbsence]] = {}
        for absence in self.absences:
            if absence.employee_id not in self.absence_lookup:
                self.absence_lookup[absence.employee_id] = {}
            self.absence_lookup[absence.employee_id][absence.date] = absence

    def get_capacity_for_work_center(
        self,
        work_center_code: str,
        target_date: date,
        default_daily_hours: float = 8.0
    ) -> float:
        """Calculate available hours for a work center on a given date."""
        total_hours = 0.0

        for emp in self.employees:
            if work_center_code not in emp.work_centers and emp.work_centers:
                continue

            absence = self.absence_lookup.get(emp.id, {}).get(target_date)
            if absence:
                hours_lost = absence.hours_lost if absence.hours_lost > 0 else emp.default_daily_hours
                total_hours += max(0, emp.default_daily_hours - hours_lost)
            else:
                total_hours += emp.default_daily_hours

        return total_hours

    def get_capacity_map(
        self,
        work_center_codes: list[str],
        start_date: date,
        num_days: int,
        default_daily_hours: float = 8.0
    ) -> dict[tuple[str, date], float]:
        """Get capacity map for multiple work centers and dates."""
        capacity_map = {}
        for wc_code in work_center_codes:
            for i in range(num_days):
                target_date = start_date + timedelta(days=i)
                cap = self.get_capacity_for_work_center(wc_code, target_date, default_daily_hours)
                capacity_map[(wc_code, target_date)] = cap
        return capacity_map


class Scheduler:
    """Main scheduling engine.

    Uses a greedy algorithm to schedule jobs:
    1. Sort jobs by due date priority, then manual priority
    2. For each job, schedule operations in sequence
    3. Respect work center capacity limits
    4. Track lateness and blocked jobs
    """

    ROUTING_PRECEDENCE = [
        "SAW", "BURN", "LASER", "RAD", "LATHE", "3SPINDLE",
        "MILL", "BRAKE", "BLACKY", "JACKBEND", "WELD",
        "CLEAN", "PAINT", "ASSEMBLY",
    ]

    SUPPORT_OPERATIONS = {"STOCK", "PANEL"}

    def __init__(
        self,
        capacity_calculator: Optional[CapacityCalculator] = None,
        default_daily_capacity: float = 8.0,
        work_day_hours: float = 8.0
    ):
        self.capacity_calculator = capacity_calculator
        self.default_daily_capacity = default_daily_capacity
        self.work_day_hours = work_day_hours
        self.schedule_result: Optional[ScheduleResult] = None

    def schedule(
        self,
        jobs: list[Job],
        blocked_job_numbers: set[str],
        start_date: Optional[date] = None,
        schedule_horizon_days: int = 90
    ) -> ScheduleResult:
        """Schedule all jobs."""
        if start_date is None:
            start_date = date.today()

        # Initialize result
        # FIX: Only initialize blocked_jobs once here — don't append again later
        result = ScheduleResult(
            blocked_jobs=list(blocked_job_numbers),
            schedule_date=start_date,
        )

        # Filter to active jobs
        active_jobs = [
            j for j in jobs
            if j.status.value not in ["COMPLETED", "CANCELLED"]
        ]

        # Get unique work centers
        work_centers = set()
        for job in active_jobs:
            for op in job.operations:
                work_centers.add(op.work_center_code)

        # Build capacity map
        capacity_map = {}
        if self.capacity_calculator:
            capacity_map = self.capacity_calculator.get_capacity_map(
                list(work_centers),
                start_date,
                schedule_horizon_days
            )
        else:
            for wc in work_centers:
                for i in range(schedule_horizon_days):
                    target_date = start_date + timedelta(days=i)
                    capacity_map[(wc, target_date)] = self.default_daily_capacity

        work_center_schedules: dict[tuple[str, date], list[tuple[str, float, int]]] = {}

        # FIX: Schedule blocked jobs but do NOT re-append to result.blocked_jobs
        # (they were already added during initialization above)
        for job in active_jobs:
            if job.job_number in blocked_job_numbers:
                for op in job.operations:
                    scheduled_op = ScheduledOperation(
                        operation=op,
                        job=job,
                        scheduled_date=start_date,
                        is_late=False,
                    )
                    result.scheduled_operations.append(scheduled_op)

        # Sort jobs by priority
        sorted_jobs = sorted(
            active_jobs,
            key=lambda j: (
                (j.due_date - start_date).days,
                j.manual_priority,
                j.job_number,
            )
        )

        job_completion_dates: dict[str, date] = {}

        for job in sorted_jobs:
            if job.job_number in blocked_job_numbers:
                continue

            current_date = start_date

            if job.release_date and job.release_date > current_date:
                current_date = job.release_date

            for op in job.operations:
                if op.work_center_code in self.SUPPORT_OPERATIONS:
                    scheduled_op = ScheduledOperation(
                        operation=op,
                        job=job,
                        scheduled_date=current_date,
                        is_late=False,
                    )
                    result.scheduled_operations.append(scheduled_op)
                    continue

                hours_needed = op.production_hours
                if hours_needed <= 0:
                    hours_needed = 0.1

                scheduled_date = self._find_available_capacity(
                    op.work_center_code,
                    current_date,
                    hours_needed,
                    capacity_map,
                    work_center_schedules,
                    schedule_horizon_days,
                    start_date
                )

                if scheduled_date:
                    is_late = scheduled_date > job.due_date
                    lateness_hours = 0.0
                    if is_late:
                        days_late = (scheduled_date - job.due_date).days
                        lateness_hours = days_late * self.work_day_hours

                    scheduled_op = ScheduledOperation(
                        operation=op,
                        job=job,
                        scheduled_date=scheduled_date,
                        scheduled_start_hour=0.0,
                        scheduled_end_hour=hours_needed,
                        is_late=is_late,
                        lateness_hours=lateness_hours,
                    )
                    result.scheduled_operations.append(scheduled_op)

                    key = (op.work_center_code, scheduled_date)
                    if key not in work_center_schedules:
                        work_center_schedules[key] = []
                    work_center_schedules[key].append((job.job_number, hours_needed, job.manual_priority))

                    current_date = scheduled_date
                else:
                    result.unscheduled_operations.append(op)

            if job.operations:
                last_op_scheduled = [
                    so for so in result.scheduled_operations
                    if so.job.job_number == job.job_number
                ]
                if last_op_scheduled:
                    completion_date = max(so.scheduled_date for so in last_op_scheduled)
                    job_completion_dates[job.job_number] = completion_date

                    if completion_date <= job.due_date:
                        result.jobs_on_time += 1
                    else:
                        result.jobs_late += 1

        if result.unscheduled_operations:
            result.notes.append(
                f"{len(result.unscheduled_operations)} operations could not be scheduled "
                "(capacity exceeded within horizon)"
            )

        if result.blocked_jobs:
            result.notes.append(
                f"{len(result.blocked_jobs)} jobs have open shortages and are blocked"
            )

        self.schedule_result = result
        return result

    def _find_available_capacity(
        self,
        work_center_code: str,
        earliest_date: date,
        hours_needed: float,
        capacity_map: dict[tuple[str, date], float],
        work_center_schedules: dict[tuple[str, date], list[tuple[str, float, int]]],
        horizon_days: int,
        schedule_start: date
    ) -> Optional[date]:
        """Find the earliest date with available capacity for an operation."""
        max_date = schedule_start + timedelta(days=horizon_days)

        for i in range(horizon_days):
            target_date = earliest_date + timedelta(days=i)
            if target_date > max_date:
                break

            if target_date.weekday() >= 5:
                continue

            key = (work_center_code, target_date)
            available = capacity_map.get(key, self.default_daily_capacity)

            scheduled_hours = 0.0
            if key in work_center_schedules:
                scheduled_hours = sum(item[1] for item in work_center_schedules[key])

            remaining = available - scheduled_hours
            if remaining >= hours_needed:
                return target_date

        return None

    def calculate_utilization(
        self,
        schedule_result: ScheduleResult,
        work_centers: list[str],
        start_date: date,
        num_days: int
    ) -> list[WorkCenterCapacity]:
        """Calculate utilization percentages for work centers."""
        utilizations = []

        for wc in work_centers:
            for i in range(num_days):
                target_date = start_date + timedelta(days=i)

                scheduled_hours = 0.0
                for so in schedule_result.scheduled_operations:
                    if (so.operation.work_center_code == wc and
                        so.scheduled_date == target_date):
                        scheduled_hours += (so.scheduled_end_hour - so.scheduled_start_hour)

                available_hours = self.default_daily_capacity
                if self.capacity_calculator:
                    available_hours = self.capacity_calculator.get_capacity_for_work_center(
                        wc, target_date, self.default_daily_capacity
                    )

                utilization = (scheduled_hours / available_hours * 100) if available_hours > 0 else 0

                utilizations.append(WorkCenterCapacity(
                    work_center_code=wc,
                    date=target_date,
                    available_hours=available_hours,
                    scheduled_hours=scheduled_hours,
                    utilization_percent=utilization,
                ))

        return utilizations

    def get_bottleneck_work_centers(
        self,
        schedule_result: ScheduleResult,
        utilization_threshold: float = 90.0
    ) -> list[tuple[str, float]]:
        """Identify work centers with high utilization (potential bottlenecks)."""
        wc_hours: dict[str, float] = {}

        for so in schedule_result.scheduled_operations:
            wc = so.operation.work_center_code
            hours = so.scheduled_end_hour - so.scheduled_start_hour
            wc_hours[wc] = wc_hours.get(wc, 0) + hours

        sorted_wc = sorted(wc_hours.items(), key=lambda x: x[1], reverse=True)
        return sorted_wc[:5]

    def explain_scheduling_decision(
        self,
        job: Job,
        schedule_result: ScheduleResult
    ) -> list[str]:
        """Generate explanation for why a job is scheduled when it is."""
        explanations = []

        job_scheduled = [
            so for so in schedule_result.scheduled_operations
            if so.job.job_number == job.job_number
        ]

        if not job_scheduled:
            explanations.append(f"Job {job.job_number} could not be scheduled")
            if job.job_number in schedule_result.blocked_jobs:
                explanations.append("Reason: Job has open shortages and is blocked")
            return explanations

        completion_date = max(so.scheduled_date for so in job_scheduled)
        if completion_date > job.due_date:
            days_late = (completion_date - job.due_date).days
            explanations.append(
                f"Job {job.job_number} is projected to be {days_late} day(s) late "
                f"(due: {job.due_date}, projected completion: {completion_date})"
            )
        else:
            days_before = (job.due_date - completion_date).days
            explanations.append(
                f"Job {job.job_number} is projected to complete {days_before} day(s) before due date"
            )

        if job.manual_priority < 100:
            explanations.append(
                f"Job has manual priority override ({job.manual_priority})"
            )

        last_op = job_scheduled[-1]
        if last_op.is_late:
            explanations.append(
                f"Last operation ({last_op.operation.work_center_name}) "
                f"scheduled for {last_op.scheduled_date} due to capacity"
            )

        return explanations
