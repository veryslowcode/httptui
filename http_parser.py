from request_struct import HttpRequest, HttpMethod
from pathlib import Path
from enum import Enum

class ParserState(Enum):
    METADATA = 0
    HEADERS  = 1
    BLANK    = 2
    BODY     = 3
    COMPLETE = 4

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
                assert current_state == ParserState.COMPLETE, \
                    "Variables must be defined prior to a request"
                split = line.split("=")
                key = split[0]
                value = split[1]
                variables[key] = value

            elif current_state == ParserState.METADATA:
                split = line.split(" ")
                current_request.method = (HttpMethod) (split[0].upper())
                current_request.url = split[1]
                current_request.version = (float) (split[2])
                current_state = ParserState.HEADERS
                           
            elif current_state == ParserState.BLANK:
                # This should be done before HEADERS
                # as the end of headers is only
                # indicated by a blank line
                if line.strip != "":
                    current_state = ParserState.HEADERS

            elif current_state == ParserState.HEADERS:
                if line.strip() == "":
                    current_state = ParserState.BODY
                    continue  # Indication of no headers
                split = line.split(":")
                key = split[0].strip()
                value = split[1].strip()
                current_request.headers[key] = value
            
            elif current_state == ParserState.BODY:
                if line.strip() == "":
                    current_state = ParserState.COMPLETE
                    continue  # Indication of no body
                current_state = ParserState.COMPLETE
                pass

            else:
                pass
            
        if current_state != ParserState.COMPLETE:
            raise SyntaxError("Invalid format of .http file")
        else:
            requests.append(current_request)

    return requests
