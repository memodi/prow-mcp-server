# MCP Prow Server

A Model Context Protocol (MCP) server for interacting with Prow CI/CD systems, retrieving build logs, and diagnosing PR build issues.

## Features

- 🔍 **Job Management**: Get latest job runs and retrieve job logs
- 📊 **Build Analysis**: Find builds for specific PRs and analyze results  
- 🚀 **Smart Discovery**: Multi-strategy PR build finding with fallback mechanisms
- 🔧 **Diagnostics**: Comprehensive PR build status diagnosis and test failure extraction

## Architecture Diagram

<img width="1279" height="782" alt="image" src="https://github.com/user-attachments/assets/8980f0fe-c43f-4b5a-a332-040c26a554a6" />


## Available Tools

The server exposes 7 MCP tools:

1. **`get_latest_job_run`** - Get the latest job run information for a specific job name
2. **`get_job_logs`** - Retrieve logs for a specific Prow job ID
3. **`get_build_logs`** - Get logs for a specific build ID and job name
4. **`get_latest_prow_build_for_pr`** - Find the latest Prow build for a GitHub PR
5. **`get_prow_logs_from_pr`** - Get comprehensive logs for a specific PR
6. **`diagnose_pr_build_status`** - Comprehensive diagnostic tool for PR build issues
7. **`get_test_failures_from_artifacts`** - Extract test failures from build artifacts

## Example Output

Check out the [examples](https://github.com/redhat-community-ai-tools/prow-mcp-server/tree/main/examples) directory.

## Quick Start

### Installation

```bash
cd /path/to/prow-mcp-server
uv sync  # Creates venv and installs dependencies from uv.lock
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### MCP Configuration

#### Cursor IDE (stdio transport)

Add to your `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "prow": {
      "command": "uv",
      "args": ["run", "/path/to/prow-mcp-server/.venv/bin/python", "/path/to/prow-mcp-server/main.py"],
      "description": "MCP server for Prow CI/CD integration"
    }
  }
}
```

#### Web-based Integration (SSE transport)

For web applications or services that need HTTP-based communication:

```json
{
  "mcpServers": {
    "prow": {
      "url": "http://0.0.0.0:8000/sse/",
      "description": "MCP server for Prow CI/CD integration with direct SSE",
      "env": {
        "MCP_TRANSPORT": "sse"
      }
    }
  }
}
```

**SSE Endpoint**: `http://0.0.0.0:8000/sse/`

> **Note**: Make sure to start the SSE server separately with `MCP_TRANSPORT=sse uv run main.py` before using this configuration.

## Testing

Run the comprehensive test suite (18 tests):

```bash
uv run python run_tests.py           # Recommended
uv run pytest tests/ -v              # Direct pytest
```

All tests pass in under 0.25 seconds with full coverage of utilities, services, and MCP tools.

## Architecture

The server uses a modular architecture with clear separation of concerns:

```
mcp_server/
├── main.py          # Server entry point
├── config.py        # Configuration
├── models/          # Type definitions
├── utils/           # Helper functions
├── services/        # Business logic (Prow API, GCS)
└── tools/           # MCP tool implementations
```

## Smart Build Discovery

The server uses intelligent fallback strategies to find PR builds:

1. **Active Prow Jobs** (real-time) →
2. **GCS PR Logs** (archived) →
3. **GCS Regular Logs** (metadata scanning) →
4. **Pattern-based Search** (heuristic fallback)

## Container Deployment

### STDIO Transport (Default)

For standard MCP integration with Cursor IDE:

```bash
# Build
podman build -t prow-mcp:latest .

# Run
podman run -i --rm prow-mcp:latest

# MCP Config
{
  "mcpServers": {
    "prow-server": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "localhost/prow-mcp:latest"]
    }
  }
}
```

### SSE Transport

For web-based integrations and HTTP communication:

```bash
# Build SSE container
podman build -f Containerfile.sse -t prow-mcp-sse:latest .

# Run SSE container
podman run -p 8000:8000 --rm prow-mcp-sse:latest

# MCP Config
{
  "mcpServers": {
    "prow-sse": {
      "url": "http://localhost:8000/sse/",
      "description": "MCP server for Prow CI/CD integration with SSE transport",
      "env": {
        "MCP_TRANSPORT": "sse"
      }
    } 
  }
}
```

**SSE Endpoint**: `http://localhost:8000/sse/`

> **Note**: The SSE container automatically configures `MCP_TRANSPORT=sse`, `MCP_HOST=0.0.0.0`, and `MCP_PORT=8000` environment variables.

## Configuration

**Optional environment variables** (can be configured in `mcp.json` or shell):

- `DEFAULT_ORG_REPO`: Organization and repository (e.g., `redhat-developer_rhdh`). Used as default when not specified in tool calls. Agents can infer org/repo from user context (GitHub URLs, repository mentions, etc.)
- `DEFAULT_JOB_NAME`: Default Prow job name (e.g., `pull-ci-redhat-developer-rhdh-main-e2e-tests`). Used as default when not specified in tool calls. Agents can infer job names from user questions (test type mentions, Prow URLs, etc.)
- `API_KEY`: For authenticated requests to access QE private Prow jobs
- `MCP_TRANSPORT`: Transport method (`stdio` (default), `sse`, `http`)
- `MCP_HOST`: Host for sse/http transport (default: `127.0.0.1`)
- `MCP_PORT`: Port for sse/http transport (default: `8000`)

> **Note**: `DEFAULT_ORG_REPO` and `DEFAULT_JOB_NAME` are now **optional**. Tools can accept these parameters per-request, and AI agents can intelligently infer them from user context such as GitHub URLs, repository mentions, or test type keywords.

### Example `mcp.json` Configuration

#### Minimal Configuration (No Defaults)
```json
{
  "mcpServers": {
    "prow-stdio": {
      "command": "uv",
      "args": ["run", "python", "/path/to/prow-mcp-server/main.py"],
      "description": "MCP server for Prow CI/CD integration"
    }
  }
}
```

#### With Default Repository (Recommended for Single Project)
```json
{
  "mcpServers": {
    "prow-stdio": {
      "command": "uv",
      "args": ["run", "python", "/path/to/prow-mcp-server/main.py"],
      "description": "MCP server for Prow CI/CD integration",
      "env": {
        "DEFAULT_ORG_REPO": "redhat-developer_rhdh",
        "DEFAULT_JOB_NAME": "pull-ci-redhat-developer-rhdh-main-e2e-tests",
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Default settings work for most other configurations:

- **Prow URL**: `https://prow.ci.openshift.org`
- **GCS URL**: `https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results`

### Transport Methods

- **`stdio`** (default): Standard input/output transport for Cursor IDE
- **`sse`**: Server-Sent Events for web-based integration (runs HTTP server on port 8000)

## Troubleshooting

### Common Issues

1. **Import Errors**: Use `main.py` entry point
2. **Missing Tools**: Verify all tool registration functions are called
3. **Authentication**: Set `API_KEY` environment variable if needed
4. **Network Issues**: Check connectivity to Prow and GCS endpoints

### Diagnostics

Use the built-in diagnostic tool for PR-specific issues:

```bash
# Through MCP: "Diagnose why PR 3191 builds are failing"
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Add tests for new functionality
4. Run test suite: `uv run python run_tests.py`
5. Submit pull request

---

**🚀 Clean, modular, and well-tested MCP Prow Server ready for use!**
