"""Main entry point for the MCP Prow server."""

import os
from fastmcp import FastMCP

from .config import validate_required_config
from .tools.job_tools import register_job_tools
from .tools.log_tools import register_log_tools
from .tools.pr_tools import register_pr_tools
from .tools.diagnostic_tools import register_diagnostic_tools
from .tools.periodic_tools import register_periodic_tools


def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools."""
    # Validate required configuration before creating server
    validate_required_config()
    
    # Create FastMCP instance with name (port will be passed to run method)
    mcp = FastMCP("Prow CI MCP Server")
    
    # Register all tool categories
    register_job_tools(mcp)
    register_log_tools(mcp)
    register_pr_tools(mcp)
    register_diagnostic_tools(mcp)
    register_periodic_tools(mcp)
    
    return mcp


def main():
    """Main entry point for the server."""
    mcp = create_server()
    
    # Get configuration from environment
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    
    if transport == "sse":
        # SSE transport with host configuration (like the article)
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        print(f"Starting MCP Prow server with transport '{transport}' on {host}:{port}")
        print(f"SSE endpoint will be available at: http://{host}:{port}/sse")
        mcp.run(
            transport="sse",
            host=host,
            port=port
        )
    elif transport == "http" or transport == "streamable-http":
        # Streamable HTTP transport
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        print(f"Starting MCP Prow server with transport '{transport}' on {host}:{port}")
        print(f"HTTP endpoint will be available at: http://{host}:{port}/mcp")
        mcp.run(
            transport="http",
            host=host,
            port=port
        )
    elif transport == "stdio":
        # STDIO transport (default) - no additional output needed
        mcp.run(transport="stdio")
    else:
        # Default to stdio for unknown transports
        print(f"Unknown transport '{transport}', defaulting to stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main() 