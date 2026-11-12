import { message } from "../../../utils/antdMessage";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { patchStoredSession } from "../hooks/useSessions";

/** Persist the share flag and tell the user when it does not stick. */
export async function saveSessionShared(
  agentId: string,
  sessionId: string,
  contributed: boolean,
  onSaved: () => void,
  failedText: string,
): Promise<void> {
  try {
    await octopThreadsApi.patch(agentId, sessionId, { contributed });
  } catch {
    message.error(failedText);
    return;
  }
  patchStoredSession(sessionId, { contributed });
  onSaved();
}
