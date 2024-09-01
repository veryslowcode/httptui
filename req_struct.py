from enum import Enum
from dataclasses import dataclass


class HttpMethod(Enum):
    GET = "GET"
    PUT = "PUT"
    POST = "POST"
    PATCH = "PATCH"
    TRACE = "TRACE"
    DELETE = "DELETE"
    CONNECT = "CONNECT"
    OPTIONS = "OPTIONS"


class HttpBodyType(Enum):
    textplain = "text/plain"
    json = "application/json"
    multipartformdata = "multipart/form-data"
    xwwwformurlencoded = "application/x-www-form-urlencoded"


@dataclass
class HttpBody():
    body_type: HttpBodyType
    body: str

    def __str__(self) -> str:
        return self.body


@dataclass
class HttpRequest():
    url: str
    headers: dict
    version: float
    body: HttpBody
    method: HttpMethod
    encrypted: bool  # HTTPS or HTTP

    def __str__(self) -> str:
        metadata = f"{self.method.value} {self.url} {self.version}\n"
        headers = f"{self.headers}\n" if self.headers else ""
        body = f"{self.body}\n" if self.body is not None else ""
        return metadata + headers + body
