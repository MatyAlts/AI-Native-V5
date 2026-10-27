"""Espejo del ai-gateway para la prueba local 6.3 (NO es codigo de produccion).

Escucha en :8111, reenvia cada request al ai-gateway real (:8011) y guarda el
body que mando el tutor-service en el archivo JSONL de la variable ESPEJO_LOG.
Asi se puede ver EXACTAMENTE que mensajes llegan al LLM.
"""

import json
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

REAL = os.environ.get("AI_GATEWAY_REAL", "http://127.0.0.1:8011")
LOG = os.environ.get("ESPEJO_LOG", "espejo-requests.jsonl")


async def proxy(request: Request) -> StreamingResponse:
    body = await request.body()
    if request.url.path.endswith("/stream"):
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(json.loads(body), ensure_ascii=False) + "\n")
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")
    }
    client = httpx.AsyncClient(timeout=60)
    req = client.build_request(
        request.method, REAL + request.url.path, content=body, headers=headers
    )
    resp = await client.send(req, stream=True)

    async def gen():
        async for chunk in resp.aiter_raw():
            yield chunk
        await resp.aclose()
        await client.aclose()

    return StreamingResponse(
        gen(), status_code=resp.status_code, media_type=resp.headers.get("content-type")
    )


app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST"])])
