from request_struct import HttpRequest, HttpMethod
from pathlib import Path
from enum import Enum

class ParserState(Enum):
    METADATA = 0
    HEADERS = 1
    BODY = 2
    FULL = 3

def parse_http_file(path: str) -> list[HttpRequest]:
    file = Path(path)
    assert file.exists(), f"No file [{path}] found"

    requests = []

    with file.open() as open_file:
        assert open_file.readable(), f"File [{path}] not readable"

        current_request = HttpRequest()
        current_state = ParserState.METADATA

        for line in open_file:

            if line[0] == "#" or line[0:1] == "//":
                continue  # Line is a comment

            elif line[0] == "@":
                # TODO Variable
                pass

            elif current_state == ParserState.METADATA:
                split = line.split(" ")
                current_request.method = (HttpMethod) (split[0].upper())
                current_request.url = split[1]
                current_request.version = (float) (split[2])
                current_state = ParserState.HEADERS

            elif current_state == ParserState.HEADERS:
                split = line.split(":")
                key = split[0].strip()
                value = split[1].strip()
                current_request.headers[key] = value

            elif current_state == ParserState.BODY:
                pass

            else:
                pass

        if current_state != ParserState.FULL:
            raise SyntaxError("Invalid format of .http file")
        else:
            requests.append(current_request)

    return requests

