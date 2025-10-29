"""Service for intelligently finding PR builds using multiple strategies."""

from typing import Dict, Any, Optional
from dateutil.parser import parse as parse_date

from .prow_service import ProwService
from .gcs_service import GCSService
from ..config import get_default_org_repo, get_default_job_name


async def smart_pr_build_finder(
    pr_number: str, 
    org_repo: Optional[str] = None, 
    job_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Advanced PR build finder that uses multiple strategies and heuristics.
    This is the core logic used by get_latest_prow_build_for_pr with additional intelligence.
    
    Args:
        pr_number: The PR number to search for
        org_repo: Organization and repository in format "org_repo". Uses default if None.
        job_name: The name of the Prow job. Uses default if None.
        
    Returns:
        Dictionary with build information and metadata about the search process
    """
    # Use defaults if not provided
    if org_repo is None:
        org_repo = get_default_org_repo()
    if job_name is None:
        job_name = get_default_job_name()
        
    strategies_attempted = []
    
    # Strategy 1: Active Prow Jobs (Real-time)
    try:
        strategies_attempted.append("active_prow_jobs")
        pr_jobs = await ProwService.get_jobs_for_pr(job_name, pr_number)
        
        if pr_jobs:
            # Sort by confidence first, then by start time
            job_confidence_pairs = []
            
            for job in pr_jobs:
                confidence = "high"  # Direct PR number match always gets high confidence
                job_confidence_pairs.append({
                    "job": job,
                    "confidence": confidence,
                    "match_method": "direct_pr_number"
                })
            
            # Sort by start time (newest first)
            job_confidence_pairs.sort(
                key=lambda x: parse_date(x["job"]["status"]["startTime"]),
                reverse=True
            )
            
            best_match = job_confidence_pairs[0]["job"]
            build_id = best_match.get("status", {}).get("build_id")
            
            if build_id:
                return {
                    "success": True,
                    "build_id": build_id,
                    "job_id": best_match["metadata"]["name"],
                    "job_name": job_name,
                    "job_status": best_match.get("status", {}).get("state"),
                    "source": "active_prow",
                    "confidence": job_confidence_pairs[0]["confidence"],
                    "match_method": job_confidence_pairs[0]["match_method"],
                    "total_matches": len(job_confidence_pairs),
                    "pr_number": pr_number,
                    "org_repo": org_repo
                }
    except Exception as e:
        strategies_attempted.append(f"active_prow_jobs_failed: {str(e)}")
    
    # Strategy 2: GCS PR Logs Structure
    try:
        strategies_attempted.append("gcs_pr_logs")
        builds = await GCSService.get_pr_builds(org_repo, pr_number, job_name)
        
        if builds:
            latest_build = builds[0]  # Already sorted newest first
            return {
                "success": True,
                "build_id": latest_build,
                "job_name": job_name,
                "source": "gcs_pr_logs",
                "confidence": "high",
                "total_builds": len(builds),
                "all_builds": builds,
                "pr_number": pr_number,
                "org_repo": org_repo
            }
    except Exception as e:
        strategies_attempted.append(f"gcs_pr_logs_failed: {str(e)}")
    
    # Strategy 3: GCS Regular Logs with Metadata Scanning
    try:
        strategies_attempted.append("gcs_metadata_scan")
        pr_builds = await GCSService.find_pr_builds_in_regular_logs(job_name, pr_number, max_builds=15)
        
        if pr_builds:
            # Return the most recent build found
            latest_build = pr_builds[0] if pr_builds else None
            if latest_build:
                return {
                    "success": True,
                    "build_id": latest_build,
                    "job_name": job_name,
                    "source": "gcs_metadata_scan",
                    "confidence": "high",
                    "total_builds": len(pr_builds),
                    "all_builds": pr_builds,
                    "pr_number": pr_number,
                    "org_repo": org_repo
                }
    except Exception as e:
        strategies_attempted.append(f"gcs_metadata_scan_failed: {str(e)}")
    
    # Strategy 4: Pattern-based Build ID Search (last resort)
    try:
        strategies_attempted.append("pattern_search")
        # Sometimes PR builds follow predictable patterns
        # This is very heuristic and may give false positives
        
        all_builds = await GCSService.get_builds_for_job(job_name)
        
        if all_builds:
            # Look for builds that might correlate with PR timing
            # This is very speculative but better than nothing
            recent_builds = all_builds[:5]
            
            # Return the most recent as a low-confidence match
            if recent_builds:
                return {
                    "success": True,
                    "build_id": recent_builds[0],
                    "job_name": job_name,
                    "source": "pattern_search",
                    "confidence": "low",
                    "note": "This is a speculative match based on recent builds",
                    "warning": "This build may not actually be for the requested PR",
                    "pr_number": pr_number,
                    "org_repo": org_repo
                }
    except Exception as e:
        strategies_attempted.append(f"pattern_search_failed: {str(e)}")
    
    # All strategies failed
    return {
        "success": False,
        "error": "All search strategies failed",
        "strategies_attempted": strategies_attempted,
        "pr_number": pr_number,
        "org_repo": org_repo,
        "job_name": job_name,
        "suggestions": [
            f"Verify PR {pr_number} exists and has CI runs",
            "Check if the job name is correct",
            "The build might be very old and archived differently",
            "Try searching manually in the Prow dashboard"
        ]
    } 