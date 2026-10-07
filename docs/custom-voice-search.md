# Custom voice and web search providers

In **Settings → Models → Voice**, select **Add custom voice provider**. Give
the provider a unique name, choose STT, TTS, or both, and configure the API key,
public HTTPS base URL (including the API prefix, such as `/v1`), model names,
and TTS voice identifier. Test the configuration before saving, then activate
the provider for speech recognition or synthesis. Saved providers can be edited
and deleted; switch away from an active provider before deleting it.

Voice uses the OpenAI audio HTTP contracts: multipart `POST
{base_url}/audio/transcriptions` returning `{"text": "…"}` for STT, and JSON
`POST {base_url}/audio/speech` returning MP3 audio for TTS. STT and TTS models
are configured independently. Existing API configurations using `extra.model`
remain supported. Baidu Qianfan and Alibaba Qwen native voice protocols are
not automatically compatible with these endpoints; use an audio gateway that
implements these contracts. This setting does not adapt arbitrary voice APIs.

In **Settings → Models → Search**, configure the **Custom Search** card:

| Field | Value |
| --- | --- |
| Search endpoint URL | Full public HTTPS endpoint, not a base URL |
| API Key | Sent as `Authorization: Bearer …` |
| API protocol | Tavily-compatible or Baidu Qianfan Web Search |

For Qianfan, use `https://qianfan.baidubce.com/v2/ai_search/web_search` and a
Qianfan API key. Octop sends `messages` and a `resource_type_filter` with
`type: web` and `top_k`; the response must contain a `references` list.
For Tavily-compatible endpoints, Octop sends `query`, `max_results`, and
`search_depth: basic`; the response must contain a `results` list.

Configuration is stored in the global env file under `CUSTOM_SEARCH_URL`,
`CUSTOM_SEARCH_API_KEY`, and `CUSTOM_SEARCH_PROTOCOL` (`tavily` or `qianfan`).
The connection test uses the unsaved values without changing process env.
Saving or revoking configuration reloads agents through the existing search
configuration workflow. Custom search takes priority over harness search
providers; revoking it restores the existing provider selection. Agent search
disable settings and the team-host tool restrictions still apply.
