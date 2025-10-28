"""Service for interacting with GCS storage and retrieving logs/artifacts."""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from ..config import GCS_URL, DEFAULT_TIMEOUT, QE_GCS_URL, EXTENDED_TIMEOUT
from ..utils.http_client import make_request, make_request_text


class GCSService:
    """Service class for GCS storage interactions."""

    @staticmethod
    def _convert_timestamp(timestamp_value) -> Optional[str]:
        """Convert epoch timestamp to ISO format string.

        Args:
            timestamp_value: Unix epoch timestamp (int or str)

        Returns:
            ISO format datetime string or None if conversion fails
        """
        if timestamp_value is None:
            return None

        try:
            # Convert to int if it's a string
            if isinstance(timestamp_value, str):
                timestamp_value = int(timestamp_value)

            # Convert epoch to datetime
            dt = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError, OSError):
            # Return original value if conversion fails
            return str(timestamp_value) if timestamp_value is not None else None

    @staticmethod
    async def get_builds_for_job(
        job_name: str, gcs_base_url: Optional[str] = None
    ) -> List[str]:
        """Get all build IDs for a specific job from GCS.

        Args:
            job_name: The name of the job
            gcs_base_url: Optional GCS base URL (defaults to GCS_URL)

        Returns:
            List of build IDs sorted by number (newest first)
        """
        base_url = gcs_base_url or GCS_URL
        logs_url = f"{base_url}/logs/{job_name}/"

        html_content = await make_request_text(logs_url, timeout=DEFAULT_TIMEOUT)

        if html_content:
            # QE GCS uses full paths, standard GCS uses relative paths
            # Try both patterns
            build_pattern_full = r'href="[^"]+/(\d+)/"'  # Matches full path like /gcs/.../1234/
            build_pattern_simple = r'<a href="(\d+)/"'   # Matches simple path like 1234/

            builds = re.findall(build_pattern_full, html_content)
            if not builds:
                builds = re.findall(build_pattern_simple, html_content)

            return sorted(builds, key=int, reverse=True)

        return []

    @staticmethod
    async def get_pr_builds(org_repo: str, pr_number: str, job_name: str) -> List[str]:
        """Get all build IDs for a specific PR from GCS PR logs structure.

        Args:
            org_repo: Organization and repository in format "org_repo"
            pr_number: The PR number
            job_name: The name of the job

        Returns:
            List of build IDs sorted by number (newest first)
        """
        pr_logs_url = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}"

        html_content = await make_request_text(pr_logs_url, timeout=DEFAULT_TIMEOUT)
        if html_content:
            build_pattern = r'<a href="(\d+)/"'
            builds = re.findall(build_pattern, html_content)
            return sorted(builds, key=int, reverse=True)

        return []

    @staticmethod
    async def get_build_metadata(
        job_name: str, build_id: str, gcs_base_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get build metadata from started.json file.

        Args:
            job_name: The name of the job
            build_id: The build ID
            gcs_base_url: Optional GCS base URL (defaults to GCS_URL)

        Returns:
            Metadata dictionary or None if not found
        """
        base_url = gcs_base_url or GCS_URL
        metadata_url = f"{base_url}/logs/{job_name}/{build_id}/started.json"

        result = await make_request(metadata_url)
        if result and "error" not in result:
            # Convert timestamp to ISO format if present
            if "timestamp" in result:
                result["timestamp_iso"] = GCSService._convert_timestamp(result["timestamp"])
            return result

        return None

    @staticmethod
    async def find_pr_builds_in_regular_logs(
        job_name: str, pr_number: str, max_builds: int = 10
    ) -> List[str]:
        """Find builds for a PR by scanning regular logs for PR metadata.

        Args:
            job_name: The name of the job
            pr_number: The PR number to search for
            max_builds: Maximum number of recent builds to check

        Returns:
            List of build IDs that are associated with the PR
        """
        all_builds = await GCSService.get_builds_for_job(job_name)
        pr_builds = []

        # Check recent builds for PR metadata
        recent_builds = all_builds[:max_builds]

        for build_id in recent_builds:
            try:
                metadata = await GCSService.get_build_metadata(job_name, build_id)
                if metadata:
                    # Look for PR number in the metadata
                    refs = metadata.get("refs", {})
                    pulls = refs.get("pulls", [])

                    for pull in pulls:
                        if str(pull.get("number", "")) == pr_number:
                            pr_builds.append(build_id)
                            break
            except Exception:
                continue

        return pr_builds

    @staticmethod
    async def get_log_files_in_directory(artifacts_url: str) -> List[str]:
        """Get list of log files in an artifacts directory.

        Args:
            artifacts_url: URL to the artifacts directory

        Returns:
            List of log file names found in the directory
        """
        html_content = await make_request_text(artifacts_url, timeout=DEFAULT_TIMEOUT)
        if html_content:
            # Look for log files in the HTML directory listing
            log_file_pattern = r'href="([^"]*\.(?:txt|log)[^"]*)"'
            return re.findall(log_file_pattern, html_content)

        return []

    @staticmethod
    async def download_file_content(url: str) -> Optional[str]:
        """Download content from a URL.

        Args:
            url: The URL to download from

        Returns:
            File content as string or None if failed
        """
        content = await make_request_text(url, timeout=DEFAULT_TIMEOUT)
        if content:
            # Basic check to see if this looks like actual file content (not a directory listing)
            if not content.strip().startswith("<!doctype html>"):
                return content

        return None
