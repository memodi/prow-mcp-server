"""Service for interacting with Prow API and managing job information."""

from typing import Dict, List, Any, Optional
from dateutil.parser import parse as parse_date

from ..utils.http_client import make_request
from ..config import PROW_URL, QE_PROW_URL
from ..models.types import ProwJob


class ProwService:
    """Service class for Prow API interactions."""

    @staticmethod
    async def get_all_jobs() -> List[ProwJob]:
        """Get all active Prow jobs.

        Returns:
            List of all Prow jobs from the API
        """
        url = f"{PROW_URL}/prowjobs.js"
        response = await make_request(url)

        if not response or "error" in response:
            # if first request failed, retry with QE_PROW_URL
            url = f"{QE_PROW_URL}/prowjobs.js"
            response = await make_request(url)
            if not response or "error" in response:
                return []

        return response.get("items", [])

    @staticmethod
    async def get_jobs_by_name(job_name: str) -> List[ProwJob]:
        """Get all jobs matching a specific job name.

        Args:
            job_name: The name of the job to filter for

        Returns:
            List of jobs matching the name, sorted by start time (newest first)
        """
        all_jobs = await ProwService.get_all_jobs()

        # Filter by job name and ensure they have start time
        matching_jobs = [
            job
            for job in all_jobs
            if job.get("spec", {}).get("job") == job_name
            and "startTime" in job.get("status", {})
        ]

        # Sort by startTime descending
        matching_jobs.sort(
            key=lambda job: parse_date(job["status"]["startTime"]), reverse=True
        )

        return matching_jobs

    @staticmethod
    async def get_latest_job_for_name(job_name: str) -> Optional[ProwJob]:
        """Get the latest job for a specific job name.

        Args:
            job_name: The name of the job

        Returns:
            The most recent job or None if not found
        """
        jobs = await ProwService.get_jobs_by_name(job_name)
        return jobs[0] if jobs else None

    @staticmethod
    async def get_job_by_id(job_id: str) -> Optional[ProwJob]:
        """Get a specific job by its ID.

        Args:
            job_id: The job ID to look for

        Returns:
            The job if found, None otherwise
        """
        all_jobs = await ProwService.get_all_jobs()

        return next(
            (job for job in all_jobs if job["metadata"]["name"] == job_id), None
        )

    @staticmethod
    async def get_jobs_for_pr(job_name: str, pr_number: str) -> List[ProwJob]:
        """Get all jobs for a specific PR.

        Args:
            job_name: The name of the job
            pr_number: The PR number to filter for

        Returns:
            List of jobs for the specified PR, sorted by start time (newest first)
        """
        jobs = await ProwService.get_jobs_by_name(job_name)

        pr_jobs = []
        for job in jobs:
            refs = job.get("spec", {}).get("refs", {})
            pulls = refs.get("pulls", [])

            for pull in pulls:
                if str(pull.get("number", "")) == pr_number:
                    pr_jobs.append(job)
                    break

        return pr_jobs
