/** Resolve display names for speakers still generating in a team room. */

export interface NamedAgent {
  agent_id: string;
  name?: string | null;
}

/**
 * Pick up to ``limit`` readable names for ``liveSpeakers`` keys
 * (``""`` / host id → hostName).
 */
export function resolveLiveSpeakerNames(
  liveSpeakers: ReadonlyArray<string>,
  agents: ReadonlyArray<NamedAgent>,
  opts?: {
    hostId?: string | null;
    hostName?: string | null;
    limit?: number;
  },
): string[] {
  const hostId = (opts?.hostId || "").trim();
  const hostName = (opts?.hostName || "").trim();
  const limit = opts?.limit ?? 2;
  const names: string[] = [];
  const seen = new Set<string>();

  for (const raw of liveSpeakers) {
    const key = (raw || "").trim();
    const isHost = !key || (hostId && key === hostId);
    const name = isHost
      ? hostName ||
        agents.find((a) => a.agent_id === hostId)?.name?.trim() ||
        ""
      : agents.find((a) => a.agent_id === key)?.name?.trim() || key;
    const label = name.trim();
    if (!label || seen.has(label)) continue;
    seen.add(label);
    names.push(label);
    if (names.length >= limit) break;
  }
  return names;
}

/** True when any assistant tool bubble is still waiting on a result. */
export function hasInFlightTool(
  messages: ReadonlyArray<{
    status?: string;
    toolData?: { output?: unknown } | null;
  }>,
): boolean {
  return messages.some(
    (m) =>
      Boolean(m.toolData) &&
      m.status === "streaming" &&
      m.toolData?.output === undefined,
  );
}

/** True when a thinking/reasoning bubble is still streaming. */
export function hasStreamingThinking(
  messages: ReadonlyArray<{
    status?: string;
    type?: string;
    toolData?: unknown;
    contentBlocks?: ReadonlyArray<{ type: string }> | null;
  }>,
): boolean {
  return messages.some((m) => {
    if (m.status !== "streaming" || m.toolData) return false;
    if (m.type === "reasoning") return true;
    return Boolean(m.contentBlocks?.some((block) => block.type === "thinking"));
  });
}
