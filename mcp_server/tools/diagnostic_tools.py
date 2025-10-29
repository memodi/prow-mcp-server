"""Diagnostic tools for comprehensive analysis of Prow jobs and failures."""

import asyncio
import json
import logging
import re
import httpx
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from fastmcp import FastMCP
from dateutil.parser import parse as parse_date

from ..config import (
    get_default_org_repo,
    get_default_job_name,
    GCS_URL,
    QE_GCS_URL,
    DEFAULT_TIMEOUT,
    EXTENDED_TIMEOUT,
)
from ..services.prow_service import ProwService
from ..services.gcs_service import GCSService
from ..services.periodic_service import PeriodicService
from ..utils.http_client import make_request_text
from ..models.types import TestFailure
from rapidfuzz import fuzz


def register_diagnostic_tools(mcp: FastMCP) -> None:
    """Register diagnostic tools with the MCP server."""

    @mcp.tool()
    def diagnose_pr_failures(
        pr_number: str, org_repo: Optional[str] = None, job_name: Optional[str] = None
    ) -> str:
        """
        Comprehensive diagnostic analysis of PR failures across multiple job runs.

        Args:
            pr_number: The GitHub PR number to analyze
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Parse from GitHub PR URLs (https://github.com/{org}/{repo}/pull/{num}),
                     extract from user context like "in the {org}/{repo} repository", or use repository
                     mentioned earlier in the conversation. Convert org/repo to org_repo format (use underscore).
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Extract from Prow URLs, identify from test type mentions in user's question
                     (e.g., "e2e failures" -> look for jobs with "e2e"), or use job name from previous messages.

        Returns:
            JSON string with comprehensive failure analysis including patterns, trends, and recommendations

        Example Usage:
            - User: "Diagnose failures in PR 500" -> pr_number="500", use defaults
            - User: "Why is https://github.com/openshift/console/pull/123 failing?" -> pr_number="123", org_repo="openshift_console"
            - User: "Analyze test failures in PR 789 for openshift-installer" -> pr_number="789", org_repo="openshift_installer"
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return json.dumps(
                    {
                        "success": False,
                        "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable.",
                    }
                )
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return json.dumps(
                    {
                        "success": False,
                        "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable.",
                    }
                )

        try:
            # This is a placeholder for actual implementation
            # In a real implementation, this would analyze PR failure patterns
            result = {
                "success": True,
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name,
                "analysis": {},
                "note": "This tool needs implementation - placeholder for PR failure diagnosis",
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to diagnose PR failures: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name,
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    async def diagnose_pr_build_status(
        pr_number: str, org_repo: Optional[str] = None, job_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Advanced diagnostic tool that checks multiple sources for PR build status.
        Provides comprehensive information about job accessibility and troubleshooting guidance.

        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Extract from GitHub URLs (convert org/repo to org_repo with underscore),
                     parse from phrases like "for the {org}/{repo} project", or maintain repository context
                     from earlier in conversation. Common patterns: github.com/openshift/console -> openshift_console
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Extract from Prow job URLs, look for job names in earlier messages,
                     or infer from test suite mentions (e.g., "e2e builds", "integration tests").

        Returns:
            Comprehensive diagnostic information including:
            - Active job status
            - GCS storage availability
            - Build history
            - Troubleshooting recommendations

        Example Usage:
            - User: "Check build status for PR 3191" -> pr_number="3191", use defaults
            - User: "Diagnose https://github.com/redhat-developer/rhdh/pull/100" -> pr_number="100", org_repo="redhat-developer_rhdh"
            - User: "What's wrong with PR 200 e2e tests in openshift/api?" -> pr_number="200", org_repo="openshift_api", infer job with "e2e"
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return {
                    "success": False,
                    "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable.",
                }
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return {
                    "success": False,
                    "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable.",
                }

        diagnosis = {
            "pr_number": pr_number,
            "org_repo": org_repo,
            "job_name": job_name,
            "timestamp": "2025-01-27T00:00:00Z",  # Current timestamp when diagnosis runs
            "checks": {},
            "recommendations": [],
            "build_info": {},
        }

        # Check 1: Active Prow Jobs
        try:
            all_jobs = await ProwService.get_all_jobs()

            if all_jobs:
                # Find all jobs for this job name
                matching_jobs = [
                    job
                    for job in all_jobs
                    if job.get("spec", {}).get("job") == job_name
                ]

                # Find PR-specific jobs
                pr_jobs = []
                for job in matching_jobs:
                    refs = job.get("spec", {}).get("refs", {})
                    pulls = refs.get("pulls", [])
                    for pull in pulls:
                        if str(pull.get("number", "")) == pr_number:
                            pr_jobs.append(job)
                            break

                diagnosis["checks"]["active_prow"] = {
                    "status": "accessible",
                    "total_jobs_for_name": len(matching_jobs),
                    "total_pr_jobs": len(pr_jobs),
                    "pr_jobs_details": [
                        {
                            "job_id": job["metadata"]["name"],
                            "state": job.get("status", {}).get("state"),
                            "start_time": job.get("status", {}).get("startTime"),
                            "completion_time": job.get("status", {}).get(
                                "completionTime"
                            ),
                            "build_id": job.get("status", {}).get("build_id"),
                        }
                        for job in pr_jobs[:5]  # Limit to 5 most recent
                    ],
                }

                if pr_jobs:
                    diagnosis["build_info"]["active_jobs_found"] = True
                    latest_job = sorted(
                        pr_jobs,
                        key=lambda j: parse_date(j["status"]["startTime"]),
                        reverse=True,
                    )[0]
                    diagnosis["build_info"]["latest_active"] = {
                        "job_id": latest_job["metadata"]["name"],
                        "build_id": latest_job.get("status", {}).get("build_id"),
                        "state": latest_job.get("status", {}).get("state"),
                    }
                else:
                    diagnosis["recommendations"].append(
                        "No active Prow jobs found for this PR. The build may have completed and been archived."
                    )

            else:
                diagnosis["checks"]["active_prow"] = {
                    "status": "inaccessible",
                    "error": "Could not fetch Prow jobs",
                }
                diagnosis["recommendations"].append(
                    "Prow API is not accessible. Check network connectivity."
                )

        except Exception as e:
            diagnosis["checks"]["active_prow"] = {"status": "error", "error": str(e)}

        # Check 2: GCS PR Logs Structure
        try:
            builds = await GCSService.get_pr_builds(org_repo, pr_number, job_name)

            if builds:
                diagnosis["checks"]["gcs_pr_logs"] = {
                    "status": "accessible",
                    "url": f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}",
                    "builds_found": len(builds),
                    "builds": builds[:10],  # Limit to 10 most recent
                }

                diagnosis["build_info"]["gcs_pr_builds_found"] = True
                diagnosis["build_info"]["latest_gcs_pr_build"] = builds[0]
            else:
                diagnosis["checks"]["gcs_pr_logs"] = {
                    "status": "not_found",
                    "url": f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}",
                    "message": "PR logs directory does not exist or contains no builds",
                }
                diagnosis["recommendations"].append(
                    "PR logs directory not found. This could mean the PR is very new, very old, or hasn't had CI runs."
                )

        except Exception as e:
            diagnosis["checks"]["gcs_pr_logs"] = {"status": "error", "error": str(e)}

        # Check 3: GCS Regular Logs
        try:
            all_builds = await GCSService.get_builds_for_job(job_name)
            pr_builds_in_regular = await GCSService.find_pr_builds_in_regular_logs(
                job_name, pr_number, max_builds=10
            )

            diagnosis["checks"]["gcs_regular_logs"] = {
                "status": "accessible",
                "url": f"{GCS_URL}/logs/{job_name}",
                "total_builds": len(all_builds),
                "recent_builds": all_builds[:5] if all_builds else [],
                "pr_builds_found": pr_builds_in_regular,
            }

            if pr_builds_in_regular:
                diagnosis["build_info"]["gcs_regular_pr_builds"] = pr_builds_in_regular
                diagnosis["build_info"]["latest_gcs_regular_build"] = (
                    pr_builds_in_regular[0]
                )

        except Exception as e:
            diagnosis["checks"]["gcs_regular_logs"] = {
                "status": "error",
                "error": str(e),
            }

        # Generate recommendations based on findings
        if not any(
            [
                diagnosis["build_info"].get("active_jobs_found"),
                diagnosis["build_info"].get("gcs_pr_builds_found"),
                diagnosis["build_info"].get("gcs_regular_pr_builds"),
            ]
        ):
            diagnosis["recommendations"].extend(
                [
                    f"No builds found for PR {pr_number} in any location",
                    "Verify the PR number is correct",
                    "Check if CI is configured for this repository",
                    "Confirm the job name is correct for this repository",
                ]
            )

        # Determine overall status
        if diagnosis["build_info"].get("active_jobs_found"):
            diagnosis["overall_status"] = "builds_active"
            diagnosis["primary_recommendation"] = (
                "Use active job ID for most recent logs"
            )
        elif diagnosis["build_info"].get("gcs_pr_builds_found"):
            diagnosis["overall_status"] = "builds_archived_pr_structure"
            diagnosis["primary_recommendation"] = (
                "Use GCS PR logs structure for archived builds"
            )
        elif diagnosis["build_info"].get("gcs_regular_pr_builds"):
            diagnosis["overall_status"] = "builds_archived_regular_structure"
            diagnosis["primary_recommendation"] = (
                "Use GCS regular logs structure with metadata scanning"
            )
        else:
            diagnosis["overall_status"] = "no_builds_found"
            diagnosis["primary_recommendation"] = "Verify PR exists and has CI runs"

        return diagnosis

    @mcp.tool()
    async def get_test_failures_from_artifacts(
        pr_number: str, org_repo: Optional[str] = None, job_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract test failure information from artifacts when main logs are sanitized.
        This tool looks for JUnit XML, test reports, and other structured data.

        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Parse from GitHub PR URLs (https://github.com/{org}/{repo}/pull/{num}),
                     convert slash to underscore (github.com/openshift/api -> openshift_api), or extract from
                     phrases like "for the {org}/{repo} project" or repository context from earlier messages.
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Extract from Prow job URLs in user messages, identify from test type
                     keywords (e.g., "e2e artifacts", "unit test failures"), or use job context from conversation.

        Returns:
            Dictionary containing extracted test failure information from artifacts

        Example Usage:
            - User: "Get test failures from artifacts for PR 3191" -> pr_number="3191", use defaults
            - User: "Extract junit results from https://github.com/openshift/console/pull/500" -> pr_number="500", org_repo="openshift_console"
            - User: "Show me test artifacts for PR 100 e2e job in redhat-developer/rhdh" -> pr_number="100", org_repo="redhat-developer_rhdh", infer job with "e2e"
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return {
                    "success": False,
                    "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable.",
                }
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return {
                    "success": False,
                    "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable.",
                }

        try:
            # First, get the build info using our internal logic
            # Strategy 1: Check active Prow jobs first
            pr_jobs = await ProwService.get_jobs_for_pr(job_name, pr_number)
            build_info = None

            if pr_jobs:
                latest_job = pr_jobs[0]  # Already sorted by start time
                build_id = latest_job.get("status", {}).get("build_id")

                if build_id:
                    build_info = {
                        "build_id": build_id,
                        "job_name": job_name,
                        "source": "active_prow",
                    }

            # Strategy 2: Try GCS PR logs if no active jobs
            if not build_info:
                builds = await GCSService.get_pr_builds(org_repo, pr_number, job_name)
                if builds:
                    build_info = {
                        "build_id": builds[0],
                        "job_name": job_name,
                        "source": "gcs_pr_logs",
                    }

            if not build_info:
                return {"error": "Could not find build info", "pr_number": pr_number}

            build_id = build_info["build_id"]
            artifacts_base = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/artifacts"

            results = {
                "pr_number": pr_number,
                "build_id": build_id,
                "job_status": (
                    build_info.get("job_status", "unknown") if build_info else "unknown"
                ),
                "source": (
                    build_info.get("source", "unknown") if build_info else "unknown"
                ),
                "test_failures": [],
                "junit_results": None,
                "error_summary": None,
                "artifacts_checked": [],
            }

            async with httpx.AsyncClient(timeout=EXTENDED_TIMEOUT) as client:

                # 1. Check JUnit XML files for structured test results
                junit_urls = [
                    f"{artifacts_base}/junit_operator.xml",
                    f"{artifacts_base}/junit.xml",
                    f"{artifacts_base}/test-results.xml",
                    f"{artifacts_base}/e2e-tests/junit.xml",
                ]

                for junit_url in junit_urls:
                    try:
                        response = await client.get(junit_url)
                        if response.status_code == 200:
                            results["artifacts_checked"].append(f"✅ {junit_url}")
                            junit_content = response.text

                            # Parse basic JUnit information
                            if (
                                "<testcase" in junit_content
                                and "failure" in junit_content
                            ):
                                # Extract test suite info
                                suite_match = re.search(
                                    r'<testsuite[^>]*name="([^"]*)"[^>]*tests="([^"]*)"[^>]*failures="([^"]*)"',
                                    junit_content,
                                )
                                if suite_match:
                                    results["junit_results"] = {
                                        "suite_name": suite_match.group(1),
                                        "total_tests": suite_match.group(2),
                                        "failures": suite_match.group(3),
                                        "source_url": junit_url,
                                    }

                                # Extract failure messages
                                failure_pattern = r'<testcase[^>]*name="([^"]*)"[^>]*>.*?<failure[^>]*message="([^"]*)"[^>]*>(.*?)</failure>'
                                failures = re.findall(
                                    failure_pattern, junit_content, re.DOTALL
                                )

                                for test_name, failure_msg, failure_details in failures:
                                    # Decode HTML entities
                                    failure_msg = (
                                        failure_msg.replace("&#34;", '"')
                                        .replace("&#xA;", "\n")
                                        .replace("&amp;", "&")
                                    )
                                    failure_details = (
                                        failure_details.replace("&#34;", '"')
                                        .replace("&#xA;", "\n")
                                        .replace("&amp;", "&")
                                    )

                                    results["test_failures"].append(
                                        {
                                            "test_name": test_name,
                                            "failure_message": failure_msg,
                                            "failure_details": (
                                                failure_details[:1000] + "..."
                                                if len(failure_details) > 1000
                                                else failure_details
                                            ),
                                        }
                                    )

                            results["junit_content"] = (
                                junit_content[:2000] + "..."
                                if len(junit_content) > 2000
                                else junit_content
                            )
                            break  # Found a valid JUnit file

                    except Exception as e:
                        results["artifacts_checked"].append(f"❌ {junit_url}: {str(e)}")
                        continue

                # 2. Check for test report files
                report_urls = [
                    f"{artifacts_base}/test-results/",
                    f"{artifacts_base}/e2e-tests/test-results/",
                    f"{artifacts_base}/playwright-report/",
                    f"{artifacts_base}/reports/",
                ]

                for report_url in report_urls:
                    try:
                        response = await client.get(report_url)
                        if response.status_code == 200:
                            results["artifacts_checked"].append(
                                f"✅ {report_url} (directory)"
                            )
                            # Look for specific test result files in the directory listing
                            html_content = response.text

                            # Look for common test result file patterns
                            file_patterns = [
                                r'<a href="([^"]*\.json)"',
                                r'<a href="([^"]*test[^"]*\.txt)"',
                                r'<a href="([^"]*result[^"]*\.xml)"',
                            ]

                            for pattern in file_patterns:
                                matches = re.findall(
                                    pattern, html_content, re.IGNORECASE
                                )
                                for match in matches[
                                    :3
                                ]:  # Limit to 3 files per directory
                                    file_url = f"{report_url.rstrip('/')}/{match}"
                                    try:
                                        file_response = await client.get(file_url)
                                        if file_response.status_code == 200:
                                            results["artifacts_checked"].append(
                                                f"✅ {file_url}"
                                            )
                                            # Add file content if it looks like test results
                                            if (
                                                match.endswith(".json")
                                                and "test" in match.lower()
                                            ):
                                                try:
                                                    json_data = file_response.json()
                                                    if (
                                                        "failures"
                                                        in str(json_data).lower()
                                                    ):
                                                        results[
                                                            "additional_test_data"
                                                        ] = {
                                                            "source": file_url,
                                                            "data": json_data,
                                                        }
                                                except:
                                                    pass
                                    except Exception:
                                        results["artifacts_checked"].append(
                                            f"❌ {file_url}"
                                        )
                    except Exception as e:
                        results["artifacts_checked"].append(
                            f"❌ {report_url}: {str(e)}"
                        )

                # 3. Generate error summary from available data
                if results["test_failures"]:
                    results["error_summary"] = {
                        "total_failures": len(results["test_failures"]),
                        "main_failure_reason": (
                            results["test_failures"][0]["failure_message"]
                            if results["test_failures"]
                            else "Unknown"
                        ),
                        "recommendation": "Check the detailed failure information in test_failures array",
                    }
                elif results["junit_results"]:
                    results["error_summary"] = {
                        "junit_failures": results["junit_results"]["failures"],
                        "junit_total": results["junit_results"]["total_tests"],
                        "recommendation": "JUnit data found but detailed failures need manual inspection",
                    }
                else:
                    results["error_summary"] = {
                        "status": "No structured test failure data found",
                        "recommendation": "Try accessing artifacts manually or wait for logs to become available",
                    }

            return results

        except Exception as e:
            return {
                "error": f"Failed to extract test failures: {str(e)}",
                "pr_number": pr_number,
                "suggestion": "Try manually accessing the artifacts URL or wait for logs to become available",
            }

    @mcp.tool()
    async def analyze_build_step_failures(
        job_name: str,
        build_id: str,
        team_name: Optional[str] = None,
        org_repo: Optional[str] = None,
        pr_number: Optional[str] = None,
        max_log_lines: int = 100,
    ) -> Dict[str, Any]:
        """Analyze build failures step-by-step, identifying which steps failed and extracting detailed failure information.

        This tool works for both periodic jobs and PR builds:
        - For periodic jobs: IMPORTANT - Always provide team_name when mentioned by user (e.g., 'netobserv', 'sdn', 'networking'). The team_name helps filter relevant JUnit test results.
        - For PR builds: provide org_repo and pr_number

        Args:
            job_name: The job name (e.g., 'periodic-ci-openshift-...' or 'pull-ci-...')
            build_id: The build ID to analyze
            team_name: Team name for periodic jobs. REQUIRED when user specifies a team (e.g., 'sdn team', 'netobserv team'). Used to filter JUnit XML results and identify relevant test failures.
            org_repo: Organization/repository for PR builds (e.g., 'redhat-developer_rhdh')
            pr_number: PR number for PR builds
            max_log_lines: Maximum number of log lines to include in excerpts (default: 100)

        Returns:
            Dictionary containing step-by-step failure analysis with JUnit test results and log analysis
        """
        try:
            # Determine job type and construct appropriate URLs
            is_pr_build = bool(org_repo and pr_number)

            if is_pr_build:
                # PR build
                gcs_base_url = GCS_URL
                artifacts_base = f"{gcs_base_url}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/artifacts"
                build_base = f"{gcs_base_url}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}"
                job_type = "PR build"
            else:
                job_type = "Periodic build"
                # Periodic build
                if not team_name:
                    team_name = PeriodicService.get_team_for_job(job_name)

            finished_data = await GCSService.get_build_finished_metadata(
                job_name, build_id, QE_GCS_URL, org_repo, pr_number
            )

            if not finished_data:
                finished_data = await GCSService.get_build_finished_metadata(
                    job_name, build_id, GCS_URL, org_repo, pr_number
                )
                if not finished_data:
                    return {
                        "success": False,
                        "error": f"Could not determine the job artifacts after trying both GCS instances {QE_GCS_URL} and {GCS_URL}",
                    }
                else:
                    gcs_base_url = GCS_URL
            else:
                gcs_base_url = QE_GCS_URL

            if is_pr_build:
                build_base = f"{gcs_base_url}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/"
                artifacts_base = f"{build_base}/artifacts"
            else:
                build_base = f"{gcs_base_url}/logs/{job_name}/{build_id}"
                artifacts_base = f"{build_base}/artifacts"

            overall_status = "unknown"
            if finished_data:
                overall_status = finished_data.get("result", "unknown")

            # First, check the build's main build-log.txt to find which step failed
            build_log_url = f"{build_base}/build-log.txt"
            build_log_content = await make_request_text(
                build_log_url, timeout=EXTENDED_TIMEOUT
            )

            failed_step_name = None
            if build_log_content:
                # Look for pattern: "Step <step-name> failed after <duration>"
                step_failure_pattern = r"Step ([^\s]+) failed after"
                match = re.search(step_failure_pattern, build_log_content)
                if match:
                    failed_step_name = match.group(1)

            if not failed_step_name:
                return {
                    "success": False,
                    "error": "Could not determine which step failed from build-log.txt",
                    "build_log_url": build_log_url,
                    "note": "The build might still be running, or the failure pattern might be different",
                }

            # Map step names to actual directory names
            # Special case: openshift-e2e-test-qe-report -> openshift-extended-test
            step_directory_mapping = {
                "openshift-e2e-test-qe-report": "openshift-extended-test"
            }

            # Get all step directories
            steps = await GCSService.get_step_directories(artifacts_base, job_name)

            if not steps:
                return {
                    "success": False,
                    "error": "No step directories found in artifacts",
                    "artifacts_url": artifacts_base,
                    "note": "The build might still be running, or artifacts may not be available yet",
                }

            # Extract configured job name from first step
            configured_job_name = None
            if steps and "configured_job_name" in steps[0]:
                configured_job_name = steps[0]["configured_job_name"]

            # Find the failed step directory
            # Strategy 1: Try hardcoded mappings first
            actual_step_dir = None
            for pattern_suffix, directory_name in step_directory_mapping.items():
                if failed_step_name.endswith(pattern_suffix):
                    actual_step_dir = directory_name
                    break

            # Strategy 2: If no mapping found, try endswith matching against available directories
            failed_step = None
            if actual_step_dir:
                # Use the mapped directory name
                for step in steps:
                    if step["name"] == actual_step_dir:
                        failed_step = step
                        break
            else:
                # Try endswith matching: find a directory whose name the failed_step_name ends with
                for step in steps:
                    if failed_step_name.endswith(step["name"]):
                        failed_step = step
                        actual_step_dir = step["name"]
                        break

            if not failed_step:
                return {
                    "success": False,
                    "error": f"Failed step directory '{actual_step_dir}' not found in artifacts",
                    "failed_step_from_log": failed_step_name,
                    "mapped_directory": actual_step_dir,
                    "available_steps": [s["name"] for s in steps],
                    "artifacts_url": artifacts_base,
                }

            # Analyze only the failed step
            step_analysis = []
            failed_steps = 0
            total_test_failures = 0

            step = failed_step
            step_name = step["name"]
            step_url = step["url"]

            step_info = {
                "name": step_name,
                "url": step_url,
                "failed_step_from_log": failed_step_name,
                "junit_results": None,
                "log_analysis": None,
                "has_failures": False,
                "failure_summary": None,
            }

            if team_name:
                # Structure is: <step-name>/artifacts/junit/*.xml and <step-name>/build-log.txt
                # First, try to get JUnit XML from <step-name>/artifacts/junit/
                junit_dir_url = f"{step_url.rstrip('/')}/artifacts/junit/"
                junit_html = await make_request_text(
                    junit_dir_url, timeout=DEFAULT_TIMEOUT
                )

                if junit_html:
                    # Look for XML files in the junit directory
                    # Pattern matches full path in href, we'll extract just the filename
                    xml_pattern = r'href="[^"]*\.xml"'
                    matches = re.findall(xml_pattern, junit_html)

                    xml_files = []
                    for match in matches:
                        # Extract filename from the full path
                        # Example: href="/gcs/.../import-Network_Observability.xml" -> import-Network_Observability.xml
                        filename = match.split("/")[-1].replace('"', "")
                        xml_files.append(filename)

                    if xml_files:
                        # If multiple XML files, prefer one matching team name
                        selected_xml = None
                        # Look for XML file matching team name (e.g., netobserv.xml)
                        similarity_score = dict()
                        for xml_file in xml_files:
                            similarity_score[xml_file] = fuzz.partial_ratio(
                                team_name, xml_file.lower()
                            )

                        selected_xml = max(similarity_score, key=similarity_score.get)  # type: ignore

                        if selected_xml:
                            # Parse selected JUnit XML file
                            junit_url = f"{junit_dir_url.rstrip('/')}/{selected_xml}"
                            junit_data = await GCSService.parse_junit_xml(junit_url)

                            if junit_data and "error" not in junit_data:
                                step_info["junit_results"] = junit_data

                                # Check if there are test failures
                                if (
                                    junit_data.get("failures", 0) > 0
                                    or junit_data.get("errors", 0) > 0
                                ):
                                    step_info["has_failures"] = True
                                    failed_steps += 1
                                    total_test_failures += len(
                                        junit_data.get("test_failures", [])
                                    )

                                    # Extract failure messages from test failures
                                    failure_messages = []
                                    for test_failure in junit_data.get(
                                        "test_failures", []
                                    )[
                                        :10
                                    ]:  # Limit to first 10
                                        failure_messages.append(
                                            {
                                                "test_name": test_failure.get(
                                                    "test_name"
                                                ),
                                                "message": test_failure.get(
                                                    "failure_message"
                                                ),
                                                "details": test_failure.get(
                                                    "failure_details", ""
                                                )[
                                                    :500
                                                ],  # Truncate details
                                            }
                                        )

                                    step_info["failure_summary"] = {
                                        "type": "test_failures",
                                        "failed_tests": len(
                                            junit_data.get("test_failures", [])
                                        ),
                                        "total_tests": junit_data.get("total_tests", 0),
                                        "suite": junit_data.get(
                                            "suite_name", "unknown"
                                        ),
                                        "failure_messages": failure_messages,
                                    }

            # Only check build-log.txt if JUnit XML is missing
            if not step_info.get("junit_results", None):
                log_url = f"{step_url.rstrip('/')}/build-log.txt"
                log_data = await GCSService.analyze_build_log(log_url, max_log_lines)

                if log_data and "error" not in log_data:
                    step_info["log_analysis"] = {
                        "total_lines": log_data.get("total_lines", 0),
                        "error_patterns": log_data.get("error_patterns_found", {}),
                        "has_errors": log_data.get("has_errors", False),
                        "log_url": log_url,
                    }

                    # Mark as failed if log shows errors
                    if log_data.get("has_errors"):
                        step_info["has_failures"] = True
                        failed_steps += 1

                        # Determine most likely failure type from error patterns
                        error_patterns = log_data.get("error_patterns_found", {})
                        if error_patterns:
                            most_common = max(
                                error_patterns.items(), key=lambda x: x[1]
                            )

                            # Extract failure messages from error lines
                            failure_messages = []
                            for error_line in log_data.get("error_lines", [])[
                                :10
                            ]:  # Limit to first 10
                                failure_messages.append(
                                    {
                                        "line_number": error_line.get("line_number"),
                                        "pattern": error_line.get("pattern"),
                                        "message": error_line.get("content", "")[
                                            :500
                                        ],  # Truncate long lines
                                    }
                                )

                            step_info["failure_summary"] = {
                                "type": "log_errors",
                                "primary_error_pattern": most_common[0],
                                "error_count": most_common[1],
                                "all_patterns": error_patterns,
                                "failure_messages": failure_messages,
                            }

            step_analysis.append(step_info)

            # Generate overall summary
            failure_types = {}
            for step in step_analysis:
                if step["has_failures"] and step["failure_summary"]:
                    ftype = step["failure_summary"]["type"]
                    failure_types[ftype] = failure_types.get(ftype, 0) + 1

            # Identify most likely root cause
            most_likely_cause = "Unknown"
            if failed_steps > 0:
                failed_step_names = [
                    s["name"] for s in step_analysis if s["has_failures"]
                ]
                if len(failed_step_names) == 1:
                    most_likely_cause = f"Failure in step: {failed_step_names[0]}"
                else:
                    most_likely_cause = (
                        f"Multiple step failures: {', '.join(failed_step_names[:3])}"
                    )
                    if len(failed_step_names) > 3:
                        most_likely_cause += f" and {len(failed_step_names) - 3} more"

            result = {
                "success": True,
                "job_name": job_name,
                "build_id": build_id,
                "job_type": job_type,
                "overall_status": overall_status,
                "artifacts_url": artifacts_base,
                "total_steps": len(steps),
                "failed_steps": failed_steps,
                "total_test_failures": total_test_failures,
                "steps": step_analysis,
                "summary": {
                    "failure_types": failure_types,
                    "most_likely_cause": most_likely_cause,
                    "has_test_failures": total_test_failures > 0,
                    "has_log_errors": "log_errors" in failure_types,
                },
            }

            # Add configured job name if available (for periodic jobs)
            if configured_job_name:
                result["configured_job_name"] = configured_job_name

            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze build steps: {str(e)}",
                "job_name": job_name,
                "build_id": build_id,
            }
