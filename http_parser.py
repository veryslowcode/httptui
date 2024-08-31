from request_struct import HttpRequest, HttpMethod
from pathlib import Path
from enum import Enum
import re


class ParserState(Enum):
    METADATA = 0
    HEADERS  = 1
    BODY     = 2


def parse_http_file(path: str) -> list[HttpRequest]:
    file = Path(path)
    assert file.exists(), f"No file [{path}] found"

    requests = []
    variables = {}

    with file.open() as open_file:
        assert open_file.readable(), f"File [{path}] not readable"

        current_request = HttpRequest("", None, {}, 1.1, HttpMethod.GET, False)
        current_state = ParserState.METADATA

        for line in open_file:

            if line[0] == "#" or line[0:1] == "//":
                continue  # Line is a comment

            elif line[0] == "@":
                assert current_state == ParserState.METADATA, \
                    "Variables must be defined prior to a request"

                split = line.split("=")
                key = split[0].replace("@", "")
                value = split[1].rstrip()
                variables[key] = value

            elif current_state == ParserState.METADATA:
                line = replace_variables(line, variables)
                current_request = populate_metadata(line, current_request)
                current_state = ParserState.HEADERS

            elif current_state == ParserState.HEADERS:
                if line.strip() == "":
                    if current_request.method == HttpMethod.GET or \
                        current_request.method == HttpMethod.DELETE:
                        requests.append(current_request)
                        current_state = ParserState.METADATA
                        # Reset the request
                        current_request = HttpRequest("", None, {}, 1.1, 
                                                      HttpMethod.GET, False)
                    else:
                        current_state = ParserState.BODY
                    continue

                line = replace_variables(line, variables)
                current_request = populate_headers(line, current_request)
            
            elif current_state == ParserState.BODY:
                if line.strip() == "":
                    requests.append(current_request)
                    current_state = ParserState.METADATA
                    # Reset the request
                    current_request = HttpRequest("", None, {}, 1.1, 
                                                  HttpMethod.GET, False)
                    continue

                line = replace_variables(line, variables)
                continue
            
        requests.append(current_request)

    return requests


def replace_variables(line: str, variables: dict) -> str:
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


def populate_metadata(line: str, request: HttpRequest) -> HttpRequest:
    split = line.split(" ")
    request.method = (HttpMethod) (split[0].upper())
    request.url = split[1]
    request.version = (float) (split[2])
    return request


def populate_headers(line: str, request: HttpRequest) -> HttpRequest:
    split = line.split(":")
    key = split[0].strip()
    value = split[1].strip()
    request.headers[key] = value
    return request


def populate_body(line: str, request: HttpRequest) -> HttpRequest:
    return request
