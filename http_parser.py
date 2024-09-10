from req_struct import HttpRequest, HttpMethod, HttpBody, HttpBodyType
from pathlib import Path
from enum import Enum
import json
import re


# Extremely simple state machine
class ParserState(Enum):
    # ParserState {{{
    METADATA = 0  # [HTTP Method] [URL] [HTTP Version]
    HEADERS = 1   # [Header Key]: [Header Value]
    BODY = 2      # [Request Body]
    # }}}


def parse_http_file(path: str) -> list[HttpRequest]:
    """
    Primary function to parse an http (.http) file
    """
    # parse_http_file {{{
    assert path.split(".")[-1] == "http", "File must be of type http"

    file = Path(path)
    assert file.exists(), f"No file [{path}] found"

    requests = []   # The actual return
    variables = {}  # Used for placeholder replacement

    with file.open() as o_file:
        assert o_file.readable(), f"File [{path}] not readable"

        # Initial state for the machine
        c_req = HttpRequest("", {}, 1.1, None, HttpMethod.GET)
        c_state = ParserState.METADATA
        c_body = ""  # Body will just be a string, but will be validated

        for line in o_file:

            if line[0] == "#" or line[0:1] == "//":
                continue  # Line is a comment

            elif line[0] == "@":  # Variable definition found
                assert c_state == ParserState.METADATA, \
                    "Variables must be defined prior to a request"
                variables = _populate_variables(line, variables)

            elif c_state == ParserState.METADATA:
                if line.strip() == "":
                    continue  # Indicates multiple blank lines between requests
                if line[0] == "&":
                    name = line.replace("&", "")
                    c_req.name = name
                    continue

                line = _replace_variables(line, variables)
                c_req = _populate_metadata(line, c_req)
                c_state = ParserState.HEADERS

            elif c_state == ParserState.HEADERS:
                if line.strip() == "":
                    result = _handle_headers_blank(c_req, requests, c_state)
                    # Reset state
                    c_req = result.get("request")
                    c_state = result.get("state")
                    requests = result.get("requests")
                else:
                    line = _replace_variables(line, variables)
                    c_req = _populate_headers(line, c_req)

            elif c_state == ParserState.BODY:
                if line.strip() == "":
                    # Validation step of request body
                    c_req = _populate_body(c_body, c_req)
                    requests.append(c_req)
                    # Reset state
                    c_body = ""
                    c_state = ParserState.METADATA
                    c_req = HttpRequest("", {}, 1.1, None,
                                        HttpMethod.GET)
                else:
                    line = _replace_variables(line, variables)
                    c_body += line

        if c_state == ParserState.BODY:
            # Validation step of request body
            c_req = _populate_body(c_body, c_req)

        if c_req.url.strip() != "":
            # Subtle check to ensure misc. line, such as comment
            # is not counted as actual request
            requests.append(c_req)

    return requests
    # }}}


def _handle_headers_blank(request: HttpRequest, requests: list[HttpRequest],
                          state: ParserState) -> dict:
    """
    Handles the case when a line is blank during the HEADERS phase
    of the parsing state machine. This determines if the next block
    should be another http request or the body of the current request
    """
    # _handle_headers_blank {{{
    result = {
        "state": state,
        "request": request,
        "requests": requests
    }

    method = request.method

    if method == HttpMethod.GET or method == HttpMethod.DELETE:
        # No body necessary for this type of request, reset and continue
        result["requests"].append(request)
        result["state"] = ParserState.METADATA
        # Reset the request
        result["request"] = HttpRequest("", {}, 1.1, None,
                                        HttpMethod.GET)
    else:
        # Body is necessary for this type of request, ensure we know
        # what type of body and advance state machine
        content_type = request.headers.get("Content-Type")
        assert content_type is not None,      \
            "POST request requires header " + \
            "Content-Type to be set"
        body_type = (HttpBodyType)(content_type.lower())
        body = HttpBody(body_type, "")
        result["request"].body = body
        result["state"] = ParserState.BODY

    return result
    # }}}


def _populate_body(body: str, request: HttpRequest) -> HttpRequest:
    """
    Responsible for the [Request Body] portion of the http file.
    This function also performs the validation of the body based
    on the Content-Type header
    """
    # _populate_body {{{
    body_type = request.body.body_type

    if body_type == HttpBodyType.textplain:
        request.body.body = body

    elif body_type == HttpBodyType.json:
        validated = json.loads(body)  # Validate json
        request.body.body = json.dumps(validated)

    elif body_type == HttpBodyType.xwwwformurlencoded:
        split = body.strip().split("&")
        for pair in split:
            assert re.fullmatch(".*=.*", pair)
        request.body.body = body

    elif body_type == HttpBodyType.multipartformdata:
        # TODO implement
        raise NotImplementedError

    return request
    # }}}


def _populate_headers(line: str, request: HttpRequest) -> HttpRequest:
    """
    Responsible for [Header Key]: [Header Value] portion of http file
    """
    # _populate_headers {{{
    split = line.split(":")
    key = split[0].strip()
    value = split[1].strip()
    request.headers[key] = value
    return request
    # }}}


def _populate_metadata(line: str, request: HttpRequest) -> HttpRequest:
    """
    Responsible for the [HTTP Method] [URL] [HTTP Version] portion of the
    http file
    """
    # _populate_metadata {{{
    split = line.split(" ")
    request.method = (HttpMethod)(split[0].upper())
    request.url = split[1]
    if len(split) > 2:
        request.version = (float)(split[2])
    else:
        request.version = 1.1
    return request
    # }}}


def _populate_variables(line: str, variables: dict) -> dict:
    """
    Counts anything with prefixed with a @ as a variable
    """
    # _populate_variables {{{
    split = line.split("=")
    key = split[0].replace("@", "")
    value = split[1].rstrip()
    variables[key] = value
    return variables
    # }}}


def _replace_variables(line: str, variables: dict) -> str:
    """
    Replaces anything with contained in {{...}}
    """
    # _replace_variables {{{
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
    # }}}


if __name__ == "__main__":
    """
    Easily peek into the parsing
    result of a given .http file
    """
    import argparse

    description = "Test parsing of provided HTTP file"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("file", help=".http file to parse")
    arguments = parser.parse_args()

    requests = parse_http_file(arguments.file)
    for request in requests:
        print(request)
