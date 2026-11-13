from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get(
    "/ping",
    tags=["Health Check"],
    description="检查服务可用性",
    response_class=PlainTextResponse,
    response_description="pong",
)
def ping(request: Request) -> str:
    return "pong"
