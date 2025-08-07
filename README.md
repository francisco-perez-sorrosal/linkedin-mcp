# LinkedIn MCP Server with Anthropic Integration

A Python-based MCP (Model Context Protocol) server that gets stuff from your LinkedIn profile and integrates with the Anthropic API for potential analysis tasks. This project follows the `src` layout for Python packaging.

<a href="https://glama.ai/mcp/servers/@francisco-perez-sorrosal/linkedin-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@francisco-perez-sorrosal/linkedin-mcp/badge" alt="LinkedIn Server MCP server" />
</a>

# TL;DR Install for Claude Desktop Access to the LinkedIn profile

```bash
# 1.a) Install the mcp server access in Claude Desktop
./install_claude_desktop_mcp.sh

# 1.b) or manually integrate this JSON snippet to the `mcpServers` section of your `claude_desktop_config.json` (e.g. `~/Library/Application\ Support/Claude/claude_desktop_config.json`)

{
  "linkedin_francisco_perez_sorrosal": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}

# 2) Restart Claude and check that the 'Add from linkedin_francisco_perez_sorrosal` option is available in the mcp servers list

# 3) Query the LinkedIn profile served from the mcp server in Claude Desktop!

e.g. TODO
```

## Features

- Serves your LinkedIn profile from the project root
- Built with FastAPI for high performance and with Pixi for dependency management and task running
- Source code organized in the `src/` directory
- Includes configurations for:
  - Docker (optional, for containerization)
  - Linting (Ruff, Black, iSort)
  - Formatting
  - Type checking (MyPy)

## Prerequisites

- Python 3.11+
- [Pixi](https://pixi.sh/) (for dependency management and task execution)
- Docker (optional, for containerization)
- Access to your LinkedIn profile

## Project Structure

```bash
.
├── .dockerignore
├── .gitignore
├── Dockerfile
├── pyproject.toml    # Python project metadata and dependencies (PEP 621)
├── README.md
├── src/
│   └── linkedin_mcp_server/
│       ├── __init__.py
│       └── main.py     # FastAPI application logic
├── tests/             # Test files (e.g., tests_main.py)
```

## Setup and Installation

1. **Clone the repository** (if applicable) or ensure you are in the project root directory.

2. **Install dependencies using Pixi**:

This command will create a virtual environment and install all necessary dependencies:

```bash
pixi install
```

## Running the Server

Pixi tasks are defined in `pyproject.toml`:

### mcps (MCP Server)

```bash
pixi run mcps --transport stdio
```

### Development Mode (with auto-reload)

```bash
# Using pixi directly
pixi run mcps --transport stdio  # or sse, streamable-http

# Alternatively, using uv directly
uv run --with "mcp[cli]" mcp run src/linkedin_mcp_server/main.py --transport streamable-http

# Go to http://127.0.0.1:10000/mcp
```

The server will start at `http://localhost:10000`. It will automatically reload if you make changes to files in the `src/` directory.

### MCP Inspection Mode

```bash
# Using pixi
DANGEROUSLY_OMIT_AUTH=true  npx @modelcontextprotocol/inspector pixi run mcps --transport stdio

# Direct execution
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector pixi run python src/linkedin_mcp_server/main.py --transport streamable-http
```

This starts the inspector for the MCP Server.

### Web scrapper

```sh
pixi run python src/linkedin_mcp_server/web_scrapper.py   
```


## Development Tasks

### Run Tests

```bash
pixi run test
```

### Lint and Check Formatting

```bash
pixi run lint
```

### Apply Formatting and Fix Lint Issues

```bash
pixi run format
```

### Build the Package

Creates sdist and wheel in `dist/`:

```bash
pixi run build
```

## Docker Support (Optional)

### Build the Docker Image

```bash
docker build -t linkedin-mcp-server .
```

### Run the Docker Container

TODO: Rewrite this if necessary. Docker support not yet done.

## MCP Server Configuration

### Local Configuration for Claude Desktop

```json
{
  "linkedin_francisco_perez_sorrosal": {
    "command": "uv",
    "args": [
      "run",
      "--with", "mcp[cli]",
      "--with", "pymupdf4llm",
      "mcp", "run",
      "src/linkedin_mcp_server/main.py",
      "--transport", "streamable-http"
    ]
  }
}
```

### Remote Configuration for Claude Desktop

For connecting to a remote MCP server:

```json
{
  "linkedin_francisco_perez_sorrosal": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}
```

> **Note**: Update the host and port as needed for your deployment.

Currently I'm using `render.com` to host the MCP server. The configuration is in the `config/claude.json` file.

Render requires `requirements.txt` to be present in the root directory. You can generate it using:

```bash
uv pip compile pyproject.toml > requirements.txt
```

Also requires `runtime.txt` to be present in the root directory with the Python version specified:

```txt
python-3.11.11
```

Remember also to set the environment variables in the render.com dashboard:

```bash
TRANSPORT=sse
PORT=1000
```

Then you can query in Claude Desktop using the `linkedin_mcp_fps` MCP server to get info from job ids. Combined with
the functionality provided by the [MCP Server serving my CV](https://github.com/francisco-perez-sorrosal/cv/tree/mcp) 
you can ask things like this:

```text
Get a list of new jobs from linkedin (2 pages) for a research engineer position in ml/ai in San Francisco, take the last job id from that list, retrieve its metadata, show its content formatted properly, and finally adapt Francisco's CV to the job's description retrieved.
```

or simply:

```text
Adapt Francisco's CV to the latest job retrieved

# or

Adapt Francisco's CV to the first two retrieved job ids
```

or, as a recruiter, get your posted LinkedIn job id and write:

```text
Adapt Francisco's CV to this job id 4122691570
```

## License

This project is licensed under the MIT License. See `pyproject.toml` (See `LICENSE` file) for details.