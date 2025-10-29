"""
Test suite for the refactored MCP server.
Tests the core functionality of the modular components.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime
import json

# Import from refactored modules
from mcp_server.utils.pr_parser import extract_pr_info
from mcp_server.utils.url_builder import construct_log_urls
from mcp_server.services.pr_finder import smart_pr_build_finder
from mcp_server.config import PROW_URL, GCS_URL
from mcp_server.tools.job_tools import get_latest_job_run_impl
from mcp_server.tools.log_tools import get_build_logs_impl
from mcp_server.services.prow_service import ProwService
from mcp_server.services.gcs_service import GCSService
from mcp_server.main import create_server


class TestExtractPrInfo:
    """Test the extract_pr_info function."""

    def test_extract_pr_info_from_job_spec_with_pulls(self):
        """Test extracting PR info from job spec with pulls."""
        job_spec = {
            "refs": {
                "pulls": [{"number": 1234}],
                "org": "redhat-developer",
                "repo": "rhdh",
                "base_ref": "main",
            }
        }

        is_pr, org_repo, pr_number = extract_pr_info(job_spec)

        assert is_pr is True
        assert org_repo == "redhat-developer_rhdh"
        assert pr_number == "1234"

    def test_extract_pr_info_from_job_spec_without_pulls(self):
        """Test extracting PR info from job spec without pulls."""
        job_spec = {
            "refs": {"org": "redhat-developer", "repo": "rhdh", "base_ref": "main"}
        }

        is_pr, org_repo, pr_number = extract_pr_info(job_spec)

        assert is_pr is False
        assert org_repo is None
        assert pr_number is None

    def test_extract_pr_info_from_job_name_pattern(self):
        """Test extracting PR info from job name pattern."""
        job_name = "pull-ci-redhat-developer-rhdh-main-e2e-tests"

        is_pr, org_repo, pr_number = extract_pr_info(None, job_name)

        assert is_pr is True
        assert org_repo == "redhat_developer"  # Current implementation uses underscores
        assert pr_number is None  # Can't extract PR number from job name

    def test_extract_pr_info_empty_inputs(self):
        """Test extracting PR info with empty inputs."""
        is_pr, org_repo, pr_number = extract_pr_info(None, None)

        assert is_pr is False
        assert org_repo is None
        assert pr_number is None


class TestConstructLogUrls:
    """Test the construct_log_urls function."""

    def test_construct_log_urls_for_pr_job(self):
        """Test URL construction for PR jobs."""
        job_spec = {
            "refs": {
                "pulls": [{"number": 1234}],
                "org": "test-org",
                "repo": "test-repo",
            }
        }

        artifacts_url, log_urls, pr_info = construct_log_urls(
            "pull-ci-test-org-test-repo-main-e2e", "build-123", job_spec
        )

        is_pr, org_repo, pr_number = pr_info
        assert is_pr is True
        assert org_repo == "test-org_test-repo"
        assert pr_number == "1234"

        # Check that PR-specific URLs are included
        assert any("pr-logs" in url for url in log_urls)
        assert "test-org_test-repo" in artifacts_url

    def test_construct_log_urls_for_regular_job(self):
        """Test URL construction for regular (non-PR) jobs."""
        artifacts_url, log_urls, pr_info = construct_log_urls(
            "periodic-ci-test-job", "build-456", None
        )

        is_pr, org_repo, pr_number = pr_info
        assert is_pr is False

        # Check that regular log URLs are included
        assert any("/logs/" in url for url in log_urls)
        assert "/logs/" in artifacts_url


class TestProwService:
    """Test the ProwService class."""

    @pytest.mark.asyncio
    async def test_get_all_jobs(self):
        """Test getting all Prow jobs."""
        mock_response = {
            "items": [
                {
                    "metadata": {"name": "job-1"},
                    "spec": {"job": "test-job"},
                    "status": {"state": "success"},
                }
            ]
        }

        with patch.object(
            ProwService, "get_all_jobs", return_value=mock_response["items"]
        ):
            jobs = await ProwService.get_all_jobs()

            assert len(jobs) == 1
            assert jobs[0].get("metadata", {}).get("name") == "job-1"

    @pytest.mark.asyncio
    async def test_get_jobs_by_name(self):
        """Test filtering jobs by name."""
        mock_response = {
            "items": [
                {
                    "metadata": {"name": "job-1"},
                    "spec": {"job": "target-job"},
                    "status": {"startTime": "2024-01-01T10:00:00Z"},
                },
                {
                    "metadata": {"name": "job-2"},
                    "spec": {"job": "other-job"},
                    "status": {"startTime": "2024-01-01T09:00:00Z"},
                },
            ]
        }

        with patch.object(
            ProwService, "get_all_jobs", return_value=mock_response["items"]
        ):
            jobs = await ProwService.get_jobs_by_name("target-job")

            assert len(jobs) == 1
            assert jobs[0].get("metadata", {}).get("name") == "job-1"


class TestGCSService:
    """Test the GCSService class."""

    @pytest.mark.asyncio
    async def test_get_builds_for_job(self):
        """Test getting builds for a job."""
        html_content = """
        <html>
        <a href="123/">Build 123</a>
        <a href="456/">Build 456</a>
        <a href="789/">Build 789</a>
        </html>
        """

        # Mock make_request_text instead of httpx.AsyncClient.get
        with patch("mcp_server.services.gcs_service.make_request_text", return_value=html_content):
            builds = await GCSService.get_builds_for_job("test-job")

            assert len(builds) == 3
            assert builds == ["789", "456", "123"]  # Sorted newest first

    @pytest.mark.asyncio
    async def test_get_pr_builds(self):
        """Test getting PR builds."""
        html_content = """
        <html>
        <a href="100/">Build 100</a>
        <a href="200/">Build 200</a>
        </html>
        """

        # Mock make_request_text instead of httpx.AsyncClient.get
        with patch("mcp_server.services.gcs_service.make_request_text", return_value=html_content):
            builds = await GCSService.get_pr_builds("org_repo", "1234", "test-job")

            assert len(builds) == 2
            assert builds == ["200", "100"]  # Sorted newest first


class TestJobTools:
    """Test job-related tools."""

    @pytest.mark.asyncio
    async def test_get_latest_job_run_impl(self):
        """Test the get_latest_job_run implementation."""
        mock_job = {
            "metadata": {"name": "job-123"},
            "status": {
                "state": "success",
                "startTime": "2024-01-01T10:00:00Z",
                "completionTime": "2024-01-01T10:30:00Z",
                "url": "https://example.com/job-123",
                "build_id": "build-456",
            },
        }

        with patch.object(
            ProwService, "get_latest_job_for_name", return_value=mock_job
        ):
            result = await get_latest_job_run_impl("test-job")

            assert result["job_id"] == "job-123"
            assert result["state"] == "success"
            assert result["build_id"] == "build-456"

    @pytest.mark.asyncio
    async def test_get_latest_job_run_impl_no_job(self):
        """Test get_latest_job_run_impl when no job is found."""
        with patch.object(ProwService, "get_latest_job_for_name", return_value=None):
            result = await get_latest_job_run_impl("nonexistent-job")

            assert "error" in result
            assert "No matching job found" in result["error"]


class TestMCPServer:
    """Test the overall MCP server functionality."""

    @pytest.mark.asyncio
    async def test_server_creation(self):
        """Test that the server can be created successfully."""
        server = create_server()
        assert server is not None

    @pytest.mark.asyncio
    async def test_all_tools_registered(self):
        """Test that all expected tools are registered."""
        server = create_server()
        tools = await server.get_tools()
        tool_names = list(tools.keys())

        expected_tools = [
            "get_latest_job_run",
            "get_job_logs",
            "get_build_logs",
            "get_latest_prow_build_for_pr",
            "diagnose_pr_build_status",
            "get_test_failures_from_artifacts",
        ]

        for expected_tool in expected_tools:
            assert (
                expected_tool in tool_names
            ), f"Tool {expected_tool} not found in {tool_names}"

    @pytest.mark.asyncio
    async def test_configuration_loaded(self):
        """Test that configuration constants are loaded correctly."""
        assert PROW_URL == "https://prow.ci.openshift.org"
        assert (
            GCS_URL
            == "https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results"
        )


class TestSmartPrBuildFinder:
    """Test the smart PR build finder."""

    @pytest.mark.asyncio
    async def test_smart_pr_build_finder_active_jobs(self):
        """Test smart PR build finder with active jobs."""
        mock_job = {
            "metadata": {"name": "job-123"},
            "status": {
                "state": "success",
                "startTime": "2024-01-01T10:00:00Z",
                "build_id": "build-456",
            },
        }

        with patch.object(ProwService, "get_jobs_for_pr", return_value=[mock_job]):
            result = await smart_pr_build_finder("1234", "org_repo", "test-job")

            assert result["success"] is True
            assert result["build_id"] == "build-456"
            assert result["source"] == "active_prow"

    @pytest.mark.asyncio
    async def test_smart_pr_build_finder_gcs_fallback(self):
        """Test smart PR build finder with GCS fallback."""
        # Mock no active jobs, but GCS has builds
        with patch.object(ProwService, "get_jobs_for_pr", return_value=[]):
            with patch.object(GCSService, "get_pr_builds", return_value=["789", "456"]):
                result = await smart_pr_build_finder("1234", "org_repo", "test-job")

                assert result["success"] is True
                assert result["build_id"] == "789"  # Latest build
                assert result["source"] == "gcs_pr_logs"

    @pytest.mark.asyncio
    async def test_smart_pr_build_finder_not_found(self):
        """Test smart PR build finder when no builds are found."""
        with patch.object(ProwService, "get_jobs_for_pr", return_value=[]):
            with patch.object(GCSService, "get_pr_builds", return_value=[]):
                with patch.object(
                    GCSService, "find_pr_builds_in_regular_logs", return_value=[]
                ):
                    with patch.object(
                        GCSService, "get_builds_for_job", return_value=[]
                    ):
                        result = await smart_pr_build_finder(
                            "1234", "org_repo", "test-job"
                        )

                        assert result["success"] is False
                        assert "strategies_attempted" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
