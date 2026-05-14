"""Tournament Harness configuration (process-level defaults).

Tournament-run shape (architectures × symbols × HP grid) lives in the operator's
tournament.yaml — NOT here (D-11). This class only holds:
  - service ports / paths
  - default Docker SDK resource caps (D-04)
  - default DB / leaderboard / results paths
  - TimescaleDB connection (read-only tournament_reader role, D-09)
  - Docker SDK runner image tag (D-05)
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TournamentSettings(BaseSettings):
    # Service Configuration
    service_name: str = Field(default="tournament-harness")
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8010)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Default per-experiment resource caps (D-04). Override per-arch in YAML.
    default_mem_limit: str = Field(default="4g")
    default_cpus: float = Field(default=2.0)
    default_wallclock_timeout_seconds: int = Field(default=1800)  # 30 min — CD-02

    # Storage paths (host-side; bind-mounted into orchestrator container)
    leaderboard_db_path: str = Field(default="/app/data/leaderboard/leaderboard.db")
    results_dir: str = Field(default="/app/data/results")
    snapshots_dir: str = Field(default="/app/data/snapshots")

    # TimescaleDB connection (read-only tournament_reader role, D-09)
    timescale_host: str = Field(default="timescaledb")
    timescale_port: int = Field(default=5432)
    timescale_db: str = Field(default="trading_bot")
    timescale_user: str = Field(default="tournament_reader")
    timescale_password: str = Field(default="")

    # Docker network the experiment containers join (D-09)
    docker_network: str = Field(default="crypto-bot-network")

    # Image tag for experiment containers (D-05 — same image as orchestrator)
    runner_image: str = Field(default="crypto-bot-tournament-harness:latest")

    @property
    def timescale_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.timescale_user}:{self.timescale_password}"
            f"@{self.timescale_host}:{self.timescale_port}/{self.timescale_db}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: Optional[TournamentSettings] = None


def get_settings() -> TournamentSettings:
    global _settings
    if _settings is None:
        _settings = TournamentSettings()
    return _settings
