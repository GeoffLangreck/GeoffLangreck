"""Routing text parser.

Parses the fopermemo field from M2M exports to extract:
- Kit/material requirements
- Delivery instructions
- Section headers
"""

import re
from typing import Optional

from shop_scheduler.models import RoutingTextData, KitItem, DeliveryInstruction


class RoutingTextParser:
    """Parser for M2M routing text / operation memo fields."""

    KIT_TABLE_PATTERN = re.compile(
        r'^\s*(\d+)\s*/\s*([A-Za-z0-9\-]+)\s*/\s*(.+)$'
    )

    DELIVERY_PATTERN = re.compile(
        r'^\s*\((\d+)\s*PER\)\s+([A-Za-z0-9\-]+)\s+\.{3,}\s*DELIVER\s+TO\s+([A-Za-z0-9\s\-]+)$',
        re.IGNORECASE
    )

    SIMPLE_PER_PATTERN = re.compile(
        r'^\s*\((\d+)\s*PER\)\s+([A-Za-z0-9\-]+)\s*(.*)$'
    )

    SECTION_PATTERN = re.compile(
        r'^([A-Z][A-Z0-9\s\-]+):\s*$'
    )

    MATERIAL_PATTERN = re.compile(
        r'^MATERIAL\s*[:\-]?\s*(.*)$',
        re.IGNORECASE
    )

    WORK_CENTER_KEYWORDS = [
        "saw", "burn", "laser", "rad", "lathe", "3 spindle", "mill",
        "brake", "blacky", "jackass", "weld", "clean", "paint",
        "assembly", "stockroom", "panel"
    ]

    def parse(self, text: str) -> RoutingTextData:
        """Parse routing text and extract structured data."""
        if not text:
            return RoutingTextData(raw_text="")

        data = RoutingTextData(raw_text=text)
        lines = text.strip().split('\n')

        for line in lines:
            self._parse_line(line.strip(), data)

        return data

    def _parse_line(self, line: str, data: RoutingTextData) -> None:
        """Parse a single line of routing text."""
        if not line:
            return

        kit_match = self.KIT_TABLE_PATTERN.match(line)
        if kit_match:
            qty = int(kit_match.group(1))
            part_no = kit_match.group(2).strip()
            description = kit_match.group(3).strip()
            data.kit_items.append(KitItem(
                quantity=qty,
                part_number=part_no,
                description=description,
                per_job=True
            ))
            return

        delivery_match = self.DELIVERY_PATTERN.match(line)
        if delivery_match:
            qty = int(delivery_match.group(1))
            part_no = delivery_match.group(2).strip()
            target = delivery_match.group(3).strip()
            data.delivery_instructions.append(DeliveryInstruction(
                quantity=qty,
                part_number=part_no,
                target_work_center=target,
                per_job=True
            ))
            return

        per_match = self.SIMPLE_PER_PATTERN.match(line)
        if per_match:
            qty = int(per_match.group(1))
            part_no = per_match.group(2).strip()
            remainder = per_match.group(3).strip()

            deliver_match = re.search(r'DELIVER\s+TO\s+([A-Za-z0-9\s\-]+)', remainder, re.IGNORECASE)
            if deliver_match:
                target = deliver_match.group(1).strip()
                data.delivery_instructions.append(DeliveryInstruction(
                    quantity=qty,
                    part_number=part_no,
                    target_work_center=target,
                    per_job=True
                ))
            else:
                data.kit_items.append(KitItem(
                    quantity=qty,
                    part_number=part_no,
                    description=remainder if remainder else "See routing",
                    per_job=True
                ))
            return

        section_match = self.SECTION_PATTERN.match(line)
        if section_match:
            section_name = section_match.group(1).strip()
            data.material_sections.append(section_name)
            return

        material_match = self.MATERIAL_PATTERN.match(line)
        if material_match:
            material_content = material_match.group(1).strip()
            if material_content:
                data.material_sections.append(f"MATERIAL: {material_content}")
            else:
                data.material_sections.append("MATERIAL")
            return

    def parse_kit_requirements(self, text: str, job_quantity: int) -> list[dict]:
        """Parse kit requirements and calculate total quantities."""
        data = self.parse(text)
        requirements = []

        for item in data.kit_items:
            total_qty = item.total_quantity(job_quantity)
            requirements.append({
                "part_number": item.part_number,
                "description": item.description,
                "per_job_qty": item.quantity,
                "total_qty": total_qty,
            })

        for instruction in data.delivery_instructions:
            total_qty = instruction.total_quantity(job_quantity)
            requirements.append({
                "part_number": instruction.part_number,
                "description": f"Deliver to {instruction.target_work_center}",
                "per_job_qty": instruction.quantity,
                "total_qty": total_qty,
                "delivery_to": instruction.target_work_center,
            })

        return requirements

    def extract_section_content(self, text: str, section_name: str) -> Optional[str]:
        """Extract content from a specific section."""
        lines = text.strip().split('\n')
        in_section = False
        content_lines = []

        header_pattern = re.compile(
            rf'^{section_name.upper()}\s*[:\-]?\s*$',
            re.IGNORECASE
        )

        for line in lines:
            if header_pattern.match(line):
                in_section = True
                continue
            if in_section:
                if self.SECTION_PATTERN.match(line.strip()):
                    break
                content_lines.append(line)

        return '\n'.join(content_lines).strip() if content_lines else None

    def has_delivery_to(self, text: str, work_center: str) -> bool:
        """Check if routing text contains a delivery instruction to a work center."""
        data = self.parse(text)
        work_center_lower = work_center.lower()

        for instruction in data.delivery_instructions:
            if work_center_lower in instruction.target_work_center.lower():
                return True

        return False

    def get_all_delivery_targets(self, text: str) -> list[str]:
        """Get all work centers mentioned in delivery instructions."""
        data = self.parse(text)
        return [inst.target_work_center for inst in data.delivery_instructions]

    def summarize(self, text: str, max_lines: int = 10) -> str:
        """Create a short summary of routing text for display."""
        if not text:
            return "(No routing text)"

        data = self.parse(text)
        summary_parts = []

        if data.kit_items:
            summary_parts.append(f"{len(data.kit_items)} kit items")

        if data.delivery_instructions:
            targets = list(set(inst.target_work_center for inst in data.delivery_instructions))
            summary_parts.append(f"Deliveries: {', '.join(targets)}")

        if data.material_sections:
            summary_parts.append(f"Sections: {', '.join(data.material_sections[:3])}")

        if summary_parts:
            return "; ".join(summary_parts)
        else:
            lines = [l for l in text.strip().split('\n') if l.strip()][:max_lines]
            return '\n'.join(lines) if lines else "(No content)"


default_parser = RoutingTextParser()
