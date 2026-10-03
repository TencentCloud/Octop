export function isEmbeddedChatPath(pathname: string): boolean {
  return pathname === "/embed/chat" || pathname.startsWith("/embed/chat/");
}

export function chatHomePath(pathname: string): string | null {
  if (!isEmbeddedChatPath(pathname)) return "/chat";
  const agentId = pathname.split("/")[3];
  return agentId ? `/embed/chat/${agentId}` : null;
}

export function chatLoginPath(location: {
  pathname: string;
  search: string;
  hash: string;
}): string {
  if (!isEmbeddedChatPath(location.pathname)) return "/login";
  const redirect = location.pathname + location.search + location.hash;
  return `/login?redirect=${encodeURIComponent(redirect)}`;
}
