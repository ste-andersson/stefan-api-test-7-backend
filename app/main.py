from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from .config import settings
from .debug_store import store
from .realtime_client import OpenAIRealtimeClient

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stt")

app = FastAPI(title="stefan-api-test-7 – STT-backend (FastAPI + Realtime)")


# ----------------------- CORS -----------------------
origins = []
regex = None
for part in [p.strip() for p in settings.cors_origins.split(",") if p.strip()]:
    if "*" in part:
        # översätt *.lovable.app => regex
        escaped = re.escape(part).replace(r"\*\.", ".*")
        regex = rf"https://{escaped}" if part.startswith("*.") else rf"{escaped}"
    else:
        origins.append(part)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------- Models -----------------------
class ConfigOut(BaseModel):
    realtime_url: str
    transcribe_model: str
    input_language: str
    commit_interval_ms: int
    cors_origins: list[str]
    cors_regex: Optional[str]

class DebugListOut(BaseModel):
    session_id: str
    data: list

# --------------------- Endpoints --------------------
@app.get("/healthz")
async def healthz():
    return {"ok": True, "ts": time.time()}

@app.get("/config", response_model=ConfigOut)
async def get_config():
    return ConfigOut(
        realtime_url=settings.realtime_url,
        transcribe_model=settings.transcribe_model,
        input_language=settings.input_language,
        commit_interval_ms=settings.commit_interval_ms,
        cors_origins=origins,
        cors_regex=regex,
    )

@app.get("/debug/frontend-chunks", response_model=DebugListOut)
async def debug_frontend_chunks(session_id: str = Query(...), limit: int = Query(200, ge=1, le=1000)):
    buf = store.get_or_create(session_id)
    data = list(buf.frontend_chunks)[-limit:]
    return DebugListOut(session_id=session_id, data=data)

@app.get("/debug/openai-chunks", response_model=DebugListOut)
async def debug_openai_chunks(session_id: str = Query(...), limit: int = Query(200, ge=1, le=1000)):
    buf = store.get_or_create(session_id)
    data = list(buf.openai_chunks)[-limit:]
    return DebugListOut(session_id=session_id, data=data)

@app.get("/debug/openai-text", response_model=DebugListOut)
async def debug_openai_text(session_id: str = Query(...), limit: int = Query(200, ge=1, le=2000)):
    buf = store.get_or_create(session_id)
    data = list(buf.openai_text)[-limit:]
    return DebugListOut(session_id=session_id, data=data)

@app.get("/debug/frontend-text", response_model=DebugListOut)
async def debug_frontend_text(session_id: str = Query(...), limit: int = Query(200, ge=1, le=2000)):
    buf = store.get_or_create(session_id)
    data = list(buf.frontend_text)[-limit:]
    return DebugListOut(session_id=session_id, data=data)

@app.post("/debug/reset")
async def debug_reset(session_id: str | None = Query(None)):
    store.reset(session_id)
    return {"ok": True, "session_id": session_id}

# --------------------- WebSocket --------------------
@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    await ws.accept()
    session_id = store.new_session()
    await ws.send_json({"type": "session.started", "session_id": session_id})

    # Setup klient mot OpenAI/Azure Realtime
    rt = OpenAIRealtimeClient(
        url=settings.realtime_url,
        api_key=settings.openai_api_key,
        transcribe_model=settings.transcribe_model,
        language=settings.input_language,
        add_beta_header=settings.add_beta_header,
    )
    await rt.connect()

    buffers = store.get_or_create(session_id)

    # Hålla senaste text för enkel diff
    last_text = ""

    # Task: läs events från Realtime och skicka deltas till frontend
    async def on_rt_event(evt: dict):
        nonlocal last_text
        t = evt.get("type")
        if t == "conversation.item.input_audio_transcription.completed":
            transcript = evt.get("transcript") or ""
            # För vissa servervarianter ligger transcriptet i evt['transcript'],
            # annars kan den ligga i evt.get('item', {}). Hantera båda.
            if not transcript and isinstance(evt.get("item"), dict):
                transcript = evt["item"].get("content", [{}])[0].get("transcript", "")
            if not isinstance(transcript, str):
                return

            # Beräkna "delta" för ord-för-ord-känsla
            if transcript.startswith(last_text):
                delta = transcript[len(last_text):]
            else:
                # fallback: skicka hela
                delta = transcript

            if delta:
                buffers.openai_text.append(transcript)
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json({"type": "transcript.delta", "delta": delta, "text": transcript})
                buffers.frontend_text.append(delta)
                last_text = transcript

    rt_recv_task = asyncio.create_task(rt.recv_loop(on_rt_event))

    # Periodisk commit för att få löpande partials
    async def commit_loop():
        try:
            while True:
                await asyncio.sleep(max(0.001, settings.commit_interval_ms / 1000))
                try:
                    await rt.commit()
                except Exception as e:
                    log.warning("Commit fel: %s", e)
                    break
        except asyncio.CancelledError:
            pass

    commit_task = asyncio.create_task(commit_loop())

    try:
        while ws.client_state == WebSocketState.CONNECTED:
            try:
                msg = await ws.receive()
                if "bytes" in msg and msg["bytes"] is not None:
                    chunk = msg["bytes"]
                    buffers.frontend_chunks.append(len(chunk))
                    try:
                        await rt.send_audio_chunk(chunk)
                        buffers.openai_chunks.append(len(chunk))
                    except Exception as e:
                        log.error("Fel när chunk skickades till Realtime: %s", e)
                        break
                elif "text" in msg and msg["text"] is not None:
                    # Tillåt ping/ctrl meddelanden som sträng
                    if msg["text"] == "ping":
                        await ws.send_text("pong")
                    else:
                        # ignoreras
                        pass
                else:
                    # okänt format
                    pass
            except WebSocketDisconnect:
                log.info("WebSocket stängd: %s", session_id)
                break
            except Exception as e:
                log.error("WebSocket fel: %s", e)
                break
    finally:
        commit_task.cancel()
        rt_recv_task.cancel()
        try:
            await rt.close()
        except Exception:
            pass
        try:
            await asyncio.gather(commit_task, rt_recv_task, return_exceptions=True)
        except Exception:
            pass
        # Kontrollera att WebSocket fortfarande är öppen innan vi stänger
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass
