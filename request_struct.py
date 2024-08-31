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


@dataclass
class HttpRequest():
    url: str
    body: object
    headers: dict
    version: float
    method: HttpMethod
    encrypted: bool  # HTTPS or HTTP

    def __str__(self) -> str:
        metadata = f"{self.method.value} {self.url} {self.version}\n"
        headers = f"{self.headers}\n" if self.headers else ""
        body = f"{self.body}\n" if self.body is not None else ""
        return metadata + headers + body
        
