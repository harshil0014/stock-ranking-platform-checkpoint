"""Configuration for the working Baseline V1 engine."""

from dataclasses import dataclass


BASELINE_METHOD_VERSION = "baseline_v1_equal_rank_mean"


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    """Stable configuration passed to the Baseline V1 engine."""

    top_n: int = 5
    method_version: str = BASELINE_METHOD_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.top_n, bool)
            or not isinstance(self.top_n, int)
            or self.top_n <= 0
        ):
            raise ValueError("top_n must be a positive integer")
        if not self.method_version.strip():
            raise ValueError("method_version must not be blank")
