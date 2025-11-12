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
            build_pattern_full = (
                r'href="[^"]+/(\d+)/"'  # Matches full path like /gcs/.../1234/
            )
            build_pattern_simple = r'<a href="(\d+)/"'  # Matches simple path like 1234/

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
            build_pattern = r'href=".+pull-.+/(\d+)/">'
            builds = re.findall(build_pattern, html_content)
            return sorted(builds, key=int, reverse=True)

        return []

    @staticmethod
    async def get_build_metadata(
        job_name: str,
        build_id: str,
        gcs_base_url: Optional[str] = None,
        org_repo: Optional[str] = None,
        pr_number: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get build metadata from started.json file.

        Args:
            job_name: The name of the job
            build_id: The build ID
            gcs_base_url: Optional GCS base URL (defaults to GCS_URL)
            org_repo: Optional org_repo for PR builds (e.g., "redhat-developer_rhdh")
            pr_number: Optional PR number for PR builds

        Returns:
            Metadata dictionary or None if not found
        """
        base_url = gcs_base_url or GCS_URL

        # Use PR path structure if org_repo and pr_number are provided
        if org_repo and pr_number:
            metadata_url = f"{base_url}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/started.json"
        else:
            metadata_url = f"{base_url}/logs/{job_name}/{build_id}/started.json"

        result = await make_request(metadata_url)
        if result and "error" not in result:
            # Convert timestamp to ISO format if present
            if "timestamp" in result:
                result["timestamp_iso"] = GCSService._convert_timestamp(
                    result["timestamp"]
                )
            return result

        return None

    @staticmethod
    async def get_build_finished_metadata(
        job_name: str,
        build_id: str,
        gcs_base_url: Optional[str] = None,
        org_repo: Optional[str] = None,
        pr_number: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get build finished metadata from finished.json file.

        Args:
            job_name: The name of the job
            build_id: The build ID
            gcs_base_url: Optional GCS base URL (defaults to GCS_URL)
            org_repo: Optional org_repo for PR builds (e.g., "redhat-developer_rhdh")
            pr_number: Optional PR number for PR builds

        Returns:
            Metadata dictionary or None if not found
        """
        base_url = gcs_base_url or GCS_URL

        # Use PR path structure if org_repo and pr_number are provided
        if org_repo and pr_number:
            metadata_url = f"{base_url}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/finished.json"
        else:
            metadata_url = f"{base_url}/logs/{job_name}/{build_id}/finished.json"

        result = await make_request(metadata_url)
        if result and "error" not in result:
            # Convert timestamp to ISO format if present
            if "timestamp" in result:
                result["timestamp_iso"] = GCSService._convert_timestamp(
                    result["timestamp"]
                )
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

    @staticmethod
    async def get_step_directories(
        artifacts_url: str, job_name: str
    ) -> List[Dict[str, str]]:
        """Get all step directories from an artifacts directory.

        Structure is: <build-id>/artifacts/<configured-job-name>/<step-directory>
        This applies to both PR and periodic jobs.

        Args:
            artifacts_url: URL to the artifacts directory (should already include /artifacts)
            job_name: Name of the Job

        Returns:
            List of dictionaries containing step name and URL
        """
        html_content = await make_request_text(artifacts_url, timeout=DEFAULT_TIMEOUT)
        if not html_content:
            return []

        # Pattern to match directory links (ending with /)
        # Matches both full paths (QE GCS) and relative paths (standard GCS)
        # Captures the directory name from the last segment before the trailing /
        dir_pattern = r'href="[^"]*?([^/"]+)/"'

        directories = []
        matches = re.findall(dir_pattern, html_content)

        for dir_name in matches:
            if dir_name in ("release", "build-resources"):
                continue
            # Skip parent directory links and special directories
            if dir_name in job_name:
                # Construct full URL
                dir_url = f"{artifacts_url.rstrip('/')}/{dir_name}/"
                directories.append({"name": dir_name, "url": dir_url})
                break

        if not directories:
            return []

        # check if the directory is a configured-job-name that contains steps
        # This is the standard structure for both PR and periodic jobs
        configured_job_dir = directories[0]
        subdirs_html = await make_request_text(
            configured_job_dir["url"], timeout=DEFAULT_TIMEOUT
        )

        if subdirs_html:
            # Check if this directory contains step subdirectories using the same pattern
            sub_matches = re.findall(dir_pattern, subdirs_html)

            if sub_matches:
                # This is the configured-job-name directory, get steps from here
                steps = []
                for step_name in sub_matches:
                    if step_name in [".", "..", "artifacts", "Parent Directory"]:
                        continue
                    step_url = f"{configured_job_dir['url'].rstrip('/')}/{step_name}/"
                    steps.append(
                        {
                            "name": step_name,
                            "url": step_url,
                            "configured_job_name": configured_job_dir["name"],
                        }
                    )

                if steps:
                    return steps

        # If we didn't find nested steps, return the top-level directories as steps
        # (This handles edge cases or old job structures)
        return directories

    @staticmethod
    async def parse_junit_xml(junit_url: str) -> Optional[Dict[str, Any]]:
        """Parse JUnit XML file and extract test failure information.

        Args:
            junit_url: URL to the JUnit XML file

        Returns:
            Dictionary containing parsed test results or None if failed
        """
        try:
            import xml.etree.ElementTree as ET

            content = await make_request_text(junit_url, timeout=EXTENDED_TIMEOUT)
            if not content:
                return None

            # Parse XML
            root = ET.fromstring(content)

            # Extract test suite information
            suite_name = root.get("name", "unknown")
            total_tests = int(root.get("tests", 0))
            failures = int(root.get("failures", 0))
            errors = int(root.get("errors", 0))
            skipped = int(root.get("skipped", 0))
            time_taken = float(root.get("time", 0.0))

            # Extract individual test failures
            test_failures = []
            for testcase in root.findall(".//testcase"):
                test_name = testcase.get("name", "unknown")
                classname = testcase.get("classname", "")
                test_time = float(testcase.get("time", 0.0))

                # Check for failures
                failure_elem = testcase.find("failure")
                error_elem = testcase.find("error")

                if failure_elem is not None or error_elem is not None:
                    elem = failure_elem if failure_elem is not None else error_elem
                    failure_type = elem.get("type", "unknown")
                    failure_message = elem.get("message", "")
                    failure_text = elem.text or ""

                    test_failures.append(
                        {
                            "test_name": test_name,
                            "classname": classname,
                            "failure_type": failure_type,
                            "failure_message": failure_message,
                            "failure_details": (
                                failure_text[:1000]
                                if len(failure_text) > 1000
                                else failure_text
                            ),
                            "time": test_time,
                        }
                    )

            return {
                "suite_name": suite_name,
                "total_tests": total_tests,
                "failures": failures,
                "errors": errors,
                "skipped": skipped,
                "time": time_taken,
                "test_failures": test_failures,
                "junit_url": junit_url,
            }

        except Exception as e:
            return {
                "error": f"Failed to parse JUnit XML: {str(e)}",
                "junit_url": junit_url,
            }

    @staticmethod
    async def analyze_build_log(log_url: str, max_lines: int = 100) -> Dict[str, Any]:
        """Analyze build-log.txt for error patterns and extract relevant information.

        Args:
            log_url: URL to the build-log.txt file
            max_lines: Maximum number of lines to return in excerpt

        Returns:
            Dictionary containing log analysis results
        """
        content = await make_request_text(log_url, timeout=EXTENDED_TIMEOUT)
        if not content:
            return {"error": "Could not fetch build log", "log_url": log_url}

        lines = content.split("\n")
        total_lines = len(lines)

        # Common error patterns to search for
        error_patterns = {
            "timeout": r"(?i)(timeout|timed out|deadline exceeded)",
            "oom": r"(?i)(out of memory|oom|memory limit|killed)",
            "connection": r"(?i)(connection refused|connection reset|connection timeout|dial tcp)",
            "permission": r"(?i)(permission denied|forbidden|unauthorized|403)",
            "not_found": r"(?i)(not found|404|no such file)",
            "test_failure": r"(?i)(test.*failed|failure|failed|error:)",
            "assertion": r"(?i)(assertion|expected.*got|should.*but)",
            "panic": r"(?i)(panic:|fatal error)",
            "segfault": r"(?i)(segmentation fault|sigsegv)",
        }

        # Find matching error patterns
        found_errors = {}
        error_lines = []

        for i, line in enumerate(lines):
            for pattern_name, pattern in error_patterns.items():
                if re.search(pattern, line):
                    if pattern_name not in found_errors:
                        found_errors[pattern_name] = 0
                    found_errors[pattern_name] += 1

                    # Store interesting error lines
                    if len(error_lines) < 50:  # Limit to 50 error lines
                        error_lines.append(
                            {
                                "line_number": i + 1,
                                "content": line.strip(),
                                "pattern": pattern_name,
                            }
                        )

        # Get last N lines (usually most relevant for failures)
        last_lines = lines[-max_lines:] if len(lines) > max_lines else lines

        return {
            "total_lines": total_lines,
            "error_patterns_found": found_errors,
            "error_lines": error_lines,
            "last_lines": last_lines,
            "log_url": log_url,
            "has_errors": len(found_errors) > 0,
        }
