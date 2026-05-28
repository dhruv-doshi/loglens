from __future__ import annotations

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from .models import LogRecord

_MASKS = [
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP"),
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "UUID"),
    (r"\b0x[0-9a-fA-F]+\b", "HEX"),
    (r"\b\d+\b", "NUM"),
]


class TemplateParser:
    def __init__(self) -> None:
        config = TemplateMinerConfig()
        config.masking_instructions = [
            MaskingInstruction(pattern=p, mask_with=m) for p, m in _MASKS
        ]
        self._miner = TemplateMiner(config=config)

    def assign(self, record: LogRecord) -> LogRecord:
        result = self._miner.add_log_message(record.message)
        record.template_id = f"T{int(result['cluster_id']):04d}"
        record.template = result["template_mined"]
        return record
