"""Utilities for constructing URLs for log and artifact access."""

from typing import Dict, List, Tuple, Optional
from .pr_parser import extract_pr_info
from ..config import GCS_URL


def construct_log_urls(
    job_name: str,
    build_id: str,
    job_spec: Dict | None = None,
    org_repo: Optional[str] = None,
    pr_number: Optional[str] = None
) -> Tuple[str, List[str], Tuple[bool, Optional[str], Optional[str]]]:
    """Construct possible log URLs for both PR and regular jobs.

    Args:
        job_name: The name of the Prow job
        build_id: The build ID
        job_spec: Optional job specification containing PR info
        org_repo: Optional org_repo override (e.g., "redhat-developer_rhdh")
        pr_number: Optional PR number override

    Returns:
        tuple: (artifacts_url, possible_log_urls, pr_info)
    """
    # If org_repo and pr_number are provided directly, use them
    # Otherwise, try to extract from job_spec
    if org_repo and pr_number:
        is_pr_job = True
    else:
        is_pr_job, org_repo, pr_number = extract_pr_info(job_spec or {}, job_name)
    
    possible_log_urls = []
    
    if is_pr_job and org_repo:
        # PR job - try pr-logs structure
        if pr_number:
            # We have the exact PR number
            base_path = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}"
            artifacts_url = f"{base_path}/artifacts"
            
            possible_log_urls.extend([
                f"{base_path}/build-log.txt",
                f"{artifacts_url}/build-log.txt",
                f"{base_path}/started.json",
                f"{base_path}/finished.json",
                f"{artifacts_url}/junit/build-log.txt",
                f"{artifacts_url}/logs/build-log.txt",
                f"{artifacts_url}/build-log.txt/log",
                f"{artifacts_url}/build-log.txt/output.txt"
            ])
        else:
            # PR job but no PR number - we'll need to try common patterns
            # This is a fallback when we detect it's a PR job but don't have the exact number
            artifacts_url = f"{GCS_URL}/pr-logs/pull/{org_repo}/*/{job_name}/{build_id}/artifacts"
            
            # Try some common PR numbers or patterns
            for pr_num in ["*"]:  # We'll add wildcard support or try to detect from error messages
                base_path = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_num}/{job_name}/{build_id}"
                possible_log_urls.extend([
                    f"{base_path}/build-log.txt",
                    f"{base_path}/artifacts/build-log.txt",
                ])
    
    # Always also try the regular logs structure as fallback
    base_path = f"{GCS_URL}/logs/{job_name}/{build_id}"
    regular_artifacts_url = f"{base_path}/artifacts"
    
    possible_log_urls.extend([
        f"{base_path}/build-log.txt",
        f"{regular_artifacts_url}/build-log.txt",
        f"{regular_artifacts_url}/junit/build-log.txt",
        f"{regular_artifacts_url}/logs/build-log.txt",
        f"{regular_artifacts_url}/build-log.txt/log",
        f"{regular_artifacts_url}/build-log.txt/output.txt"
    ])
    
    # Use the best artifacts URL we have
    if is_pr_job and org_repo and pr_number:
        artifacts_url = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/artifacts"
    else:
        artifacts_url = regular_artifacts_url
    
    return artifacts_url, possible_log_urls, (is_pr_job, org_repo, pr_number) 