"""Tools for PR-related operations in the MCP Prow server."""

import json
from typing import List, Dict, Any, Optional

from fastmcp import FastMCP
from ..config import get_default_org_repo, get_default_job_name, GCS_URL
from ..services.pr_finder import smart_pr_build_finder
from ..utils.pr_parser import extract_pr_info


def register_pr_tools(mcp: FastMCP) -> None:
    """Register PR-related tools with the MCP server."""

    @mcp.tool()
    def find_pr_for_prow_job(
        job_id: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> str:
        """
        Find the PR number and details associated with a specific Prow job.

        Args:
            job_id: The Prow job ID to look up
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Extract from Prow job URLs like 'https://prow.ci.openshift.org/view/gs/.../pr-logs/pull/{org}_{repo}/...'
                     or from user context mentioning specific repositories.
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Extract from Prow URLs, user's previous messages mentioning specific jobs,
                     or infer from repository context (e.g., if user mentions "e2e tests" look for matching job names).

        Returns:
            JSON string with PR details including number, title, author, and links

        Example Usage:
            - User: "What PR is job 1234567890 for?" -> Use job_id="1234567890", rely on defaults
            - User: "Find PR for job 1234567890 in openshift_installer" -> org_repo="openshift_installer"
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return json.dumps({
                    "success": False,
                    "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable."
                })
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return json.dumps({
                    "success": False,
                    "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable."
                })
            
        try:
            # For now, return a placeholder result since we don't have the actual implementation
            # In a real implementation, this would query Prow API for job details
            result = {
                "success": True,
                "job_id": job_id,
                "org_repo": org_repo,
                "job_name": job_name,
                "note": "This tool needs implementation - placeholder for PR lookup by job ID"
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to find PR details: {str(e)}",
                "job_id": job_id,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    async def get_latest_prow_build_for_pr(
        pr_number: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> str:
        """
        Find the latest Prow build ID for a specific GitHub PR number.

        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Extract from GitHub PR URLs like 'https://github.com/{org}/{repo}/pull/{number}'
                     or from user context mentioning "in the X/Y repository" or "for the Z project".
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Look for job names in user's question, infer from test type mentioned
                     (e.g., "e2e tests" might map to jobs with "e2e" in the name), or extract from Prow URLs.

        Returns:
            JSON string with build information including build_id, job_name, pr_number, etc.

        Example Usage:
            - User: "Get latest build for PR 3191" -> pr_number="3191", rely on defaults
            - User: "Show me builds for https://github.com/openshift/installer/pull/123" -> pr_number="123", org_repo="openshift_installer"
            - User: "Latest build for PR 456 in cluster-api-provider" -> pr_number="456", infer org_repo from context
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return json.dumps({
                    "success": False,
                    "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable."
                })
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return json.dumps({
                    "success": False,
                    "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable."
                })

        try:
            # Use await instead of asyncio.run() since we're already in an async context
            result = await smart_pr_build_finder(pr_number, org_repo, job_name)
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to find PR build: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    def get_recent_job_status(
        pr_number: int,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        Get recent job status for a specific PR across multiple runs.

        Args:
            pr_number: The PR number to check
            org_repo: Organization and repository in format 'org_repo' (e.g., 'redhat-developer_rhdh').
                     Falls back to DEFAULT_ORG_REPO env var if not provided.
                     AGENT INFERENCE: Parse from GitHub URLs, extract from phrases like "in the {org}/{repo} repo",
                     or maintain context from earlier conversation about specific repositories.
            job_name: Job name pattern (e.g., 'pull-ci-redhat-developer-rhdh-main-e2e-tests').
                     Falls back to DEFAULT_JOB_NAME env var if not provided.
                     AGENT INFERENCE: Extract from Prow job URLs, user's previous messages, or infer from
                     test type keywords (e.g., "unit tests", "integration tests", "e2e").
            limit: Maximum number of recent jobs to return (default: 10)
                     AGENT INFERENCE: If user says "last 5 jobs" use limit=5, "recent" use default 10

        Returns:
            JSON string with recent job statuses and trends

        Example Usage:
            - User: "Show me recent jobs for PR 100" -> pr_number=100, use defaults
            - User: "What's the status of the last 5 e2e runs for PR 200?" -> pr_number=200, limit=5, infer job_name with "e2e"
            - User: "Check PR 300 in openshift/console" -> pr_number=300, org_repo="openshift_console"
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
            if org_repo is None:
                return json.dumps({
                    "success": False,
                    "error": "org_repo is required. Either provide it as a parameter or set DEFAULT_ORG_REPO environment variable."
                })
        if job_name is None:
            job_name = get_default_job_name()
            if job_name is None:
                return json.dumps({
                    "success": False,
                    "error": "job_name is required. Either provide it as a parameter or set DEFAULT_JOB_NAME environment variable."
                })
            
        try:
            # This is a placeholder for actual implementation
            # In a real implementation, this would query Prow for recent job runs
            result = {
                "success": True,
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name,
                "recent_jobs": [],
                "note": "This tool needs implementation - placeholder for recent job status lookup"
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to get recent job status: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2) 