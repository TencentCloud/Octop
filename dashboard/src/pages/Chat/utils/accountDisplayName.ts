/** Same label as the sidebar / account avatar: display name, then username. */
export function accountDisplayName(
  user:
    | { display_name?: string | null; username?: string | null }
    | null
    | undefined,
): string {
  return user?.display_name?.trim() || user?.username?.trim() || "";
}

export function accountInitials(name: string): string {
  const source = name.trim() || "?";
  return source.charAt(0).toUpperCase();
}
