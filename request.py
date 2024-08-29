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
class Request():
    url: str
    body: object
    headers: dict
    version: float
    method: HttpMethod
    encrypted: bool  # HTTPS or HTTP
