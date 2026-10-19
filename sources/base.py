from abc import ABC, abstractmethod
from typing import ClassVar
from core.models import Job

class BaseSource(ABC):
    """Abstract Base Source with self-registering plugin pattern."""
    registry: ClassVar[dict[str, type["BaseSource"]]] = {}
    name: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name") and cls.name:
            BaseSource.registry[cls.name] = cls

    @abstractmethod
    def fetch(self, profile: dict, config: dict) -> list[Job]:
        """Fetch and map jobs into unified Job dataclasses."""
        pass