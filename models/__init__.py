"""Core data models for the shop scheduling system."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from enum import Enum


class ShortageStatus(str, Enum):
    """Status of a shortage."""
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class JobStatus(str, Enum):
    """Status of a job from M2M export."""
    RELEASED = "RELEASED"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class KitItem:
    """A kit/material item from routing text."""
    quantity: int
    part_number: str
    description: str
    per_job: bool = True

    def total_quantity(self, job_quantity: int) -> int:
        """Calculate total quantity needed for the job."""
        if self.per_job:
            return self.quantity * job_quantity
        return self.quantity


@dataclass
class DeliveryInstruction:
    """A delivery instruction from routing text."""
    quantity: int
    part_number: str
    target_work_center: str
    per_job: bool = True

    def total_quantity(self, job_quantity: int) -> int:
        """Calculate total quantity for the job."""
        if self.per_job:
            return self.quantity * job_quantity
        return self.quantity


@dataclass
class RoutingTextData:
    """Parsed data from routing text."""
    kit_items: list[KitItem] = field(default_factory=list)
    material_sections: list[str] = field(default_factory=list)
    delivery_instructions: list[DeliveryInstruction] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class Operation:
    """A single operation in a job's routing."""
    job_number: str
    operation_number: int
    work_center_code: str
    work_center_name: str
    quantity: int
    unit_production_time_hours: float
    setup_time_hours: float = 0.0
    move_time_hours: float = 0.0
    operation_memo: str = ""
    routing_text_data: Optional[RoutingTextData] = None

    @property
    def production_hours(self) -> float:
        """Calculate total production hours for this operation."""
        return self.unit_production_time_hours * self.quantity

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "job_number": self.job_number,
            "operation_number": self.operation_number,
            "work_center_code": self.work_center_code,
            "work_center_name": self.work_center_name,
            "quantity": self.quantity,
            "unit_production_time_hours": self.unit_production_time_hours,
            "production_hours": self.production_hours,
            "operation_memo": self.operation_memo,
        }


@dataclass
class Job:
    """A manufacturing job."""
    job_number: str
    part_number: str
    quantity: int
    due_date: date
    status: JobStatus
    release_date: Optional[date] = None
    actual_release_timestamp: Optional[datetime] = None
    manual_priority: int = 100
    operations: list[Operation] = field(default_factory=list)
    is_blocked: bool = False
    blocked_reason: str = ""

    @property
    def total_production_hours(self) -> float:
        """Calculate total production hours for all operations."""
        return sum(op.production_hours for op in self.operations)

    @property
    def earliest_operation_date(self) -> Optional[date]:
        """Get the earliest operation date from scheduled operations."""
        scheduled = [op for op in self.operations if hasattr(op, 'scheduled_date') and op.scheduled_date]
        if scheduled:
            return min(op.scheduled_date for op in scheduled)
        return None

    @property
    def latest_operation_date(self) -> Optional[date]:
        """Get the latest operation date from scheduled operations."""
        scheduled = [op for op in self.operations if hasattr(op, 'scheduled_date') and op.scheduled_date]
        if scheduled:
            return max(op.scheduled_date for op in scheduled)
        return None

    def get_operation_by_work_center(self, work_center_code: str) -> Optional[Operation]:
        """Get an operation by work center code."""
        for op in self.operations:
            if op.work_center_code == work_center_code:
                return op
        return None

    def get_next_operation(self, current_op: Operation) -> Optional[Operation]:
        """Get the next operation in the routing sequence."""
        try:
            idx = self.operations.index(current_op)
            if idx + 1 < len(self.operations):
                return self.operations[idx + 1]
        except ValueError:
            pass
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "job_number": self.job_number,
            "part_number": self.part_number,
            "quantity": self.quantity,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status.value if self.status else None,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "manual_priority": self.manual_priority,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "total_production_hours": self.total_production_hours,
            "operations": [op.to_dict() for op in self.operations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """Create Job from dictionary (deserialization)."""
        due_date = data.get("due_date")
        if isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)

        release_date = data.get("release_date")
        if isinstance(release_date, str):
            release_date = date.fromisoformat(release_date)

        operations = []
        for op_data in data.get("operations", []):
            op = Operation(
                job_number=op_data["job_number"],
                operation_number=op_data["operation_number"],
                work_center_code=op_data["work_center_code"],
                work_center_name=op_data.get("work_center_name", ""),
                quantity=op_data["quantity"],
                unit_production_time_hours=op_data["unit_production_time_hours"],
                operation_memo=op_data.get("operation_memo", ""),
            )
            operations.append(op)

        return cls(
            job_number=data["job_number"],
            part_number=data["part_number"],
            quantity=data["quantity"],
            due_date=due_date,
            status=JobStatus(data.get("status", "OPEN")),
            release_date=release_date,
            manual_priority=data.get("manual_priority", 100),
            is_blocked=data.get("is_blocked", False),
            blocked_reason=data.get("blocked_reason", ""),
            operations=operations,
        )


@dataclass
class Shortage:
    """A material shortage or blocker for a job."""
    job_number: str
    description: str
    part: Optional[str] = None
    quantity: Optional[int] = None
    status: ShortageStatus = ShortageStatus.OPEN
    notes: str = ""
    date_added: date = field(default_factory=date.today)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "job_number": self.job_number,
            "description": self.description,
            "part": self.part,
            "quantity": self.quantity,
            "status": self.status.value,
            "notes": self.notes,
            "date_added": self.date_added.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Shortage":
        """Create from dictionary."""
        date_added = data.get("date_added")
        if isinstance(date_added, str):
            date_added = date.fromisoformat(date_added)
        return cls(
            id=data.get("id", ""),
            job_number=data["job_number"],
            description=data["description"],
            part=data.get("part"),
            quantity=data.get("quantity"),
            status=ShortageStatus(data.get("status", "OPEN")),
            notes=data.get("notes", ""),
            date_added=date_added or date.today(),
        )


@dataclass
class Employee:
    """An employee in the shop."""
    name: str
    default_daily_hours: float = 8.0
    work_centers: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "default_daily_hours": self.default_daily_hours,
            "work_centers": self.work_centers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Employee":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data["name"],
            default_daily_hours=data.get("default_daily_hours", 8.0),
            work_centers=data.get("work_centers", []),
        )


@dataclass
class EmployeeAbsence:
    """Record of an employee being absent on a specific date."""
    employee_id: str
    date: date
    reason: str = ""
    hours_lost: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "employee_id": self.employee_id,
            "date": self.date.isoformat(),
            "reason": self.reason,
            "hours_lost": self.hours_lost,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmployeeAbsence":
        """Create from dictionary."""
        date_val = data.get("date")
        if isinstance(date_val, str):
            date_val = date.fromisoformat(date_val)
        return cls(
            employee_id=data["employee_id"],
            date=date_val or date.today(),
            reason=data.get("reason", ""),
            hours_lost=data.get("hours_lost", 0.0),
        )


@dataclass
class WorkCenterCapacity:
    """Daily capacity for a work center."""
    work_center_code: str
    date: date
    available_hours: float = 0.0
    scheduled_hours: float = 0.0
    utilization_percent: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "work_center_code": self.work_center_code,
            "date": self.date.isoformat(),
            "available_hours": self.available_hours,
            "scheduled_hours": self.scheduled_hours,
            "utilization_percent": self.utilization_percent,
        }


@dataclass
class ScheduledOperation:
    """An operation with scheduling information."""
    operation: Operation
    job: Job
    scheduled_date: date
    scheduled_start_hour: float = 0.0
    scheduled_end_hour: float = 0.0
    is_late: bool = False
    lateness_hours: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "job_number": self.job.job_number,
            "operation_number": self.operation.operation_number,
            "work_center_code": self.operation.work_center_code,
            "work_center_name": self.operation.work_center_name,
            "scheduled_date": self.scheduled_date.isoformat(),
            "scheduled_hours": self.scheduled_end_hour - self.scheduled_start_hour,
            "is_late": self.is_late,
            "lateness_hours": self.lateness_hours,
        }


@dataclass
class ScheduleResult:
    """The result of a scheduling run."""
    scheduled_operations: list[ScheduledOperation] = field(default_factory=list)
    unscheduled_operations: list[Operation] = field(default_factory=list)
    jobs_on_time: int = 0
    jobs_late: int = 0
    blocked_jobs: list[str] = field(default_factory=list)
    schedule_date: date = field(default_factory=date.today)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "schedule_date": self.schedule_date.isoformat(),
            "jobs_on_time": self.jobs_on_time,
            "jobs_late": self.jobs_late,
            "blocked_jobs": self.blocked_jobs,
            "notes": self.notes,
            "scheduled_operations": [so.to_dict() for so in self.scheduled_operations],
        }
