from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    timeout_seconds: int = 30


def load_settings(environment: Mapping[str, str]) -> Settings:
    return Settings()
