"""Configuration constants for the MCP Prow server."""

import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prow and GCS URLs
PROW_URL = "https://prow.ci.openshift.org"
QE_PROW_URL = "https://qe-private-deck-ci.apps.ci.l2s4.p1.openshiftapps.com"
GCS_URL = (
    "https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results"
)
QE_GCS_URL = "https://gcsweb-qe-private-deck-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/qe-private-deck"

# HTTP client configuration
DEFAULT_TIMEOUT = 30.0
EXTENDED_TIMEOUT = 60.0


# Optional default environment variables
def get_default_org_repo() -> str | None:
    """Get default org/repo from environment. Optional - can be provided per request."""
    return os.environ.get("DEFAULT_ORG_REPO")


def get_default_job_name() -> str | None:
    """Get default job name from environment. Optional - can be provided per request."""
    return os.environ.get("DEFAULT_JOB_NAME")


# API Key configuration
def get_api_key() -> str | None:
    """Get API key for app.ci cluster, returning None if not set or is placeholder."""
    api_key = os.environ.get("API_KEY")
    if api_key and api_key != "your-api-key":  # Ignore placeholder values
        return api_key
    return None


def validate_required_config() -> None:
    """Validate configuration and log warnings for missing optional defaults."""
    # Check if optional defaults are set and warn if not
    org_repo = get_default_org_repo()
    job_name = get_default_job_name()

    if not org_repo:
        logger.warning(
            "DEFAULT_ORG_REPO environment variable is not set. "
            "Tools will require 'org_repo' parameter or rely on AI agent inference from user context "
            "(e.g., GitHub URLs, repository mentions)."
        )
    else:
        logger.info(f"DEFAULT_ORG_REPO set to: {org_repo}")

    if not job_name:
        logger.warning(
            "DEFAULT_JOB_NAME environment variable is not set. "
            "Tools will require 'job_name' parameter or rely on AI agent inference from user context "
            "(e.g., Prow URLs, test type keywords like 'e2e', 'unit tests')."
        )
    else:
        logger.info(f"DEFAULT_JOB_NAME set to: {job_name}")

    # Check API key status
    api_key = get_api_key()
    if not api_key:
        logger.info(
            "API_KEY not set. Access to QE private Prow jobs will be limited. "
            "Set API_KEY environment variable if you need to access private jobs."
        )
    else:
        logger.info("API_KEY is configured for authenticated requests.")
