import { isBridgeAgentId } from "../../utils/remoteExpert";
import {
  isToolPluginIndexReady,
  lookupPluginIdForTool,
} from "./toolPluginIndex";

/**
 * Cloud expert returned a plugin card, and this machine has no matching plugin.
 * Wait until the local catalog has loaded so a slow list does not flash the note.
 */
export function remotePluginUiUnavailable(opts: {
  agentId?: string | null;
  toolName?: string;
  hasOctopUi: boolean;
}): boolean {
  if (!opts.hasOctopUi) return false;
  if (!isBridgeAgentId(opts.agentId)) return false;
  if (!isToolPluginIndexReady()) return false;
  return lookupPluginIdForTool(opts.toolName) == null;
}
