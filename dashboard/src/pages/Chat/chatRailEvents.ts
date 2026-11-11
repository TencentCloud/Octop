/**
 * Window event: "open the conversation-history rail".
 *
 * The rail's fold control only owns its own boolean, but opening it while the
 * nav is collapsed would reveal it beside nothing — so the click broadcasts
 * instead of setting the flag directly, and whoever mounts both columns
 * (MainLayout) decides that opening one also brings the other back.
 */
export const EXPAND_CHAT_RAIL_EVENT = "octop:expand-chat-rail";
