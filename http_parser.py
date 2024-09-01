from req_struct import HttpRequest, HttpMethod, HttpBody, HttpBodyType
from pathlib import Path
from enum import Enum
import json
import re


class ParserState(Enum):
    METADATA = 0
    HEADERS = 1
    BODY = 2


def parse_http_file(path: str) -> list[HttpRequest]:
    file = Path(path)
    assert file.exists(), f"No file [{path}] found"

    requests = []
    variables = {}

    with file.open() as o_file:
        assert o_file.readable(), f"File [{path}] not readable"

        c_req = HttpRequest("", {}, 1.1, None, HttpMethod.GET, False)
        c_state = ParserState.METADATA
        c_body = ""

        for line in o_file:

            if line[0] == "#" or line[0:1] == "//":
                continue  # Line is a comment

            elif line[0] == "@":
                assert c_state == ParserState.METADATA, \
                    "Variables must be defined prior to a request"
                variables = _populate_variables(line, variables)

            elif c_state == ParserState.METADATA:
                if line.strip() == "":
                    continue

                line = _replace_variables(line, variables)
                c_req = _populate_metadata(line, c_req)
                c_state = ParserState.HEADERS

            elif c_state == ParserState.HEADERS:
                if line.strip() == "":
                    result = _handle_headers_blank(c_req, requests, c_state)
                    c_req = result.get("request")
                    c_state = result.get("state")
                    requests = result.get("requests")
                else:
                    line = _replace_variables(line, variables)
                    c_req = _populate_headers(line, c_req)

            elif c_state == ParserState.BODY:
                if line.strip() == "":
                    c_req = _populate_body(c_body, c_req)
                    requests.append(c_req)
                    c_body = ""
                    c_state = ParserState.METADATA
                    c_req = HttpRequest("", {}, 1.1, None,
                                        HttpMethod.GET, False)
                else:
                    line = _replace_variables(line, variables)
                    c_body += line

        if c_state == ParserState.BODY:
            c_req = _populate_body(c_body, c_req)

        requests.append(c_req)

    return requests


def _populate_variables(line: str, variables: dict) -> dict:
    split = line.split("=")
    key = split[0].replace("@", "")
    value = split[1].rstrip()
    variables[key] = value
    return variables


def _replace_variables(line: str, variables: dict) -> str:
    matches = re.findall("{{[a-zA-Z0-9-_]+}}", line)

    if len(matches) > 0:
        for match in matches:
            key = match.replace("{", "")
            key = key.replace("}", "")

            value = variables.get(key)
            if value is None:
                raise Exception(f"Variable {key} not defined")

            line = line.replace(match, value)

    return line


def _populate_metadata(line: str, request: HttpRequest) -> HttpRequest:
    split = line.split(" ")
    request.method = (HttpMethod)(split[0].upper())
    request.url = split[1]
    request.version = (float)(split[2])
    return request


def _populate_headers(line: str, request: HttpRequest) -> HttpRequest:
    split = line.split(":")
    key = split[0].strip()
    value = split[1].strip()
    request.headers[key] = value
    return request


def _handle_headers_blank(request: HttpRequest, requests: list[HttpRequest],
                          state: ParserState) -> dict:
    result = {
        "state": state,
        "request": request,
        "requests": requests
    }

    method = request.method

    if method == HttpMethod.GET or method == HttpMethod.DELETE:
        result["requests"].append(request)
        result["state"] = ParserState.METADATA
        # Reset the request
        result["request"] = HttpRequest("", {}, 1.1, None,
                                        HttpMethod.GET, False)
    else:
        content_type = request.headers.get("Content-Type")
        assert content_type is not None,      \
            "POST request requires header " + \
            "Content-Type to be set"
        body_type = (HttpBodyType)(content_type.lower())
        body = HttpBody(body_type, "")
        result["request"].body = body
        result["state"] = ParserState.BODY

    return result


def _populate_body(body: str, request: HttpRequest) -> HttpRequest:
    body_type = request.body.body_type

    if body_type == HttpBodyType.textplain:
        request.body.body = body
    elif body_type == HttpBodyType.json:
        validated = json.loads(body)  # Validate json
        request.body.body = json.dumps(validated)
    elif body_type == HttpBodyType.xwwwformurlencoded:
        pass
    elif body_type == HttpBodyType.multipartformdata:
        pass

    return request
