export * from "./types";

export { request, setAuthToken, getAuthToken, clearAuthToken } from "./request";

export { getApiUrl, getWsUrl } from "./config";

import { authApi } from "./modules/auth";
import { updateApi } from "./modules/update";
import { rootApi } from "./modules/root";
import { channelApi } from "./modules/channel";
import { envsApi } from "./modules/env";
import { providerApi } from "./modules/provider";
import { agentApi } from "./modules/agent";
import { workspaceApi } from "./modules/workspace";
import { ollamaModelApi } from "./modules/ollamaModel";
import { onnxModelApi } from "./modules/onnxModel";
import { uploadApi } from "./modules/upload";
import { acpApi } from "./modules/acp";
import { embeddingApi } from "./modules/embedding";
import { browserApi } from "./modules/browser";
import { mbtiApi } from "./modules/mbti";
import { terminalAiApi } from "./modules/terminalAi";
import { ssoApi } from "./modules/sso";
import { knowledgeBasesApi } from "./modules/knowledgeBases";

export const api = {
  // Root
  ...rootApi,

  // Update
  ...updateApi,

  // Auth
  ...authApi,
  ...ssoApi,

  // Knowledge bases
  ...knowledgeBasesApi,

  // ACP
  ...acpApi,

  // Channels
  ...channelApi,

  // Environment Variables
  ...envsApi,

  // Providers
  ...providerApi,

  // Agent
  ...agentApi,

  // Workspace
  ...workspaceApi,

  // Ollama Models
  ...ollamaModelApi,

  // ONNX local embedding service
  ...onnxModelApi,

  // Upload
  ...uploadApi,

  // Embedding
  ...embeddingApi,

  // Browser (Auth Handoff)
  ...browserApi,

  // MBTI
  ...mbtiApi,

  // Terminal AI
  ...terminalAiApi,
};

export default api;
