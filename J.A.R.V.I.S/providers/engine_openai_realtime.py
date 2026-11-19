"""
OpenAI Realtime API engine — native audio in/out over WebSocket.

Speaks the same Live-shaped Msg dialect as providers/base.py so main.py,
viseme, echo guard, tools and barge-in keep working without changes.

Requires: httpx (already used) + websockets (optional install).
Config: OpenAI API key + model (e.g. gpt-4o-realtime-preview).

This is an alternative to Gemini Live, not a replacement. Select it in the
providers panel when you want OpenAI's realtime path.
"""
from __future__ import annotations

import asyncio
import audioop
import base64
import json
import traceback
from typing import Any, AsyncIterator, Optional

from .base import (
    DEFAULT_CAPS, Field, FunctionCall, Msg, ServerContent, Transcription, ToolCall,
)


def available() -> bool:
    try:
        import importlib.util
        return (
            importlib.util.find_spec("websockets") is not None
            and importlib.util.find_spec("httpx") is not None
        )
    except Exception:
        return False


# OpenAI realtime expects 24 kHz PCM16 mono for output; input is typically 24 kHz.
_IN_RATE = 24000
_OUT_RATE = 24000


class OpenAIRealtimeEngine:
    """Minimal Realtime session that emits Live-shaped events."""

    def __init__(self, cfg: dict):
        self._api_key = str(cfg.get("api_key") or "").strip()
        self._model = str(cfg.get("model") or "gpt-4o-realtime-preview").strip()
        self._voice = str(cfg.get("voice") or "alloy").strip()
        self._log = cfg.get("log") or (lambda _m: None)
        self._live_config = cfg.get("live_config") or {}
        self.caps = {
            **DEFAULT_CAPS,
            "vision": True,
            "tools": True,
            "tool_format": "openai",
            "audio_out": True,
            "barge_in": True,
            "non_blocking": False,
            "resumption": False,
            "max_tools": 32,
        }
        self._ws = None
        self._out_q: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._recv_task: Optional[asyncio.Task] = None
        self._tools_openai: list[dict] = []
        self._pending_calls: dict[str, FunctionCall] = {}

    def _url(self) -> str:
        return f"wss://api.openai.com/v1/realtime?model={self._model}"

    async def _ensure(self) -> None:
        if self._ws is not None:
            return
        if not self._api_key:
            raise RuntimeError("OpenAI Realtime: api_key missing")
        import websockets
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(
            self._url(),
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
        )
        # Session update: voice, modalities, tools
        session: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "voice": self._voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": {"type": "server_vad"},
            "instructions": (
                (self._live_config.get("system_instruction") or "")
                if isinstance(self._live_config, dict) else ""
            ) or "You are a helpful voice assistant.",
        }
        if self._tools_openai:
            session["tools"] = self._tools_openai
            session["tool_choice"] = "auto"
        await self._ws.send(json.dumps({"type": "session.update", "session": session}))
        self._recv_task = asyncio.create_task(self._reader())
        self._log(f"[Realtime] connected model={self._model}")

    def set_tools(self, openai_tools: list[dict]) -> None:
        """Called by the pipeline wiring if tools were converted to OpenAI shape."""
        self._tools_openai = list(openai_tools or [])

    async def send_realtime_input(self, *, audio) -> None:
        """Microphone PCM. Accept 16 kHz or 24 kHz mono; resample to 24 kHz if needed."""
        await self._ensure()
        pcm = _pcm_bytes(audio)
        if not pcm:
            return
        # Heuristic: main.py usually sends 16 kHz; realtime wants 24 kHz.
        if len(pcm) > 0:
            # Assume 16 kHz input from the app mic path unless tagged.
            try:
                pcm = audioop.ratecv(pcm, 2, 1, 16000, _IN_RATE, None)[0]
            except Exception:
                pass
        b64 = base64.b64encode(pcm).decode("ascii")
        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": b64,
        }))

    async def send_client_content(self, *, turns, turn_complete: bool = True) -> None:
        await self._ensure()
        # turns: Gemini-shaped {"role","parts":[...]}
        texts = []
        images = []
        for turn in (turns if isinstance(turns, list) else [turns]):
            if not isinstance(turn, dict):
                continue
            for part in turn.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("text"):
                    texts.append(str(part["text"]))
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict) and inline.get("data"):
                    images.append(inline)
        if texts:
            await self._ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "\n".join(texts)}],
                },
            }))
        for img in images:
            # Best-effort: realtime image support varies by model; send as text note if needed.
            mime = img.get("mime_type") or img.get("mimeType") or "image/jpeg"
            await self._ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_image",
                        "image_url": f"data:{mime};base64,{img.get('data')}",
                    }],
                },
            }))
        if turn_complete:
            await self._ws.send(json.dumps({"type": "response.create"}))

    async def send_tool_response(self, *, function_responses) -> None:
        await self._ensure()
        items = function_responses if isinstance(function_responses, list) else [function_responses]
        for fr in items:
            if not isinstance(fr, dict):
                continue
            call_id = str(fr.get("id") or fr.get("call_id") or "")
            output = fr.get("response") or fr.get("output") or fr
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)[:6000]
            await self._ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            }))
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if self._closed:
                    break
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                et = ev.get("type") or ""
                if et == "response.audio.delta":
                    b64 = ev.get("delta") or ""
                    if b64:
                        try:
                            pcm = base64.b64decode(b64)
                            await self._out_q.put(Msg.audio(pcm))
                        except Exception:
                            pass
                elif et == "response.audio_transcript.delta":
                    text = ev.get("delta") or ""
                    if text:
                        await self._out_q.put(Msg.said(text))
                elif et == "conversation.item.input_audio_transcription.completed":
                    text = ev.get("transcript") or ""
                    if text:
                        await self._out_q.put(Msg.heard(text))
                elif et == "response.function_call_arguments.done":
                    call_id = str(ev.get("call_id") or "")
                    name = str(ev.get("name") or "")
                    try:
                        args = json.loads(ev.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    if name:
                        fc = FunctionCall(id=call_id or f"call_{name}", name=name, args=args)
                        self._pending_calls[call_id or name] = fc
                elif et == "response.done":
                    if self._pending_calls:
                        calls = list(self._pending_calls.values())
                        self._pending_calls.clear()
                        await self._out_q.put(Msg.calls(calls))
                    await self._out_q.put(Msg.turn_end())
                elif et == "input_audio_buffer.speech_started":
                    # Barge-in signal — surface as interrupted
                    await self._out_q.put(Msg(
                        server_content=ServerContent(interrupted=True)
                    ))
                elif et == "error":
                    err = ev.get("error") or ev
                    self._log(f"[Realtime] error: {err}")
        except Exception as e:
            if not self._closed:
                self._log(f"[Realtime] reader stopped: {e}")
                traceback.print_exc()
        finally:
            await self._out_q.put(None)

    def receive(self) -> AsyncIterator[Msg]:
        async def _gen():
            await self._ensure()
            while not self._closed:
                item = await self._out_q.get()
                if item is None:
                    break
                yield item
        return _gen()

    async def close(self) -> None:
        self._closed = True
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None


def _pcm_bytes(audio) -> bytes:
    if audio is None:
        return b""
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    # google.genai style blob
    data = getattr(audio, "data", None)
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(audio, dict) and isinstance(audio.get("data"), (bytes, bytearray)):
        return bytes(audio["data"])
    return b""


def _make(cfg: dict) -> OpenAIRealtimeEngine:
    return OpenAIRealtimeEngine(cfg)


PROVIDER = {
    "id": "openai_realtime",
    "kind": "engine",
    "label": "OpenAI Realtime",
    "hint": "Native audio WebSocket — low latency, barge-in, tools (needs websockets)",
    "requires": ("websockets", "httpx"),
    "install": "websockets httpx",
    "needs": (
        Field("api_key", "OpenAI API key", kind="secret", required=True),
        Field("model", "Realtime model",
              default="gpt-4o-realtime-preview",
              hint="e.g. gpt-4o-realtime-preview"),
        Field("voice", "Voice", default="alloy",
              choices=("alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"),
              advanced=True),
    ),
    "caps": {
        "vision": True,
        "tools": True,
        "tool_format": "openai",
        "audio_out": True,
        "barge_in": True,
        "non_blocking": False,
        "resumption": False,
        "max_tools": 32,
    },
    "factory": _make,
}
