"""JSON overlay storage adapter.

This adapter stores user modifications and overrides separately from the source CSV.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from shop_scheduler.models import (
    Shortage, ShortageStatus, Employee, EmployeeAbsence, Job
)


class OverlayStorage:
    """Storage adapter for user overlays and modifications."""

    DEFAULT_DATA_DIR = "shop_data"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the storage adapter."""
        self.data_dir = Path(data_dir) if data_dir else Path(self.DEFAULT_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.priorities_file = self.data_dir / "job_priorities.json"
        self.shortages_file = self.data_dir / "shortages.json"
        self.employees_file = self.data_dir / "employees.json"
        self.absences_file = self.data_dir / "absences.json"
        self.schedule_file = self.data_dir / "schedule.json"
        self.jobs_file = self.data_dir / "jobs.json"

    # =========================================================================
    # Job Priorities
    # =========================================================================

    def get_job_priority(self, job_number: str) -> Optional[int]:
        """Get manual priority for a job."""
        priorities = self._load_json(self.priorities_file, {})
        return priorities.get(job_number)

    def set_job_priority(self, job_number: str, priority: int) -> None:
        """Set manual priority for a job."""
        priorities = self._load_json(self.priorities_file, {})
        priorities[job_number] = priority
        self._save_json(self.priorities_file, priorities)

    def remove_job_priority(self, job_number: str) -> None:
        """Remove manual priority override for a job."""
        priorities = self._load_json(self.priorities_file, {})
        if job_number in priorities:
            del priorities[job_number]
            self._save_json(self.priorities_file, priorities)

    def get_all_priorities(self) -> dict:
        """Get all job priorities."""
        return self._load_json(self.priorities_file, {})

    def clear_all_priorities(self) -> None:
        """Clear all job priorities."""
        self._save_json(self.priorities_file, {})

    # =========================================================================
    # Jobs
    # =========================================================================

    def get_jobs(self) -> list[Job]:
        """Get all saved jobs."""
        data = self._load_json(self.jobs_file, [])
        return [Job.from_dict(item) for item in data]

    def save_jobs(self, jobs: list[Job]) -> None:
        """Save all jobs to storage."""
        data = [job.to_dict() for job in jobs]
        self._save_json(self.jobs_file, data)

    def clear_jobs(self) -> None:
        """Clear all saved jobs."""
        self._save_json(self.jobs_file, [])

    def has_saved_jobs(self) -> bool:
        """Check if there are saved jobs."""
        return self.jobs_file.exists() and self.jobs_file.stat().st_size > 0

    # =========================================================================
    # Shortages
    # =========================================================================

    def get_shortages(self, status: Optional[ShortageStatus] = None) -> list[Shortage]:
        """Get shortages, optionally filtered by status."""
        data = self._load_json(self.shortages_file, [])
        shortages = [Shortage.from_dict(item) for item in data]

        if status:
            shortages = [s for s in shortages if s.status == status]

        return shortages

    def get_shortages_for_job(self, job_number: str) -> list[Shortage]:
        """Get all shortages for a specific job."""
        data = self._load_json(self.shortages_file, [])
        shortages = [Shortage.from_dict(item) for item in data]
        return [s for s in shortages if s.job_number == job_number]

    def add_shortage(self, shortage: Shortage) -> None:
        """Add a new shortage."""
        data = self._load_json(self.shortages_file, [])
        data.append(shortage.to_dict())
        self._save_json(self.shortages_file, data)

    def update_shortage(self, shortage: Shortage) -> None:
        """Update an existing shortage."""
        data = self._load_json(self.shortages_file, [])
        for i, item in enumerate(data):
            if item.get("id") == shortage.id:
                data[i] = shortage.to_dict()
                break
        self._save_json(self.shortages_file, data)

    def delete_shortage(self, shortage_id: str) -> None:
        """Delete a shortage by ID."""
        data = self._load_json(self.shortages_file, [])
        data = [item for item in data if item.get("id") != shortage_id]
        self._save_json(self.shortages_file, data)

    def resolve_shortage(self, shortage_id: str) -> None:
        """Mark a shortage as resolved."""
        data = self._load_json(self.shortages_file, [])
        for item in data:
            if item.get("id") == shortage_id:
                item["status"] = ShortageStatus.RESOLVED.value
                break
        self._save_json(self.shortages_file, data)

    def get_open_shortage_job_numbers(self) -> set:
        """Get set of job numbers with open shortages."""
        data = self._load_json(self.shortages_file, [])
        return {item["job_number"] for item in data if item.get("status") == "OPEN"}

    # =========================================================================
    # Employees
    # =========================================================================

    def get_employees(self) -> list[Employee]:
        """Get all employees."""
        data = self._load_json(self.employees_file, [])
        return [Employee.from_dict(item) for item in data]

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        """Get an employee by ID."""
        employees = self.get_employees()
        for emp in employees:
            if emp.id == employee_id:
                return emp
        return None

    def add_employee(self, employee: Employee) -> None:
        """Add a new employee."""
        data = self._load_json(self.employees_file, [])
        data.append(employee.to_dict())
        self._save_json(self.employees_file, data)

    def update_employee(self, employee: Employee) -> None:
        """Update an existing employee."""
        data = self._load_json(self.employees_file, [])
        for i, item in enumerate(data):
            if item.get("id") == employee.id:
                data[i] = employee.to_dict()
                break
        self._save_json(self.employees_file, data)

    def delete_employee(self, employee_id: str) -> None:
        """Delete an employee by ID."""
        data = self._load_json(self.employees_file, [])
        data = [item for item in data if item.get("id") != employee_id]
        self._save_json(self.employees_file, data)

    def clear_all_employees(self) -> None:
        """Clear all employees."""
        self._save_json(self.employees_file, [])

    # =========================================================================
    # Employee Absences
    # =========================================================================

    def get_absences(self, date_filter: Optional[date] = None) -> list[EmployeeAbsence]:
        """Get all absences, optionally filtered by date."""
        data = self._load_json(self.absences_file, [])
        absences = [EmployeeAbsence.from_dict(item) for item in data]

        if date_filter:
            absences = [a for a in absences if a.date == date_filter]

        return absences

    def get_absences_for_employee(self, employee_id: str) -> list[EmployeeAbsence]:
        """Get all absences for a specific employee."""
        data = self._load_json(self.absences_file, [])
        absences = [EmployeeAbsence.from_dict(item) for item in data]
        return [a for a in absences if a.employee_id == employee_id]

    def add_absence(self, absence: EmployeeAbsence) -> None:
        """Add a new absence record."""
        data = self._load_json(self.absences_file, [])
        data.append(absence.to_dict())
        self._save_json(self.absences_file, data)

    def delete_absence(self, employee_id: str, absence_date: date) -> None:
        """Delete an absence record."""
        data = self._load_json(self.absences_file, [])
        data = [
            item for item in data
            if not (item["employee_id"] == employee_id and item["date"] == absence_date.isoformat())
        ]
        self._save_json(self.absences_file, data)

    def clear_all_absences(self) -> None:
        """Clear all absence records."""
        self._save_json(self.absences_file, [])

    # =========================================================================
    # Schedule Results
    # =========================================================================

    def save_schedule_result(self, schedule_data: dict) -> None:
        """Save a schedule result."""
        schedule_data["saved_at"] = datetime.now().isoformat()
        self._save_json(self.schedule_file, schedule_data)

    def load_schedule_result(self) -> Optional[dict]:
        """Load the last saved schedule result."""
        return self._load_json(self.schedule_file, None)

    def clear_schedule_result(self) -> None:
        """Clear saved schedule result."""
        if self.schedule_file.exists():
            self.schedule_file.unlink()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_storage_stats(self) -> dict:
        """Get statistics about stored data."""
        return {
            "priorities_count": len(self._load_json(self.priorities_file, {})),
            "shortages_count": len(self._load_json(self.shortages_file, [])),
            "employees_count": len(self._load_json(self.employees_file, [])),
            "absences_count": len(self._load_json(self.absences_file, [])),
            "jobs_count": len(self._load_json(self.jobs_file, [])),
            "schedule_saved": self.schedule_file.exists(),
            "storage_directory": str(self.data_dir),
        }

    def clear_all_data(self) -> None:
        """Clear all stored data."""
        self.clear_all_priorities()
        self._save_json(self.shortages_file, [])
        self.clear_all_employees()
        self.clear_all_absences()
        self.clear_jobs()
        self.clear_schedule_result()

    def _load_json(self, file_path: Path, default):
        """Load JSON from a file, returning default if not exists."""
        if not file_path.exists():
            return default

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
        except Exception:
            return default

    def _save_json(self, file_path: Path, data) -> None:
        """Save data to a JSON file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
