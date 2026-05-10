from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAdapter(ABC):
    """
    All protocol adapters implement this interface.
    Orchestrator only knows this — never the concrete adapter.
    """

    @abstractmethod
    async def call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an action against the target service.

        Args:
            action:  Service-specific operation name (e.g. "getOrder")
            payload: Input parameters for the operation

        Returns:
            Normalized dict response

        Raises:
            AdapterError: On any communication or parsing failure
        """
        ...


class AdapterError(Exception):
    def __init__(self, code: str, message: str, service: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.service = service

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "service": self.service,
        }
