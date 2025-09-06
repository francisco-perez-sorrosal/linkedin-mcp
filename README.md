# LinkedIn MCP Server with Anthropic's Claude Integration

A Python-based MCP (Model Context Protocol) server that gets stuff from your LinkedIn profile and integrates with the Anthropic API for potential analysis tasks.

# TL;DR Install for Claude Desktop/Code Access to the LinkedIn profile

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

- **Job Search URL Generation**: Create properly formatted LinkedIn job search URLs with location, distance, and query parameters
- **Job ID Retrieval**: Extract job IDs from LinkedIn search pages with pagination support
- **Job Metadata Extraction**: Get detailed job information including title, company, description, and requirements
- **CV Adaptation**: Combined with the cv MCP Server, adapt Francisco's CV to match specific job requirements
- Built with FastMCP for high performance and with Pixi for dependency management and task running
- Source code organized in the `src/` directory
- Includes configurations for:
  - Docker (optional, for containerization)
  - Linting (Ruff, Black, iSort)
  - Formatting
  - Type checking (MyPy)

## Prerequisites

- Python 3.11+
- [Pixi](https://pixi.sh/) (for dependency management and task execution)
- uv (for building the MCP bundle)
- Docker (optional, for containerization)

## Project Structure

This project follows the `src` layout for Python packaging.

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

### Build the Python Package

Creates sdist and wheel in `dist/`:

```bash
pixi run build
```

### Docker Support (Optional)

#### Build the Docker Image

```bash
docker build -t linkedin-mcp-server .
```

#### Run the Docker Container

TODO: Rewrite this if necessary. Docker support not yet done.

## MCP Server Installation

### Local Installation with MCP

#### Init the dxt

Init dxt project with a manifest

```sh
npx @anthropic-ai/dxt init --yes
```

**Note** When creating the manifest, in the `mcp_config` section, put the full path to the python interpreter ->  `"command": "/Users/fperez/.pyenv/shims/python"`

#### Bundle Python libs and Package Project as dxt

```sh
pixi install
pixi run bundle
pixi run pack
```

The output file `linkedin-mcp-fps.dxt` is created on the `dxt-package` directory. Alternatively, download the `linkedin-mcp-fps.dxt` file from releases (TODO).

With the packaged extension:

1. Double-click the `.dxt` file to install it in Claude Desktop
2. Alternatively, drag and drop it to Claude Desktop Settings/Extensions section
3. Restart Claude Desktop (In new Claude versions it's not necessary)
4. The extension should appear in your MCP servers list

### Extension Requirements

This extension requires Python 3.11+ and includes all necessary dependencies bundled.


### Dev Local Installation for Claude Desktop/Code (without DXT)

```json
{
  "linkedin_mcp_fps": {
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

### Remote Configuration for Claude Desktop/Code

For connecting to a remote MCP server:

```json
{
  "linkedin_mcp_fps": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}
```

> **Note**: Update the host and port as needed for your deployment.

Currently I'm using `render.com` to host the MCP server. The configuration for Claude is in the `config/claude.json` file. It uses `sse` but it is deprecated now. TODO: Make streamable-https the default for remote.

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

## User Guide

### Available Tools

1. get_url_for_jobs_search: Generate LinkedIn job search URLs

2. get_new_job_ids: Get new job IDs from LinkedIn

3. get_jobs_raw_metadata: Extract detailed job information

4. adapt_cv_to_latest_job: Adapt CV to job requirements

After installing the MCP server, you can access its functionality in Claude Desktop/Code using the tools to get information about jobs in Linkedin. Combined with the functionality provided by the [MCP Server serving my CV](https://github.com/francisco-perez-sorrosal/cv/tree/mcp) 
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

## Cache

The system uses a local cache to avoid re-scraping jobs:
- Cache location: `~/.linkedin-mcp/raw_job_description_cache/`
- Format: JSONL (JSON Lines)
- Automatically managed
- In-memory cache for fast lookups
- Configurable cache keys and storage locations

## Troubleshooting

If you encounter issues:

1. **Import errors**: Ensure all required Python packages are installed
2. **WebDriver issues**: Make sure Chrome is installed for Selenium
3. **Connection errors**: Check your internet connection for LinkedIn access
4. **Permission errors**: Ensure the cache directory is writable
5. **Python path issues**: Verify the manifest.json uses the correct Python executable path

## Dev

### Requirements

- `pixi`
- `uv`

## Support

For issues and feature requests, visit: https://github.com/francisco-perez-sorrosal/linkedin-mcp

## License

This project is licensed under the MIT License. See `pyproject.toml` (See `LICENSE` file) for details.
