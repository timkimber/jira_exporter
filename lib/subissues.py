from __future__ import unicode_literals

import os
import re
from datetime import datetime


_HEADING_RE = re.compile(r"^h([1-6])\.\s+(.*)$")
_CODE_RE = re.compile(r"^\{code(?::([^}]+))?\}|\{code\}\s*$")
_QUOTE_RE = re.compile(r"^\{quote\}|\{quote\}\s*$")
_PANEL_RE = re.compile(r"^\{panel(?::([^}]+))?\}\s*$")
# Regex for !image.png! or !image.png|params!  (excludes ![[...]] Obsidian syntax)
_IMAGE_RE = re.compile(r"!(?!\[\[)([^|!\n]+)(?:\|([^!\n]+))?!")

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
    text = text.replace("<", "\\<")  # escape '<' to avoid Markdown treating it as HTML

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

        # Skip Obsidian-style image links: ![[...]]
        # At first '[': check if preceded by '!' and followed by '['
        if (index >= 1 and text[index - 1] == "!"
                and index + 1 < length and text[index + 1] == "["):
            # Emit both '[' characters unescaped
            result.append("[")
            result.append("[")
            index += 2
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


# Image handling logic
def _replace_images_in_text(jira, text, issue_key, export_dir):
    if not text:
        return text

    def _download_and_replace_image(match):
        filename = match.group(1).strip()
        local_filename = f"{issue_key}_{filename}"

        # Ensure images directory exists
        images_dir = os.path.join(export_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        local_path = os.path.join(images_dir, local_filename)

        # Download if not already downloaded
        if not os.path.exists(local_path):
            try:
                # Find the attachment in the issue
                attachment = next(
                    (
                        a
                        for a in jira.issue(issue_key).fields.attachment
                        if a.filename == filename
                    ),
                    None,
                )
                if attachment:
                    with open(local_path, "wb") as f:
                        f.write(attachment.get())
                        print(f'Created: {local_path}')
            except Exception as e:
                print(f"Failed to download image {filename}: {e}")

        return f"![[images/{local_filename}]]"

    # Process line by line so we skip code blocks
    result_lines = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if _CODE_RE.search(stripped):
            in_code = not in_code
            result_lines.append(line)
        elif in_code:
            result_lines.append(line)
        else:
            result_lines.append(_IMAGE_RE.sub(_download_and_replace_image, line))
    return "\n".join(result_lines)


def _jira_wiki_to_markdown(text):

    if not text:
        return ""

    output = []
    in_code = False
    in_quote = False
    in_panel = False
    # Track ordered list counters per depth (1-based depth)
    ordered_counters = {}

    for line in text.splitlines():
        stripped = line.strip()

        code_match = _CODE_RE.search(stripped)
        if code_match:
            if in_code:
                if stripped.endswith("{code}"):
                    content_before = stripped[:-7].strip()
                    if content_before:
                        output.append(content_before)
                output.append("```")
                in_code = False
            else:
                lang = code_match.group(1) or ""
                output.append("```" + lang.strip())
                if stripped.startswith("{code"):
                    content_after = stripped[stripped.find("}") + 1 :].strip()
                    if content_after:
                        output.append(content_after)
                in_code = True
            continue

        if not in_code:
            quote_match = _QUOTE_RE.search(stripped)
            if quote_match:
                if stripped.startswith("{quote}") and stripped.endswith("{quote}"):
                    inline_quote_content = stripped[7:-7].strip()
                    output.append("> " + _convert_inline(inline_quote_content))
                elif stripped.startswith("{quote}"):
                    in_quote = not in_quote
                    content_after = stripped[7:].strip()
                    if content_after:
                        output.append("> " + _convert_inline(content_after))
                elif stripped.endswith("{quote}"):
                    content_before = stripped[:-7].strip()
                    if content_before:
                        output.append("> " + _convert_inline(content_before))
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
            elif stripped == "----":
                converted_lines = ["---"]
            else:
                list_match = re.match(r"^([*#]+)\s+(.*)$", stripped)
                if list_match:
                    markers = list_match.group(1)
                    item_text = list_match.group(2)
                    depth = len(markers)
                    indent = "    " * (depth - 1)
                    # Use the outermost (first) marker to determine list type
                    outermost = markers[0]
                    if outermost == "#":
                        # Increment counter for this depth, reset deeper levels
                        ordered_counters[depth] = ordered_counters.get(depth, 0) + 1
                        for d in list(ordered_counters.keys()):
                            if d > depth:
                                del ordered_counters[d]
                        num = ordered_counters[depth]
                        marker = f"{num}. "
                    else:
                        # Bullet list resets ordered counters at this depth and deeper
                        for d in list(ordered_counters.keys()):
                            if d >= depth:
                                del ordered_counters[d]
                        marker = "- "
                    converted_lines = [indent + marker + _convert_inline(item_text)]
                else:
                    # Reset ordered counters when leaving list context (blank or non-list line)
                    if not stripped:
                        ordered_counters.clear()
                    converted_lines = [_convert_inline(line.rstrip())]

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


def _write_issue_to_file(jira, issue, export_dir):
    content = _to_string(jira, issue, export_dir)
    # Replace brackets with parentheses in the filename
    title = _convert_inline(issue.fields.summary) or ""
    safe_title = title.replace("[", "(").replace("]", ")")
    filename = "{0} {1}.md".format(issue.key, safe_title)
    output_path = os.path.join(export_dir, filename)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"Created: {output_path}")


def _write_raw_jira_to_file(jira, issue, input_dir):
    output_path = os.path.join(input_dir, "{0}.txt".format(issue.key))
    with open(output_path, "w", encoding="utf-8") as handle:
        if issue.fields.description:
            handle.write(issue.fields.description)
        comments = jira.comments(issue)
        if comments:
            handle.write("\n\n---\n\n# COMMENTS:\n\n")
            for comment in comments:
                handle.write(
                    "by: " + str(comment.author) + " on " + str(comment.created) + "\n"
                )
                handle.write(comment.body + "\n\n")
    print(f"Created: {output_path}")


def list_epics_stories_and_tasks(jira, query, export_dir="output"):
    os.makedirs(export_dir, exist_ok=True)

    input_dir = "input"
    os.makedirs(input_dir, exist_ok=True)

    epics = jira.search_issues(
        query, maxResults=500, fields="issuetype,summary,description,status"
    )
    if len(epics) == 0:
        print(f'No jiras found for {query}')
    for epic in epics:
        _write_raw_jira_to_file(jira, epic, input_dir)
        _write_issue_to_file(jira, epic, export_dir)
        stories = jira.search_issues('"Epic Link" = %s' % epic.key)
        for story in stories:
            _write_raw_jira_to_file(jira, story, input_dir)
            _write_issue_to_file(jira, story, export_dir)
            tasks = jira.search_issues("parent = %s" % story.key)
            for task in tasks:
                _write_raw_jira_to_file(jira, task, input_dir)
                _write_issue_to_file(jira, task, export_dir)

    return ""


def _to_string(jira, issue, export_dir, level=0):
    # Build YAML frontmatter with today's date (export date)
    today = datetime.now().strftime("%Y-%m-%d")

    result = "---\nCreated: {0}\n---\n".format(today)
    result += "# User Story"

    if issue.fields.description:
        result += "\n"
        description = _replace_images_in_text(
            jira, issue.fields.description, issue.key, export_dir
        )
        description = _jira_wiki_to_markdown(description)
        result += "\n" + description + "\n"

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
            body = _replace_images_in_text(
                jira, comment.body, issue.key, export_dir
            )
            body = _jira_wiki_to_markdown(body)
            lines = body.splitlines()
            result += "\n".join(line for line in lines) + "\n"

    return result
