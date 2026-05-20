# Research: Dynamic Model Listing via OpenAI-Compatible /v1/models

- **Query**: How OpenAI-compatible APIs expose model listing, and what VideoNote needs to implement
- **Scope**: Mixed (internal codebase + external API testing)
- **Date**: 2026-05-20

## Findings

### 1. OpenAI `/v1/models` Endpoint Specification

**Request format:**
- `GET /v1/models`
- Authentication: `Authorization: Bearer <api_key>` header (required)
- Optional query params (OpenAI official): `limit` (int, default 20, max 100), `after` (str, cursor for pagination)

**Response format (OpenAI canonical):**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4o",
      "object": "model",
      "created": 1715367049,
      "owned_by": "system"
    }
  ]
}
```

**Model object fields (from OpenAI SDK `openai.types.model.Model`):**
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | Yes | Model identifier (e.g. "gpt-4o", "deepseek-chat") |
| `object` | `Literal["model"]` | Yes | Always "model" |
| `created` | `int` | Yes | Unix timestamp of creation (can be `None`/`null` in some providers) |
| `owned_by` | `str` | Yes | Owner of the model (can be empty string in some providers) |

**Pagination fields on the page object (OpenAI SDK `SyncPage`):**
| Field | Type | Description |
|---|---|---|
| `object` | `str` | "list" |
| `data` | `list[Model]` | Array of model objects |
| `has_more` | `bool` | Whether more pages exist (not always present) |
| `first_id` | `str | None` | Cursor for first item |
| `last_id` | `str | None` | Cursor for last item |

### 2. Provider-by-Provider /v1/models Compatibility

#### OpenAI (api.openai.com/v1)
- Full spec compliance. Requires Bearer auth.
- Returns all standard fields: `id`, `object`, `created`, `owned_by`
- Supports `limit` and `after` pagination params
- Large model list (100+ models)

#### DeepSeek (api.deepseek.com/v1)
- Compatible endpoint at `GET /v1/models`
- Returns `object: "list"` at top level
- **Only 2 models returned** (deepseek-v4-flash, deepseek-v4-pro)
- `created` field is **omitted** (null in SDK), `owned_by` = "deepseek"
- No pagination (small list)

#### SiliconFlow (api.siliconflow.cn/v1)
- Compatible endpoint at `GET /v1/models`
- Returns `object: "list"` at top level
- **91 models** returned in a single response
- `created` is always `0` (placeholder), `owned_by` is always empty string `""`
- **No pagination support** — ignores `limit` param, returns all models at once
- Model IDs include organization prefix (e.g. "deepseek-ai/DeepSeek-V4-Flash", "FunAudioLLM/SenseVoiceSmall")
- Mixes LLM, ASR, TTS, embedding, image, and reranker models in one list

#### OpenRouter (openrouter.ai/api/v1/models)
- **Public endpoint — no auth required** for model listing
- Returns 357 models
- **Non-standard**: omits `object` field from both top-level and model objects, omits `owned_by`
- Adds many extra fields per model: `name`, `description`, `context_length`, `architecture` (modality info), `pricing`, `supported_parameters`, etc.
- No pagination — returns all models in one response
- Model IDs use `provider/model` format (e.g. "google/gemini-3.5-flash")

#### Groq (api.groq.com/openai/v1)
- Endpoint at `GET /openai/v1/models` (note: `/openai/` prefix)
- Requires Bearer auth, returns 403 without it
- Compatible with OpenAI SDK when using correct `base_url`

#### Together AI (api.together.xyz/v1)
- Endpoint at `GET /v1/models`
- Requires Bearer auth, returns 401 without it
- Known to be compatible with OpenAI SDK

#### Ollama (localhost:11434/v1)
- Implements `/v1/models` endpoint when running locally
- Returns model objects in standard format
- Model list depends on locally pulled models
- No auth required by default

#### LiteLLM
- LiteLLM is a proxy, not a provider — it forwards `/v1/models` to the underlying provider
- When used as a proxy, model listing depends on the target provider

### 3. Summary of Cross-Provider Differences

| Provider | Standard Fields Complete | Pagination | Auth Required | Model Count | Non-Standard Fields |
|---|---|---|---|---|---|
| OpenAI | Yes | Yes (limit/after) | Yes | 100+ | No |
| DeepSeek | Partial (no `created`) | No | Yes | 2 | No |
| SiliconFlow | Partial (`created=0`, `owned_by=""`) | No | Yes | 91 | No |
| OpenRouter | No (missing `object`, `owned_by`) | No | No | 357 | Many (architecture, pricing, etc.) |
| Groq | Yes | Unknown | Yes | Varies | No |
| Together | Yes | Unknown | Yes | Varies | Some |
| Ollama | Yes | No | No | Varies | No |

**Key observation**: All providers return at minimum an `id` field per model. The `object`, `created`, and `owned_by` fields are inconsistent. Pagination is rarely implemented outside OpenAI itself.

### 4. Filtering Models by Capability

**There is no standard way to filter models by capability (chat vs audio/transcription) via the `/v1/models` API.** The endpoint returns all models regardless of type.

Workarounds used in practice:
- **OpenRouter**: Provides `architecture.modality` and `architecture.input_modalities`/`architecture.output_modalities` fields (e.g. "text+image+file+audio+video->text")
- **SiliconFlow**: Model ID prefixes often indicate type (e.g. "FunAudioLLM/SenseVoiceSmall" for ASR, "TeleAI/TeleSpeechASR" for ASR, embedding models with "embed"/"bge"/"e5" in name)
- **Heuristic filtering**: Parse model ID/name for keywords like "whisper", "tts", "embed", "image", "rerank" to categorize
- **Application-level categorization**: The VideoNote app must maintain its own logic to map models to ASR vs LLM use

### 5. Rate Limits and Pagination Concerns

- OpenAI: Rate limited (typically 500 RPM for models endpoint), supports pagination with `limit`/`after`
- Most other providers: No documented rate limits for model listing; return all models in single response
- SiliconFlow (91 models) and OpenRouter (357 models) return everything at once — no pagination
- For VideoNote: model listing should be cached on the backend to avoid hitting provider API on every frontend request

### 6. VideoNote Current Codebase

#### Backend Files

| File | Path | Description |
|---|---|---|
| config.py | `backend/app/config.py` | PROVIDER_PRESETS dict (hardcoded), env vars for ASR/LLM defaults |
| routes.py | `backend/app/api/routes.py` | `/api/providers` returns presets, `/api/settings` for CRUD |
| schemas.py | `backend/app/schemas.py` | `ProviderPreset`, `ProvidersResponse`, `ProviderConfig`, etc. |
| db.py | `backend/app/db.py` | `user_providers` table, `save_provider_config`, `get_all_provider_configs` |
| transcribe.py | `backend/app/services/transcribe.py` | Uses `OpenAI` SDK with `client.audio.transcriptions.create` |
| note_gen.py | `backend/app/services/note_gen.py` | Uses `OpenAI` SDK with `client.chat.completions.create` |
| crypto.py | `backend/app/crypto.py` | Fernet encrypt/decrypt for API keys |

**Key observations from current code:**
- `PROVIDER_PRESETS` in `config.py:40-65` is a static dict with `asr` and `llm` keys, each containing a list of `{provider, models, api_base}` dicts
- The `/api/providers` route at `routes.py:538-544` simply returns `PROVIDER_PRESETS` as `ProvidersResponse`
- `ProviderPreset` schema at `schemas.py:92-95` has fields: `provider`, `models` (list[str]), `api_base`
- Both `transcribe.py` and `note_gen.py` use `from openai import OpenAI` and create a client with `(api_key=..., base_url=...)` — the OpenAI SDK is already installed (`openai>=1.60.0` in pyproject.toml)
- `httpx>=0.28.0` is also a dependency, so the backend can make direct HTTP calls if needed
- The `OpenAI` SDK already has `client.models.list()` which works with any OpenAI-compatible endpoint

#### Frontend Files

| File | Path | Description |
|---|---|---|
| SettingsPage.tsx | `frontend/src/pages/SettingsPage.tsx` | ProviderConfigSection component with provider/model dropdowns |
| client.ts | `frontend/src/api/client.ts` | `fetchProviders()`, `fetchSettings()`, `saveSettings()` functions |
| types/index.ts | `frontend/src/types/index.ts` | `ProviderPreset`, `ProvidersResponse`, `ProviderConfig`, etc. |

**Key observations from current frontend:**
- `ProviderConfigSection` at `SettingsPage.tsx:74-204` shows provider dropdown -> model dropdown flow
- When a provider is selected, models come from `selectedPreset?.models` (line 84) — currently a hardcoded list
- Custom provider mode (`isCustom: true`) switches model input from dropdown to free-text `<Input>` (lines 148-174)
- `fetchProviders()` at `client.ts:59-61` calls `GET /api/providers` and returns `ProvidersResponse`
- Types at `types/index.ts:27-36`: `ProviderPreset = { provider, models, api_base }`, `ProvidersResponse = { asr: ProviderPreset[], llm: ProviderPreset[] }`

### 7. Proposed Backend Endpoint Design

A new endpoint should proxy the `/v1/models` call from the user's configured provider to avoid exposing API keys to the frontend.

**Proposed route: `POST /api/models`**

```python
class ModelsRequest(BaseModel):
    api_key: str        # User's API key (will NOT be stored)
    api_base: str       # Provider base URL (e.g. "https://api.deepseek.com/v1")
    category: str        # "asr" or "llm" (for future filtering hint)

class ModelItem(BaseModel):
    id: str
    object: str | None = None
    created: int | None = None
    owned_by: str | None = None

class ModelsResponse(BaseModel):
    models: list[ModelItem]
    error: str | None = None
```

**Implementation approach using the already-installed OpenAI SDK:**
```python
from openai import AsyncOpenAI

@router.post("/models", response_model=ModelsResponse)
async def list_models(req: ModelsRequest, user: CurrentUser):
    try:
        client = AsyncOpenAI(api_key=req.api_key, base_url=req.api_base)
        # Use the SDK's built-in models.list() — works with any compatible endpoint
        page = await client.models.list()
        models = [
            ModelItem(id=m.id, object=m.object, created=m.created, owned_by=m.owned_by)
            for m in page.data
        ]
        return ModelsResponse(models=models)
    except Exception as e:
        return ModelsResponse(models=[], error=str(e))
```

**Key design decisions documented:**
- Backend proxies the request to avoid sending API key from frontend directly to third-party providers
- Uses `AsyncOpenAI` SDK (already available) rather than raw `httpx` — handles auth headers, response parsing, and compatibility
- Returns normalized `ModelItem` with optional fields to handle provider differences
- Returns `error` field for graceful degradation on failure
- The `category` parameter is included for future server-side filtering (not used for the API call itself)

### 8. Proposed Frontend Component Changes

**New API function in `client.ts`:**
```typescript
export async function fetchModels(
  apiKey: string,
  apiBase: string,
  category: "asr" | "llm"
): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>(`${API_BASE}/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, api_base: apiBase, category }),
  });
}
```

**New types in `types/index.ts`:**
```typescript
export interface ModelItem {
  id: string;
  object?: string;
  created?: number;
  owned_by?: string;
}

export interface ModelsResponse {
  models: ModelItem[];
  error?: string;
}
```

**SettingsPage.tsx `ProviderConfigSection` changes:**
- When a provider is selected (or custom provider with api_base + api_key filled), trigger `fetchModels()`
- Replace hardcoded `models` array with dynamically fetched model list
- Show a loading state while fetching
- On fetch failure: fall back to empty list + free-text input (same as custom mode)
- Keep the free-text input option available even with dynamic models (user can type a model not in the list)
- For custom provider: fetch models only after both api_base and api_key are provided

### 9. Edge Cases

| Edge Case | Description | Mitigation |
|---|---|---|
| Provider doesn't support /v1/models | Some self-hosted or niche providers may not implement the endpoint | Return error, frontend falls back to free-text input |
| Large model lists | SiliconFlow (91), OpenRouter (357) return all models at once | Frontend: use searchable select/dropdown; Backend: optional server-side filtering by category |
| No auth key provided | Can't call /v1/models without API key | Don't fetch until API key is entered; keep hardcoded presets as fallback |
| `created` / `owned_by` missing | DeepSeek omits `created`, SiliconFlow returns `created=0` and empty `owned_by` | All fields optional in `ModelItem` schema; frontend only needs `id` |
| API key exposed to backend | The backend receives the user's API key transiently for the proxy call | Key is NOT stored; only used in-memory for the single request |
| Rate limiting | OpenAI may rate-limit frequent /v1/models calls | Cache model list in backend (TTL ~5-10 min); avoid refetch on every render |
| Ollama / local providers | May be unreachable from backend if backend runs in different environment | Return connection error, frontend falls back to free-text input |
| Groq URL prefix | Groq uses `/openai/v1/models` not `/v1/models` | User provides full base_url (e.g. "https://api.groq.com/openai/v1"); OpenAI SDK handles path correctly |
| Mixed model types | SiliconFlow mixes LLM, ASR, TTS, embedding models in one list | Frontend or backend can apply keyword-based filtering (e.g. filter out "embed", "image", "rerank" for LLM list) |

### 10. OpenAI SDK `client.models.list()` Details

The project already has `openai>=1.60.0` as a dependency. Key SDK details:

- **Sync**: `client.models.list()` returns `SyncPage[Model]`
- **Async**: `AsyncOpenAI.models.list()` returns `AsyncPaginator[Model, AsyncPage[Model]]`
- The SDK sends `GET /models` (relative to base_url) with `Authorization: Bearer <key>` header
- The `Model` object has fields: `id` (str, required), `object` (Literal["model"], required), `created` (int, required but can be None), `owned_by` (str, required but can be empty)
- Works with any OpenAI-compatible endpoint when instantiated with `base_url` parameter
- **No additional code or dependencies needed** — just use the existing SDK

### 11. Related Specs

- `.trellis/tasks/05-20-api/prd.md` — PRD for this feature (enhanced API model selection)

## Caveats / Not Found

- Could not test Groq, Together AI, or Ollama directly (no API keys / no local server running). Their compatibility is based on documentation and community reports.
- OpenAI's own `/v1/models` could not be reached due to SSL issues in the test environment; information is from SDK source code and official documentation.
- No existing `.trellis/spec/` directory files were found — the project has no spec documents yet.
- The exact UX for "when to fetch models" (on provider select vs on explicit button click vs on api_key blur) is a design decision not covered by this research.
