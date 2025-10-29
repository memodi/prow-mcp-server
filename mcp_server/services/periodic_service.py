"""Service for managing periodic job configurations."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PeriodicJobConfig:
    """Configuration for a periodic job team."""
    team_name: str
    jobs: List[str]


class PeriodicService:
    """Service class for periodic job configuration management."""

    _configs_cache: Dict[str, PeriodicJobConfig] = {}
    _all_jobs_cache: Dict[str, str] = {}  # job_name -> team_name mapping

    @staticmethod
    def _get_periodics_dir() -> Path:
        """Get the path to the periodics directory."""
        current_file = Path(__file__)
        periodics_dir = current_file.parent.parent / "periodics"
        return periodics_dir

    @staticmethod
    def load_team_config(team_name: str) -> Optional[PeriodicJobConfig]:
        """Load configuration for a specific team.

        Args:
            team_name: The name of the team (e.g., 'netobserv')

        Returns:
            PeriodicJobConfig if found, None otherwise
        """
        # Check cache first
        if team_name in PeriodicService._configs_cache:
            return PeriodicService._configs_cache[team_name]

        periodics_dir = PeriodicService._get_periodics_dir()
        config_file = periodics_dir / f"{team_name}.json"

        if not config_file.exists():
            return None

        try:
            with open(config_file, 'r') as f:
                data = json.load(f)

            config = PeriodicJobConfig(
                team_name=team_name,
                jobs=data.get("periodic_jobs", [])
            )

            # Cache the config
            PeriodicService._configs_cache[team_name] = config

            # Update the all jobs cache
            for job in config.jobs:
                PeriodicService._all_jobs_cache[job] = team_name

            return config

        except Exception:
            return None

    @staticmethod
    def load_all_configs() -> Dict[str, PeriodicJobConfig]:
        """Load all periodic job configurations from the periodics directory.

        Returns:
            Dictionary mapping team names to their configurations
        """
        periodics_dir = PeriodicService._get_periodics_dir()

        if not periodics_dir.exists():
            return {}

        configs = {}

        for config_file in periodics_dir.glob("*.json"):
            team_name = config_file.stem
            config = PeriodicService.load_team_config(team_name)
            if config:
                configs[team_name] = config

        return configs

    @staticmethod
    def get_team_for_job(job_name: str) -> Optional[str]:
        """Find which team a job belongs to.

        Args:
            job_name: The periodic job name

        Returns:
            Team name if found, None otherwise
        """
        # Check cache first
        if job_name in PeriodicService._all_jobs_cache:
            return PeriodicService._all_jobs_cache[job_name]

        # Search through team config files individually
        periodics_dir = PeriodicService._get_periodics_dir()

        if not periodics_dir.exists():
            return None

        for config_file in periodics_dir.glob("*.json"):
            team_name = config_file.stem

            # Load only this team's config
            config = PeriodicService.load_team_config(team_name)

            # Check if job is in this team's jobs
            if config and job_name in config.jobs:
                # Cache the result for future lookups
                PeriodicService._all_jobs_cache[job_name] = team_name
                return team_name

        return None

    @staticmethod
    def get_jobs_for_team(team_name: str) -> List[str]:
        """Get all jobs for a specific team.

        Args:
            team_name: The name of the team

        Returns:
            List of job names for the team
        """
        config = PeriodicService.load_team_config(team_name)
        return config.jobs if config else []

    @staticmethod
    def list_all_teams() -> List[str]:
        """List all teams that have periodic job configurations.

        Returns:
            List of team names
        """
        configs = PeriodicService.load_all_configs()
        return list(configs.keys())
