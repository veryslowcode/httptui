from enum import Enum
from dataclasses import dataclass


class HttpMethod(Enum):
    # HttpMethod {{{
    GET = "GET"
    PUT = "PUT"
    POST = "POST"
    HEAD = "HEAD"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    # }}}


class HttpBodyType(Enum):
    # HttpBodyType {{{
    textplain = "text/plain"
    json = "application/json"
    multipartformdata = "multipart/form-data"
    xwwwformurlencoded = "application/x-www-form-urlencoded"
    # }}}


@dataclass
class HttpBody():
    # HttpBody {{{
    body_type: HttpBodyType
    body: str

    def __str__(self) -> str:
        return self.body
    # }}}


@dataclass
class HttpRequest():
    # HttpRequest {{{
    url: str
    headers: dict
    version: float
    body: HttpBody
    method: HttpMethod
    name: str = ""   # Non-essential

    def __str__(self) -> str:
        metadata = f"{self.method.value} {self.url} {self.version}\n"
        headers = f"{self.headers}\n" if self.headers else ""
        body = f"{self.body}\n" if self.body is not None else ""
        return self.name + metadata + headers + body
    # }}}
