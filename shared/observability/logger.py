from __future__ import annotations

import json
import logging
from pathlib import Path

from domain.models import AgentLogEntry


class JsonExecutionLogger:
    def __init__(self, root_path: str = ".coreflow/logs"):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("coreflow")
        self._logger.setLevel(logging.INFO)

    def log(self, correlation_id: str, agent_name: str, level: str, message: str, payload: dict | None = None) -> AgentLogEntry:
        entry = AgentLogEntry(
            correlation_id=correlation_id,
            agent_name=agent_name,
            level=level.lower(),
            message=message,
            payload=payload or {},
        )
        line = entry.model_dump(mode="json")
        self._logger.log(getattr(logging, level.upper(), logging.INFO), json.dumps(line, default=str))
        log_dir = self.root_path / correlation_id
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"{agent_name}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, default=str) + "\n")
        return entry
