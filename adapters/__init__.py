"""CSV adapter for importing Made2Manage routing exports.

This adapter is designed to handle:
- Varying column names (with fallbacks)
- Optional columns
- Quoted multiline fields
- Future exports that may have additional or different columns
"""

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from shop_scheduler.models import (
    Job, Operation, JobStatus, RoutingTextData
)


def _to_str(value) -> str:
    """Safely convert a value to string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


class ColumnMapping:
    """Maps CSV column names to internal field names with fallbacks."""

    # Column name variations (lowercase, various spellings)
    MAPPINGS = {
        "job_number": ["fjobno", "jobno", "job_number", "job", "job_num"],
        "status": ["fstatus", "status", "job_status"],
        "part_number": ["fpartno", "partno", "part_number", "part", "part_num"],
        "quantity": ["fquantity", "quantity", "qty", "job_quantity"],
        "due_date": ["fddue_date", "due_date", "fduedate", "due", "ddue"],
        "release_date": ["frel_dt", "release_date", "rel_dt", "frel", "release"],
        "actual_release": ["fact_rel", "actual_release", "act_rel", "released_at"],
        "operation_number": ["foperno", "operno", "operation_number", "oper_no", "oper"],
        "work_center_code": ["fpro_id", "pro_id", "work_center_code", "wc", "wc_code"],
        "work_center_name": ["fcpro_name", "cpro_name", "work_center_name", "wc_name", "pro_name"],
        "operation_quantity": ["foperqty", "operqty", "operation_quantity", "oper_qty"],
        "unit_production_time": ["fuprodtime", "uprodtime", "unit_prod_time", "prod_time", "unit_time"],
        "setup_time": ["fsetuptime", "setuptime", "setup_time", "setup"],
        "move_time": ["fmovetime", "movetime", "move_time", "move"],
        "operation_memo": ["fopermemo", "opermemo", "operation_memo", "memo", "routing_text"],
    }

    def __init__(self, headers: list[str]):
        """Initialize mapping from CSV headers."""
        self.headers = [_to_str(h).lower() for h in headers]
        self.column_map = {}
        self._build_mapping()

    def _build_mapping(self) -> None:
        """Build mapping from available headers to internal names."""
        for internal_name, variations in self.MAPPINGS.items():
            for var in variations:
                if var in self.headers:
                    actual_header = self.headers[self.headers.index(var)]
                    self.column_map[internal_name] = actual_header
                    break

    def get(self, internal_name: str, row: dict) -> Optional[str]:
        """Get a column value by internal name."""
        header = self.column_map.get(internal_name)
        if header:
            value = row.get(header)
            return _to_str(value) if value else ""
        return None

    def has(self, internal_name: str) -> bool:
        """Check if a column exists."""
        return internal_name in self.column_map

    def missing_columns(self) -> list[str]:
        """Get list of essential columns that are missing."""
        essential = ["job_number", "part_number", "quantity", "due_date", "operation_number"]
        return [col for col in essential if col not in self.column_map]


class CSVImportResult:
    """Result of a CSV import operation."""

    def __init__(
        self,
        jobs: list[Job],
        column_mapping: ColumnMapping,
        warnings: list[str],
        errors: list[str],
    ):
        self.jobs = jobs
        self.column_mapping = column_mapping
        self.warnings = warnings
        self.errors = errors
        self.row_count = 0
        self.jobs_loaded = 0

    def has_errors(self) -> bool:
        """Check if there were any errors."""
        return len(self.errors) > 0

    def summary(self) -> str:
        """Get a summary of the import."""
        return (
            f"Rows processed: {self.row_count}, "
            f"Jobs loaded: {self.jobs_loaded}, "
            f"Warnings: {len(self.warnings)}, "
            f"Errors: {len(self.errors)}"
        )


class CSVAdapter:
    """Adapter for importing M2M routing exports from CSV files."""

    # Known work center display names to codes mapping
    WORK_CENTER_NAMES = {
        "saw": "SAW",
        "burn": "BURN",
        "laser": "LASER",
        "rad": "RAD",
        "lathe": "LATHE",
        "3 spindle": "3SPINDLE",
        "3spindle": "3SPINDLE",
        "mill": "MILL",
        "brake": "BRAKE",
        "blacky": "BLACKY",
        "jackass bender": "JACKBEND",
        "jab": "JACKBEND",
        "weld": "WELD",
        "clean": "CLEAN",
        "paint": "PAINT",
        "assembly": "ASSEMBLY",
        "stockroom": "STOCK",
        "panel build": "PANEL",
        "panel": "PANEL",
    }

    def __init__(self, file_path: Optional[str] = None):
        """Initialize the adapter."""
        self.file_path = file_path
        self.jobs: list[Job] = []
        self._column_mapping: Optional[ColumnMapping] = None

    def _normalize_work_center_code(self, code: str, display_name: str) -> str:
        """Normalize a work center code."""
        if not code:
            # Try to derive from display name
            name_lower = _to_str(display_name).lower()
            for key, normalized in self.WORK_CENTER_NAMES.items():
                if key in name_lower:
                    return normalized
            return _to_str(display_name).upper() if display_name else "UNKNOWN"

        # Clean up the code
        code_clean = _to_str(code).upper()
        if len(code_clean) <= 4:
            return code_clean
        # Try to find a shorter code
        for key, normalized in self.WORK_CENTER_NAMES.items():
            if key in code_clean.lower():
                return normalized
        return code_clean

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse a date string in various formats."""
        if not date_str:
            return None

        date_str = _to_str(date_str)

        # Try common formats
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%m-%d-%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # Try ISO format directly
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass

        return None

    def _parse_status(self, status_str: str) -> JobStatus:
        """Parse a job status string."""
        if not status_str:
            return JobStatus.OPEN

        status_lower = _to_str(status_str).lower()

        if status_lower in ["released", "rel"]:
            return JobStatus.RELEASED
        elif status_lower in ["completed", "done", "closed"]:
            return JobStatus.COMPLETED
        elif status_lower in ["cancelled", "cancel", "void"]:
            return JobStatus.CANCELLED
        else:
            return JobStatus.OPEN

    def _parse_float(self, value: str) -> float:
        """Parse a float value."""
        if not value:
            return 0.0
        # Remove any non-numeric characters except . and -
        cleaned = re.sub(r'[^\d.-]', '', str(value).strip())
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _parse_int(self, value: str) -> int:
        """Parse an integer value."""
        if not value:
            return 0
        cleaned = re.sub(r'[^\d]', '', str(value).strip())
        try:
            return int(cleaned) if cleaned else 0
        except ValueError:
            return 0

    def import_file(self, file_path: str) -> CSVImportResult:
        """Import a CSV file and return jobs."""
        self.file_path = file_path
        result = self._parse_csv(Path(file_path))
        # FIX: Store parsed jobs on the adapter so callers can access them
        self.jobs = result.jobs
        return result

    def import_dataframe(self, df) -> CSVImportResult:
        """Import from a pandas DataFrame."""
        result = self._parse_dataframe(df)
        # FIX: Store parsed jobs on the adapter so callers can access them
        self.jobs = result.jobs
        return result

    def _parse_csv(self, file_path: Path) -> CSVImportResult:
        """Parse a CSV file."""
        warnings = []
        errors = []
        jobs: list[Job] = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read with csv.DictReader to handle quoted fields
                reader = csv.DictReader(f)
                return self._process_rows(list(reader))
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    reader = csv.DictReader(f)
                    return self._process_rows(list(reader))
            except Exception as e:
                errors.append(f"Failed to read file: {str(e)}")
                return CSVImportResult(jobs, ColumnMapping([]), warnings, errors)
        except Exception as e:
            errors.append(f"Failed to read file: {str(e)}")
            return CSVImportResult(jobs, ColumnMapping([]), warnings, errors)

    def _parse_dataframe(self, df) -> CSVImportResult:
        """Parse a pandas DataFrame."""
        # Convert DataFrame to list of dicts
        rows = df.to_dict('records')
        # Convert column names to lowercase for consistency
        normalized_rows = []
        for row in rows:
            normalized_row = {_to_str(k).lower(): v for k, v in row.items()}
            normalized_rows.append(normalized_row)
        return self._process_rows(normalized_rows)

    def _process_rows(self, rows: list[dict]) -> CSVImportResult:
        """Process CSV rows and build jobs."""
        warnings = []
        errors = []
        jobs: list[Job] = []

        if not rows:
            errors.append("No data rows found in CSV")
            return CSVImportResult(jobs, ColumnMapping([]), warnings, errors)

        # Build column mapping from first row
        first_row = rows[0]
        headers = list(first_row.keys())
        self._column_mapping = ColumnMapping(headers)

        # Check for essential columns
        missing = self._column_mapping.missing_columns()
        if missing:
            errors.append(f"Missing essential columns: {', '.join(missing)}")

        # Group rows by job
        job_rows: dict[str, list[dict]] = {}
        for i, row in enumerate(rows):
            job_no = _to_str(row.get(self._column_mapping.column_map.get("job_number", "")))
            if not job_no:
                warnings.append(f"Row {i+1}: Missing job number, skipping")
                continue
            if job_no not in job_rows:
                job_rows[job_no] = []
            job_rows[job_no].append(row)

        # Build Job objects
        for job_no, job_data in job_rows.items():
            job = self._build_job(job_no, job_data)
            if job:
                jobs.append(job)

        result = CSVImportResult(jobs, self._column_mapping, warnings, errors)
        result.row_count = len(rows)
        result.jobs_loaded = len(jobs)

        return result

    def _build_job(self, job_no: str, rows: list[dict]) -> Optional[Job]:
        """Build a Job object from CSV rows."""
        first_row = rows[0]
        mapping = self._column_mapping

        # Parse job-level fields
        part_no = mapping.get("part_number", first_row) or ""
        quantity = mapping.get("quantity", first_row) or "0"
        due_date_str = mapping.get("due_date", first_row) or ""
        status_str = mapping.get("status", first_row) or ""
        release_date_str = mapping.get("release_date", first_row) or ""
        actual_release_str = mapping.get("actual_release", first_row) or ""

        due_date = self._parse_date(due_date_str)
        release_date = self._parse_date(release_date_str)
        actual_release = self._parse_date(actual_release_str)

        if not due_date:
            due_date = date.today()  # Fallback

        job = Job(
            job_number=job_no,
            part_number=part_no,
            quantity=self._parse_int(quantity),
            due_date=due_date,
            status=self._parse_status(status_str),
            release_date=release_date,
            actual_release_timestamp=actual_release,
        )

        # Build operations
        for row in rows:
            op = self._build_operation(job_no, row)
            if op:
                job.operations.append(op)

        # Sort operations by operation number
        job.operations.sort(key=lambda x: x.operation_number)

        return job

    def _build_operation(self, job_no: str, row: dict) -> Optional[Operation]:
        """Build an Operation object from a CSV row."""
        mapping = self._column_mapping

        op_no_str = mapping.get("operation_number", row) or "0"
        wc_code = mapping.get("work_center_code", row) or ""
        wc_name = mapping.get("work_center_name", row) or ""
        op_qty_str = mapping.get("operation_quantity", row) or _to_str(row.get("quantity")) or "0"
        uprod_time_str = mapping.get("unit_production_time", row) or "0"
        setup_time_str = mapping.get("setup_time", row) or "0"
        move_time_str = mapping.get("move_time", row) or "0"
        memo = mapping.get("operation_memo", row) or ""

        op_no = self._parse_int(op_no_str)
        if op_no == 0:
            return None  # Skip invalid operations

        wc_code = self._normalize_work_center_code(wc_code, wc_name)

        return Operation(
            job_number=job_no,
            operation_number=op_no,
            work_center_code=wc_code,
            work_center_name=wc_name or wc_code,
            quantity=self._parse_int(op_qty_str),
            unit_production_time_hours=self._parse_float(uprod_time_str),
            setup_time_hours=self._parse_float(setup_time_str),
            move_time_hours=self._parse_float(move_time_str),
            operation_memo=memo,
        )

    def get_work_centers(self) -> list[str]:
        """Get list of unique work centers from loaded jobs."""
        work_centers = set()
        for job in self.jobs:
            for op in job.operations:
                work_centers.add(op.work_center_code)
        return sorted(work_centers)

    def detect_column_info(self) -> dict:
        """Get information about detected columns."""
        if not self._column_mapping:
            return {"status": "No data loaded"}

        info = {
            "all_columns": self._column_mapping.headers,
            "mapped_columns": list(self._column_mapping.column_map.keys()),
            "missing_essential": self._column_mapping.missing_columns(),
        }
        return info
