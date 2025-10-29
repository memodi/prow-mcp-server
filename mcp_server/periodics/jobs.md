Use this directory to create JSON file for your team's periodic jobs configuration.

## Sample Configuration

```json
{
    "periodic_jobs": [
        "periodic-ci-example-team-job-1",
        "periodic-ci-example-team-job-2"
    ]
}
```

## Fields

- **`periodic_jobs`** (array, required): List of periodic job names for your team

## Notes

- Team name is optional when using the MCP tools - they will attempt auto-detection based on the job name
- The server automatically tries both GCS instances (qe-private-deck and test-platform-results) to locate job data
