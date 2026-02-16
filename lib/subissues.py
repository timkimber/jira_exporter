from __future__ import unicode_literals

import os
import re


_HEADING_RE = re.compile(r"^h([1-6])\.\s+(.*)$")
_CODE_RE = re.compile(r"^\{code(?::([^}]+))?\}\s*$")
_QUOTE_RE = re.compile(r"^\{quote\}\s*$")
_PANEL_RE = re.compile(r"^\{panel(?::([^}]+))?\}\s*$")


def _extract_panel_title(params):
    if not params:
        return ""
    parts = [part.strip() for part in params.split("|") if part.strip()]
    for part in parts:
        if part.startswith("title="):
            return part[len("title=") :].strip()
    return ""


def _convert_inline(text):
    if not text:
        return text

    text = re.sub(r"\{\{(.*?)\}\}", r"`\1`", text)
    text = re.sub(r"\*([^*\n]+)\*", r"**\1**", text)
    # text = re.sub(r"_([^_\n]+)_", r"*\1*", text)

    def _link_with_text(match):
        return "[{0}]({1})".format(match.group(1), match.group(2))

    text = re.sub(r"\[([^\]|]+)\|([^\]]+)\]", _link_with_text, text)

    def _link_url(match):
        value = match.group(1)
        if value.startswith("~"):
            return match.group(0)
        return "[{0}]".format(value)

    text = re.sub(r"\[([^\]|]+)\]", _link_url, text)

    text = _escape_remaining_left_brackets(text)
    return text


def _escape_remaining_left_brackets(text):
    if "[" not in text:
        return text
    result = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "[":
            result.append(char)
            index += 1
            continue

        close_index = text.find("]", index + 1)
        if close_index != -1 and close_index + 1 < length:
            if text[close_index + 1] == "(":
                result.append("[")
                index += 1
                continue

        result.append("\\[")
        index += 1
    return "".join(result)


def _table_row_to_markdown(line, header, allow_inline):
    stripped = line.strip()
    if header:
        if stripped.startswith("||"):
            stripped = stripped[2:]
        if stripped.endswith("||"):
            stripped = stripped[:-2]
        cells = [cell.strip() for cell in stripped.split("||")]
    else:
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [cell.strip() for cell in stripped.split("|")]

    if allow_inline:
        cells = [_convert_inline(cell) for cell in cells]
    return "| " + " | ".join(cells) + " |", len(cells)


def _jira_wiki_to_markdown(text):
    if not text:
        return ""

    output = []
    in_code = False
    in_quote = False
    in_panel = False

    for line in text.splitlines():
        stripped = line.strip()

        code_match = _CODE_RE.match(stripped)
        if code_match:
            if in_code:
                output.append("```")
                in_code = False
            else:
                lang = code_match.group(1) or ""
                output.append("```" + lang.strip())
                in_code = True
            continue

        if not in_code:
            if _QUOTE_RE.match(stripped):
                in_quote = not in_quote
                continue

            panel_match = _PANEL_RE.match(stripped)
            if panel_match:
                if in_panel:
                    in_panel = False
                else:
                    title = _extract_panel_title(panel_match.group(1))
                    if title:
                        output.append("> [!NOTE] " + title)
                    else:
                        output.append("> [!NOTE]")
                    in_panel = True
                continue

        converted_lines = []

        if stripped.startswith("||"):
            header_line, cell_count = _table_row_to_markdown(line, True, not in_code)
            separator = "| " + " | ".join(["---"] * cell_count) + " |"
            converted_lines = [header_line, separator]
        elif stripped.startswith("|"):
            row_line, _cell_count = _table_row_to_markdown(line, False, not in_code)
            converted_lines = [row_line]
        elif in_code:
            converted_lines = [line]
        else:
            heading_match = _HEADING_RE.match(stripped)
            if heading_match:
                level = int(heading_match.group(1))
                converted_lines = [
                    ("#" * level) + " " + _convert_inline(heading_match.group(2))
                ]
            else:
                list_match = re.match(r"^([*#]+)\s*(.*)$", stripped)
                if list_match:
                    markers = list_match.group(1)
                    item_text = list_match.group(2)
                    indent = "  " * (len(markers) - 1)
                    marker = "- " if markers[0] == "*" else "1. "
                    converted_lines = [indent + marker + _convert_inline(item_text)]
                else:
                    converted_lines = [_convert_inline(line)]

        if in_quote or in_panel:
            prefix = "> "
            converted_lines = [
                (prefix.rstrip() if converted == "" else prefix + converted)
                for converted in converted_lines
            ]

        output.extend(converted_lines)

    if in_code:
        output.append("```")

    return "\n".join(output)


def list_epics_stories_and_tasks(jira, query):
    print("---\nSource: Jira Exporter\nJQL: " + query + "\n---\n\n")
    result = []
    export_dir = "epic_texts"
    os.makedirs(export_dir, exist_ok=True)
    epics = jira.search_issues(
        query, maxResults=500, fields="issuetype,summary,description,status"
    )
    for epic in epics:
        if epic.fields.description:
            epic_path = os.path.join(export_dir, "{0}.txt".format(epic.key))
            with open(epic_path, "w", encoding="utf-8") as handle:
                handle.write(epic.fields.description)
        result.append(_to_string(jira, epic))
        stories = jira.search_issues('"Epic Link" = %s' % epic.key)
        for story in stories:
            result.append(_to_string(jira, story, 1))
            tasks = jira.search_issues("parent = %s" % story.key)
            for task in tasks:
                result.append(_to_string(jira, task, 2))

    return "\n\n---\n\n".join(result)


def _to_string(jira, issue, level=0):
    # result = '{0}* {1.key} ({1.fields.status}): {1.fields.summary}'
    result = "# " + issue.key + ": " + _convert_inline(issue.fields.summary)
    # if (issue.fields.issuetype.name =='Sub-task' or issue.fields.issuetype.name =='Task'):
    if issue.fields.description:
        result += "\n"
        description = _jira_wiki_to_markdown(issue.fields.description)
        lines = description.splitlines()
        result += "  \n"
        result += "  \n".join(line for line in lines)

    comments = jira.comments(issue)
    if comments:
        result += "\n\n---\n\n# COMMENTS:"
        for index, comment in enumerate(comments):
            if index > 0:
                result += "\n---\n"
            result += (
                "\n"
                + "by: "
                + str(comment.author)
                + " on "
                + str(comment.created)
                + "\n"
            )
            body = _jira_wiki_to_markdown(comment.body)
            lines = body.splitlines()
            result += "  \n".join(line for line in lines) + "\n"

    return result
