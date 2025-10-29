"""Unit tests for periodic tools and services."""

import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from mcp_server.services.periodic_service import PeriodicService, PeriodicJobConfig
from mcp_server.tools.periodic_tools import register_periodic_tools
from fastmcp import FastMCP


class TestPeriodicService:
    """Test the PeriodicService class."""

    def setup_method(self):
        """Clear cache before each test."""
        PeriodicService._configs_cache.clear()
        PeriodicService._all_jobs_cache.clear()

    def test_load_team_config_success(self):
        """Test loading a team configuration successfully."""
        mock_config = {
            "periodic_jobs": [
                "periodic-ci-openshift-netobserv-job1",
                "periodic-ci-openshift-netobserv-job2",
            ]
        }

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch(
                    "builtins.open", mock_open(read_data=json.dumps(mock_config))
                ):
                    config = PeriodicService.load_team_config("netobserv")

                    assert config is not None
                    assert config.team_name == "netobserv"
                    assert len(config.jobs) == 2
                    assert "periodic-ci-openshift-netobserv-job1" in config.jobs

    def test_load_team_config_not_found(self):
        """Test loading a non-existent team configuration."""
        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=False):
                config = PeriodicService.load_team_config("nonexistent")

                assert config is None

    def test_load_team_config_caching(self):
        """Test that team configs are cached."""
        mock_config = {"periodic_jobs": ["job1", "job2"]}

        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch(
                    "builtins.open", mock_open(read_data=json.dumps(mock_config))
                ) as mock_file:
                    # First call
                    config1 = PeriodicService.load_team_config("netobserv")
                    # Second call
                    config2 = PeriodicService.load_team_config("netobserv")

                    # File should only be opened once due to caching
                    assert mock_file.call_count == 1
                    assert config1 is config2

    def test_get_team_for_job_found(self):
        """Test finding team for a job."""
        mock_config = {"periodic_jobs": ["periodic-ci-openshift-netobserv-main-test"]}

        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch(
                    "pathlib.Path.glob", return_value=[Path("/fake/netobserv.json")]
                ):
                    with patch(
                        "builtins.open", mock_open(read_data=json.dumps(mock_config))
                    ):
                        team = PeriodicService.get_team_for_job(
                            "periodic-ci-openshift-netobserv-main-test"
                        )

                        assert team == "netobserv"

    def test_get_team_for_job_not_found(self):
        """Test finding team for a non-existent job."""
        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.glob", return_value=[]):
                    team = PeriodicService.get_team_for_job("nonexistent-job")

                    assert team is None

    def test_list_all_teams(self):
        """Test listing all teams."""
        mock_configs = {
            "netobserv": PeriodicJobConfig(team_name="netobserv", jobs=["job1"]),
            "sdn": PeriodicJobConfig(team_name="sdn", jobs=["job2"]),
            "networking": PeriodicJobConfig(team_name="networking", jobs=["job3"]),
        }

        with patch.object(
            PeriodicService, "load_all_configs", return_value=mock_configs
        ):
            teams = PeriodicService.list_all_teams()

            assert len(teams) == 3
            assert "netobserv" in teams
            assert "sdn" in teams
            assert "networking" in teams

    def test_load_all_configs(self):
        """Test loading all configurations."""
        mock_config = {"periodic_jobs": ["job1", "job2"]}
        mock_files = [Path("/fake/netobserv.json"), Path("/fake/sdn.json")]

        with patch.object(
            PeriodicService, "_get_periodics_dir", return_value=Path("/fake")
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.glob", return_value=mock_files):
                    with patch(
                        "builtins.open", mock_open(read_data=json.dumps(mock_config))
                    ):
                        configs = PeriodicService.load_all_configs()

                        assert len(configs) == 2
                        assert "netobserv" in configs
                        assert "sdn" in configs


class TestPeriodicTools:
    """Test periodic MCP tools."""

    def setup_method(self):
        """Clear cache and create MCP server before each test."""
        PeriodicService._configs_cache.clear()
        PeriodicService._all_jobs_cache.clear()
        self.mcp = FastMCP("test-server")
        register_periodic_tools(self.mcp)

    @pytest.mark.asyncio
    async def test_list_periodic_teams_success(self):
        """Test listing periodic teams successfully."""
        mock_teams = ["netobserv", "sdn", "networking"]
        mock_config = PeriodicJobConfig(
            team_name="netobserv", jobs=["job1", "job2", "job3"]
        )

        with patch.object(PeriodicService, "list_all_teams", return_value=mock_teams):
            with patch.object(
                PeriodicService, "load_team_config", return_value=mock_config
            ):
                # Get the tool function
                tools = await self.mcp.get_tools()
                list_teams_tool = tools["list_periodic_teams"]

                # Call the tool - sync function
                result = list_teams_tool.fn()

                assert result["success"] is True
                assert result["total_teams"] == 3
                assert "netobserv" in result["teams"]

    @pytest.mark.asyncio
    async def test_list_periodic_teams_error(self):
        """Test listing periodic teams with error."""
        with patch.object(
            PeriodicService, "list_all_teams", side_effect=Exception("Test error")
        ):
            tools = await self.mcp.get_tools()
            list_teams_tool = tools["list_periodic_teams"]

            result = list_teams_tool.fn()

            assert result["success"] is False
            assert "Test error" in result["error"]

    @pytest.mark.asyncio
    async def test_list_periodic_jobs_for_team_success(self):
        """Test listing jobs for a specific team."""
        mock_config = PeriodicJobConfig(
            team_name="netobserv",
            jobs=[
                "periodic-ci-openshift-netobserv-job1",
                "periodic-ci-openshift-netobserv-job2",
            ],
        )

        with patch.object(
            PeriodicService, "load_team_config", return_value=mock_config
        ):
            tools = await self.mcp.get_tools()
            list_jobs_tool = tools["list_periodic_jobs_for_team"]

            result = list_jobs_tool.fn(team_name="netobserv")

            assert result["success"] is True
            assert result["team_name"] == "netobserv"
            assert result["total_jobs"] == 2
            assert len(result["jobs"]) == 2

    @pytest.mark.asyncio
    async def test_list_periodic_jobs_for_team_not_found(self):
        """Test listing jobs for a non-existent team."""
        with patch.object(PeriodicService, "load_team_config", return_value=None):
            with patch.object(
                PeriodicService, "list_all_teams", return_value=["netobserv", "sdn"]
            ):
                tools = await self.mcp.get_tools()
                list_jobs_tool = tools["list_periodic_jobs_for_team"]

                result = list_jobs_tool.fn(team_name="nonexistent")

                assert result["success"] is False
                assert "not found" in result["error"]
                assert "available_teams" in result

    @pytest.mark.asyncio
    async def test_get_periodic_latest_build_success(self):
        """Test getting latest build ID for a periodic job."""
        mock_build_id = "1234567890"

        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.tools.periodic_tools.make_request_text",
                return_value=mock_build_id,
            ):
                tools = await self.mcp.get_tools()
                latest_build_tool = tools["get_periodic_latest_build"]

                result = await latest_build_tool.fn(
                    job_name="periodic-ci-openshift-netobserv-main-test",
                    team_name="netobserv",
                )

                assert result["success"] is True
                assert result["latest_build_id"] == mock_build_id
                assert result["team_name"] == "netobserv"

    @pytest.mark.asyncio
    async def test_get_periodic_latest_build_not_found(self):
        """Test getting latest build when file doesn't exist."""
        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.tools.periodic_tools.make_request_text", return_value=None
            ):
                tools = await self.mcp.get_tools()
                latest_build_tool = tools["get_periodic_latest_build"]

                result = await latest_build_tool.fn(
                    job_name="periodic-ci-openshift-netobserv-main-test"
                )

                assert result["success"] is False
                assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_periodic_latest_build_auto_detect_team(self):
        """Test getting latest build with auto-detected team."""
        mock_build_id = "1234567890"

        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.tools.periodic_tools.make_request_text",
                return_value=mock_build_id,
            ):
                tools = await self.mcp.get_tools()
                latest_build_tool = tools["get_periodic_latest_build"]

                result = await latest_build_tool.fn(
                    job_name="periodic-ci-openshift-netobserv-main-test"
                )

                assert result["success"] is True
                assert result["team_name"] == "netobserv"

    @pytest.mark.asyncio
    async def test_get_periodic_job_builds_success(self):
        """Test getting recent builds for a periodic job."""
        mock_builds = ["100", "99", "98", "97", "96"]

        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.services.gcs_service.GCSService.get_builds_for_job",
                return_value=mock_builds,
            ):
                tools = await self.mcp.get_tools()
                job_builds_tool = tools["get_periodic_job_builds"]

                result = await job_builds_tool.fn(
                    job_name="periodic-ci-openshift-netobserv-main-test", max_builds=5
                )

                assert result["success"] is True
                assert result["builds_returned"] == 5
                assert len(result["builds"]) == 5
                assert result["latest_build"] == "100"

    @pytest.mark.asyncio
    async def test_get_periodic_build_status_success(self):
        """Test getting build status for a periodic job."""
        mock_finished = {"timestamp": 1700000000, "result": "SUCCESS", "passed": True}
        mock_started = {"timestamp": 1699999000}

        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.services.gcs_service.GCSService.get_build_metadata",
                return_value=mock_started,
            ):
                with patch(
                    "mcp_server.tools.periodic_tools.make_request",
                    return_value=mock_finished,
                ):
                    tools = await self.mcp.get_tools()
                    build_status_tool = tools["get_periodic_build_status"]

                    result = await build_status_tool.fn(
                        job_name="periodic-ci-openshift-netobserv-main-test",
                        build_id="1234567890",
                    )

                    assert result["success"] is True
                    assert result["status"] == "SUCCESS"
                    assert "finished" in result
                    assert result["finished"]["passed"] is True

    @pytest.mark.asyncio
    async def test_get_periodic_build_status_not_found(self):
        """Test getting build status when metadata not found."""
        with patch.object(
            PeriodicService, "get_team_for_job", return_value="netobserv"
        ):
            with patch(
                "mcp_server.services.gcs_service.GCSService.get_build_finished_metadata",
                return_value=None,
            ):
                tools = await self.mcp.get_tools()
                build_status_tool = tools["get_periodic_build_status"]

                result = await build_status_tool.fn(
                    job_name="periodic-ci-openshift-netobserv-main-test",
                    build_id="1234567890",
                )

                assert result["success"] is False
                assert "not found" in result["error"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
