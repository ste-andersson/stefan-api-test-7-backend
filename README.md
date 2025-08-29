# stefan-api-test-7 – Backend (FastAPI + Realtime STT)

Detta är ett minimalt backend för live-transkribering (STT) via **OpenAI/Azure Realtime API** med **FastAPI** och **WebSocket**.
Frontend (Lovable) skickar PCM16 @ 16kHz som binära chunks över `/ws/transcribe`. Backend vidarebefordrar ljudet till Realtime-API:t och returnerar löpande textdeltas till frontend (ord‑för‑ord‑känsla).

## Snabbstart (lokalt)

1) Skapa och aktivera virtuell miljö (du kör redan så här):
```bash
uv venv --python python3.13
source .venv/bin/activate
```

2) Installera beroenden:
```bash
make install
```

3) Skapa `.env` (kopiera från exempel och fyll i nycklar):
```bash
cp .env.example .env
# Fyll i OPENAI_API_KEY och verifiera REALTIME_URL m.m.
```

4) Starta dev-server (auto-reload):
```bash
make dev
# Server på http://localhost:8000
```

## Viktiga miljövariabler

- **OPENAI_API_KEY** – API-nyckel (OpenAI eller Azure OpenAI).
- **REALTIME_URL** – WebSocket endpoint för Realtime.
  - OpenAI-exempel: `wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17`  
  - Azure-exempel: `wss://<din-resurs>.openai.azure.com/openai/realtime?api-version=2025-04-01-preview&deployment=<ditt-deployment-namn>`  
- **REALTIME_TRANSCRIBE_MODEL** – `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` (vi kör svenska).
- **INPUT_LANGUAGE** – `sv` (för svenska, förbättrar accuracy/latency).
- **OPENAI_ADD_BETA_HEADER** – sätt `1` om din endpoint kräver headern `OpenAI-Beta: realtime=v1`.
- **COMMIT_INTERVAL_MS** – hur ofta vi skickar `input_audio_buffer.commit` för att få löpande text.
- **CORS_ORIGINS** – `*.lovable.app` samt lokalt (`http://localhost:3000` m.fl.).

> **OBS:** Realtime API accepterar PCM16 (och g711 μ-law/a-law). Den här backend:en skickar PCM16 (base64) via `input_audio_buffer.append` och gör frekventa `commit` för att få snabb text.  
> **Referenser:** se *Audio events reference* (Azure OpenAI) för `input_audio_buffer.append/commit` och transkriptionshändelserna.

## WebSocket-protokoll (frontend ↔ backend)

- **Kund → Server**: Skicka **binära** PCM16-chunks (16kHz). Ingen wrapper krävs.
- **Server → Kund**: Backend skickar **text**-meddelanden (deltas). Frontend sätter ihop till en löpande sträng.

Första meddelandet från backend är JSON:
```json
{ "type": "session.started", "session_id": "<uuid>" }
```

## Debug- och observability-endpoints

- `GET /debug/frontend-chunks?session_id=...&limit=200` – antal bytes/chunk som inkommit från frontend (senaste N).
- `GET /debug/openai-chunks?session_id=...` – antal bytes/chunk vidarebefordrat till OpenAI.
- `GET /debug/openai-text?session_id=...` – transkriberad text (historik).
- `GET /debug/frontend-text?session_id=...` – textdeltas som skickats till frontend.
- `POST /debug/reset` – nollställer buffertar (globalt eller per `session_id`).
- `GET /config` – visar körningskonfig.
- `GET /healthz` – enkel healthcheck.

## CORS och origins

- Tillåter `*.lovable.app` och lokalt (localhost:3000/5173). WebSocket-origin valideras inte av CORS, men HTTP-endpoints skyddas via `CORSMiddleware`. Justera vid behov i `.env`.

## Deploy på Render

- Bind till `0.0.0.0` och läs `PORT` från miljö (Makefile:s `run` stödjer det).
- Lägg in `OPENAI_API_KEY`, `REALTIME_URL`, `REALTIME_TRANSCRIBE_MODEL`, `INPUT_LANGUAGE=sv` i Render Environment.

## Kända noter

- För ord-för-ord-känsla används frekventa `commit` + enkel diff. Om din Realtime‑deployment ger mer granulara transkriptions‑events kan du parsa dem direkt i `on_rt_event`.
- Om du använder Azure Realtime: kontrollera API-version och modellnamn (public preview kan ändras).
