"""MCP tools for periodic job management and failure diagnosis."""

import json
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..config import GCS_URL, QE_GCS_URL, DEFAULT_TIMEOUT, EXTENDED_TIMEOUT
from ..services.periodic_service import PeriodicService
from ..services.gcs_service import GCSService
from ..utils.http_client import make_request, make_request_text


def register_periodic_tools(mcp: FastMCP):
    """Register periodic job-related MCP tools."""

    @mcp.tool()
    def list_periodic_teams() -> Dict[str, Any]:
        """List all teams that have periodic job configurations.

        Returns:
            Dictionary containing team names and summary information
        """
        try:
            teams = PeriodicService.list_all_teams()
            team_details = {}

            for team in teams:
                config = PeriodicService.load_team_config(team)
                if config:
                    team_details[team] = {
                        "job_count": len(config.jobs),
                    }

            return {"success": True, "total_teams": len(teams), "teams": team_details}
        except Exception as e:
            return {"success": False, "error": f"Failed to list teams: {str(e)}"}

    @mcp.tool()
    def list_periodic_jobs_for_team(team_name: str) -> Dict[str, Any]:
        """List all periodic jobs for a specific team.

        Args:
            team_name: The name of the team (e.g., 'netobserv')

        Returns:
            Dictionary containing job list and team configuration
        """
        try:
            config = PeriodicService.load_team_config(team_name)

            if not config:
                return {
                    "success": False,
                    "error": f"Team '{team_name}' not found",
                    "available_teams": PeriodicService.list_all_teams(),
                }

            return {
                "success": True,
                "team_name": team_name,
                "total_jobs": len(config.jobs),
                "jobs": config.jobs,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list jobs for team '{team_name}': {str(e)}",
            }

    @mcp.tool()
    async def get_periodic_latest_build(
        job_name: str, team_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the latest build ID for a periodic job from latest-build.txt.

        Args:
            job_name: The periodic job name
            team_name: Optional team name (auto-detected if not provided)

        Returns:
            Dictionary containing latest build information
        """
        try:
            # Auto-detect team if not provided
            if not team_name:
                team_name = PeriodicService.get_team_for_job(job_name)

            # Get latest-build.txt
            latest_build_url = f"{QE_GCS_URL}/logs/{job_name}/latest-build.txt"

            latest_build_content = await make_request_text(
                latest_build_url, timeout=DEFAULT_TIMEOUT
            )

            # try to gcs_url
            if not latest_build_content:
                latest_build_url = f"{GCS_URL}/logs/{job_name}/latest-build.txt"

                latest_build_content = await make_request_text(
                    latest_build_url, timeout=DEFAULT_TIMEOUT
                )

            if not latest_build_content:
                return {
                    "success": False,
                    "job_name": job_name,
                    "team_name": team_name,
                    "error": "latest-build.txt not found or empty",
                    "url": latest_build_url,
                }

            # Extract build ID (should be a single number)
            latest_build_id = latest_build_content.strip()

            return {
                "success": True,
                "job_name": job_name,
                "team_name": team_name,
                "latest_build_id": latest_build_id,
                "build_url": latest_build_url,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get latest build: {str(e)}",
                "job_name": job_name,
            }

    @mcp.tool()
    async def get_periodic_job_builds(
        job_name: str, team_name: Optional[str] = None, max_builds: int = 10
    ) -> Dict[str, Any]:
        """Get recent builds for a periodic job.

        Args:
            job_name: The periodic job name
            team_name: Optional team name (auto-detected if not provided)
            max_builds: Maximum number of builds to return (default: 10)

        Returns:
            Dictionary containing build information
        """
        try:
            # Auto-detect team if not provided
            if not team_name:
                team_name = PeriodicService.get_team_for_job(job_name)

            # Get builds from GCS
            builds = await GCSService.get_builds_for_job(job_name, QE_GCS_URL)

            if not builds:
                # retry to GCS_URL
                builds = await GCSService.get_builds_for_job(job_name, GCS_URL)
                if not builds:
                    return {
                        "success": False,
                        "job_name": job_name,
                        "team_name": team_name,
                        "error": f"No builds found after trying both GCS instances {QE_GCS_URL} and {GCS_URL}",
                    }

            # Limit builds
            limited_builds = builds[:max_builds]

            return {
                "success": True,
                "job_name": job_name,
                "team_name": team_name,
                "total_builds_found": len(builds),
                "builds_returned": len(limited_builds),
                "builds": limited_builds,
                "latest_build": builds[0] if builds else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get builds: {str(e)}",
                "job_name": job_name,
            }

    @mcp.tool()
    async def get_periodic_build_status(
        job_name: str, build_id: str, team_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get detailed status for a specific periodic build.

        Args:
            job_name: The periodic job name
            build_id: The build ID
            team_name: Optional team name (auto-detected if not provided)

        Returns:
            Dictionary containing build status and metadata
        """
        try:
            # Auto-detect team if not provided
            if not team_name:
                team_name = PeriodicService.get_team_for_job(job_name)

            # Get build metadata
            metadata = await GCSService.get_build_metadata(
                job_name, build_id, QE_GCS_URL
            )

            if not metadata:
                metadata = await GCSService.get_build_metadata(
                    job_name, build_id, GCS_URL
                )
                if not metadata:
                    return {
                        "success": False,
                        "job_name": job_name,
                        "build_id": build_id,
                        "error": f"Build metadata not found after trying both GCS instances {QE_GCS_URL} and {GCS_URL}",
                    }
                else:
                    gcs_base_url = GCS_URL
            else:
                gcs_base_url = QE_GCS_URL

            # Get finished.json for completion status
            finished_url = f"{gcs_base_url}/logs/{job_name}/{build_id}/finished.json"
            finished_data = await make_request(finished_url)
            if finished_data and "error" in finished_data:
                finished_data = None

            result = {
                "success": True,
                "job_name": job_name,
                "build_id": build_id,
                "team_name": team_name,
                "started": metadata,
                "build_log_url": f"{gcs_base_url}/logs/{job_name}/{build_id}/build-log.txt",
                "artifacts_url": f"{gcs_base_url}/logs/{job_name}/{build_id}/artifacts",
            }

            if finished_data:
                result["finished"] = finished_data
                result["status"] = finished_data.get("result", "unknown")

                # Convert timestamp to ISO format
                if "timestamp" in finished_data:
                    from datetime import datetime, timezone as tz

                    try:
                        epoch_ts = int(finished_data["timestamp"])
                        dt = datetime.fromtimestamp(epoch_ts, tz=tz.utc)
                        result["completion_time"] = dt.isoformat()
                        result["completion_time_epoch"] = finished_data["timestamp"]
                    except (ValueError, TypeError):
                        result["completion_time"] = finished_data.get("timestamp")

            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get build status: {str(e)}",
                "job_name": job_name,
                "build_id": build_id,
            }

    @mcp.tool()
    async def diagnose_periodic_failures(
        job_name: str, team_name: Optional[str] = None, num_builds: int = 5
    ) -> str:
        """Comprehensive diagnosis of periodic job failures.

        Analyzes recent builds to identify failure patterns, common errors,
        and provides recommendations.

        Args:
            job_name: The periodic job name
            team_name: Optional team name (auto-detected if not provided)
            num_builds: Number of recent builds to analyze (default: 5)

        Returns:
            JSON string with comprehensive failure analysis
        """
        try:
            # Auto-detect team if not provided
            if not team_name:
                team_name = PeriodicService.get_team_for_job(job_name)

            # Get recent builds
            all_builds = await GCSService.get_builds_for_job(job_name, QE_GCS_URL)

            if not all_builds:
                all_builds = await GCSService.get_builds_for_job(job_name, GCS_URL)
                if not all_builds:
                    return json.dumps(
                        {
                            "success": False,
                            "job_name": job_name,
                            "error": f"No builds found after trying both GCS instances {QE_GCS_URL} and {GCS_URL}",
                        },
                        indent=2,
                    )
                else:
                    gcs_base_url = GCS_URL
            else:
                gcs_base_url = QE_GCS_URL

            builds_to_analyze = all_builds[:num_builds]

            analysis = {
                "success": True,
                "job_name": job_name,
                "team_name": team_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_builds_available": len(all_builds),
                "builds_analyzed": len(builds_to_analyze),
                "build_results": [],
                "summary": {
                    "total_failures": 0,
                    "total_successes": 0,
                    "total_pending": 0,
                    "failure_rate": 0.0,
                    "common_errors": [],
                },
                "recent_failures": [],
                "recommendations": [],
            }

            # Analyze each build
            error_messages = []

            for build_id in builds_to_analyze:
                build_info = {
                    "build_id": build_id,
                    "status": "unknown",
                    "url": f"{gcs_base_url}/logs/{job_name}/{build_id}",
                }

                # Get finished.json
                try:
                    finished_url = (
                        f"{gcs_base_url}/logs/{job_name}/{build_id}/finished.json"
                    )
                    finished_data = await make_request(finished_url)

                    if finished_data and "error" not in finished_data:
                        status = finished_data.get("result", "unknown")
                        build_info["status"] = status

                        # Convert timestamp to ISO format
                        if "timestamp" in finished_data:
                            try:
                                epoch_ts = int(finished_data["timestamp"])
                                dt = datetime.fromtimestamp(epoch_ts, tz=timezone.utc)
                                build_info["completion_time"] = dt.isoformat()
                                build_info["completion_time_epoch"] = finished_data[
                                    "timestamp"
                                ]
                            except (ValueError, TypeError):
                                build_info["completion_time"] = finished_data[
                                    "timestamp"
                                ]

                        build_info["metadata"] = finished_data.get("metadata", {})

                        if status == "SUCCESS":
                            analysis["summary"]["total_successes"] += 1
                        elif status == "FAILURE":
                            analysis["summary"]["total_failures"] += 1

                            # Try to get error details
                            build_log_url = f"{gcs_base_url}/logs/{job_name}/{build_id}/build-log.txt"
                            log_content = await make_request_text(
                                build_log_url, timeout=EXTENDED_TIMEOUT
                            )

                            if log_content:
                                # Extract error patterns
                                error_patterns = [
                                    r"(?:ERROR|FAIL|FAILED)[:\s]+(.+)",
                                    r"(?:Test failed|Failure)[:\s]+(.+)",
                                    r"(?:panic|exception|error)[:\s]+(.+)",
                                ]

                                for pattern in error_patterns:
                                    matches = re.findall(
                                        pattern, log_content, re.IGNORECASE
                                    )
                                    error_messages.extend(
                                        matches[:3]
                                    )  # Limit per build

                                # Get last 500 chars for context
                                build_info["log_tail"] = log_content[-500:]

                            analysis["recent_failures"].append(build_info)
                        else:
                            analysis["summary"]["total_pending"] += 1
                    else:
                        analysis["summary"]["total_pending"] += 1

                except Exception as e:
                    build_info["error"] = str(e)
                    analysis["summary"]["total_pending"] += 1

                analysis["build_results"].append(build_info)

            # Calculate failure rate
            total_completed = (
                analysis["summary"]["total_failures"]
                + analysis["summary"]["total_successes"]
            )
            if total_completed > 0:
                analysis["summary"]["failure_rate"] = (
                    analysis["summary"]["total_failures"] / total_completed * 100
                )

            # Identify common errors
            if error_messages:
                from collections import Counter

                error_counter = Counter(error_messages)
                analysis["summary"]["common_errors"] = [
                    {"error": error, "occurrences": count}
                    for error, count in error_counter.most_common(5)
                ]

            # Generate recommendations
            if analysis["summary"]["failure_rate"] > 50:
                analysis["recommendations"].append(
                    "High failure rate detected. This job may need immediate attention."
                )

            if analysis["summary"]["total_failures"] > 0:
                analysis["recommendations"].append(
                    "Check the recent_failures section for specific build errors."
                )

            if error_messages:
                analysis["recommendations"].append(
                    "Review common_errors section for recurring issues."
                )
            else:
                analysis["recommendations"].append(
                    "No error patterns detected in logs. Manual log review may be needed."
                )

            # Add helpful links
            analysis["helpful_links"] = {
                "job_logs": f"{gcs_base_url}/logs/{job_name}",
                "latest_build": f"{gcs_base_url}/logs/{job_name}/{builds_to_analyze[0]}",
            }

            return json.dumps(analysis, indent=2)

        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Failed to diagnose failures: {str(e)}",
                    "job_name": job_name,
                },
                indent=2,
            )

    @mcp.tool()
    async def get_periodic_build_logs(
        job_name: str, build_id: str, team_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get build logs for a specific periodic job build.

        Args:
            job_name: The periodic job name
            build_id: The build ID
            team_name: Optional team name (auto-detected if not provided)

        Returns:
            Dictionary containing build logs and related information
        """
        try:
            # Auto-detect team if not provided
            if not team_name:
                team_name = PeriodicService.get_team_for_job(job_name)

            # Try QE GCS first
            qe_build_log_url = f"{QE_GCS_URL}/logs/{job_name}/{build_id}/build-log.txt"
            content = await make_request_text(
                qe_build_log_url, timeout=EXTENDED_TIMEOUT
            )
            if not content:
                testp_build_log_url = (
                    f"{GCS_URL}/logs/{job_name}/{build_id}/build-log.txt"
                )
                content = await make_request_text(
                    testp_build_log_url, timeout=EXTENDED_TIMEOUT
                )
                if not content:
                    return {
                        "success": False,
                        "job_name": job_name,
                        "error": f"Build logs not found after trying both GCS instances {QE_GCS_URL} and {GCS_URL}",
                    }
                else:
                    gcs_base_url = GCS_URL
                    successful_url = testp_build_log_url
            else:
                gcs_base_url = QE_GCS_URL
                successful_url = qe_build_log_url

            # Get test failures from JUnit if available
            junit_url = f"{gcs_base_url}/logs/{job_name}/{build_id}/artifacts/junit_operator.xml"
            test_failures = []

            junit_content = await make_request_text(junit_url, timeout=DEFAULT_TIMEOUT)
            if junit_content:
                # Parse failures
                failure_pattern = r'<testcase[^>]*name="([^"]*)"[^>]*>.*?<failure[^>]*message="([^"]*)"'
                failures = re.findall(failure_pattern, junit_content, re.DOTALL)

                for test_name, failure_msg in failures[:10]:  # Limit to 10
                    test_failures.append(
                        {
                            "test_name": test_name,
                            "failure_message": failure_msg.replace(
                                "&#34;", '"'
                            ).replace("&#xA;", "\n"),
                        }
                    )

            return {
                "success": True,
                "job_name": job_name,
                "build_id": build_id,
                "team_name": team_name,
                "log_url": successful_url,
                "test_failures": test_failures if test_failures else None,
                "artifacts_url": f"{gcs_base_url}/logs/{job_name}/{build_id}/artifacts",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get build logs: {str(e)}",
                "job_name": job_name,
                "build_id": build_id,
            }
