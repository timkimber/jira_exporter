# export-jira

Python app that uses the JIRA API to export JIRA in markdown format 
that are not possible with filters or gadgets in JIRA web UI.

Heavily based on the `Ask Jira` project from mrts: https://github.com/mrts/ask-jira.git

Features:

* `export_from_jql`: prints a Markdown-compatible tree
  of epics, stories, subtasks, bugs, issues that match the given JQL query

* `list_projects`: List available JIRA projects (mainly for testing)

* `list_fields`: List available JIRA field names and IDs, useful to get the internal names used by JIRA

## Installation

1. Clone this project
1. cd into the project
1. Using venv:
    1. `virtualenv venv`
    1. `. venv/scripts/activate`
    1. `pip install --requirement=requirements.txt`
1. Using uv
    1. `uv sync`
1. EDIT `jiraconfig.py` (you can use jiraconfig-sample.py as example)
1. Call `./export-jira.py list_projects` to test your settings are working (this will print available projects)
    1. or `uv run ./export-jira.py list_projects`

JIRA server configuration is picked up from `jiraconfig.py`.

## Usage

Run the command with 

    $ ./export-jira.py <command> <command-specific parameters>

Here's the default help:

    $ ./export-jira.py
    usage: export-jira.py [-h] command

    positional arguments:
     command   the command to run, available commands:
               'export_from_jql': Prints a Markdown-compatible tree of epics,
                   stories, subtasks, bugs, issues that match the given JQL query
                   jql: the JQL query used in the command
                   -o, --output-dir: the directory to export files to (default: output)
               'list_fields': List available JIRA field names and IDs
               'list_projects': List available JIRA projects
                
    optional arguments:
      -h, --help  show this help message and exit

### `export_from_jql` arguments

    usage: export-jira.py export_from_jql [-h] [-o OUTPUT_DIR] jql

    positional arguments:
      jql                    the JQL query used in the command

    optional arguments:
      -h, --help             show this help message and exit
      -o, --output-dir       the directory to export files to (default: output)

Note: if the command is not recognised, it is assumed to be a JQL query and `export_from_jql` is used automatically. For example, `./export-jira.py 'project = PROJ'` is equivalent to `./export-jira.py export_from_jql 'project = PROJ'`.

## Examples

    # export Project PROJ
    ./export-jira.py export_from_jql 'project = PROJ and sprint in openSprints() and status = Closed' > PROJ.MD

    ./export-jira.py export_from_jql 'project = PROJ and type = Epic' > PROJ2.MD

    # export Project PROJ to a custom output directory
    ./export-jira.py export_from_jql 'project = PROJ' -o /path/to/output
