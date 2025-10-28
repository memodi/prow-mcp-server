"""Configuration constants for the MCP Prow server."""

import os
import sys

# Prow and GCS URLs
PROW_URL = "https://prow.ci.openshift.org"
GCS_URL = "https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results"
QE_GCS_URL = "https://gcsweb-qe-private-deck-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/qe-private-deck"

# HTTP client configuration
DEFAULT_TIMEOUT = 30.0
EXTENDED_TIMEOUT = 60.0

# Required environment variables
def get_default_org_repo() -> str:
    """Get default org/repo from environment. Required for server startup."""
    org_repo = os.environ.get("DEFAULT_ORG_REPO")
    if not org_repo:
        print("ERROR: DEFAULT_ORG_REPO environment variable is required", file=sys.stderr)
        print("Example: export DEFAULT_ORG_REPO=redhat-developer_rhdh", file=sys.stderr)
        sys.exit(1)
    return org_repo

def get_default_job_name() -> str:
    """Get default job name from environment. Required for server startup."""
    job_name = os.environ.get("DEFAULT_JOB_NAME")
    if not job_name:
        print("ERROR: DEFAULT_JOB_NAME environment variable is required", file=sys.stderr)
        print("Example: export DEFAULT_JOB_NAME=pull-ci-redhat-developer-rhdh-main-e2e-tests", file=sys.stderr)
        sys.exit(1)
    return job_name

# API Key configuration
def get_api_key() -> str | None:
    """Get API key from environment, returning None if not set or is placeholder."""
    api_key = os.environ.get("API_KEY")
    if api_key and api_key != "your-api-key":  # Ignore placeholder values
        return api_key
    return None

def validate_required_config() -> None:
    """Validate that all required environment variables are set."""
    # This will exit if any required variables are missing
    get_default_org_repo()
    get_default_job_name() 