import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  BookOpen,
  Brain,
  CalendarClock,
  CircleHelp,
  Clock,
  Code2,
  Eye,
  FileKey,
  FilePen,
  FileSearch,
  FileText,
  Folder,
  Globe,
  Handshake,
  Image,
  Library,
  ListChecks,
  ListTodo,
  MessageCircle,
  Monitor,
  MousePointerClick,
  Move,
  Pencil,
  Play,
  Plug,
  Plus,
  Search,
  Send,
  Smartphone,
  Terminal,
  Trash2,
  Users,
  Video,
  Wrench,
} from "lucide-react";

/** Lucide icons for built-in harness / Octop host tools. */
export const BUILTIN_TOOL_ICONS: Record<string, LucideIcon> = {
  ls: Folder,
  read_file: FileSearch,
  write_file: FilePen,
  edit_file: Pencil,
  glob: Search,
  grep: FileText,
  execute: Terminal,
  write_todos: ListTodo,
  task: Users,
  current_time: Clock,
  web_fetch: Globe,
  browser_use: AppWindow,
  desktop_screenshot: Monitor,
  send_file_to_user: Send,
  read_env_file: FileKey,
  write_env_file: FileKey,
  ask_user_question: CircleHelp,
  tavily_search: Globe,
  brave_search: Globe,
  google_search: Globe,
  kimi_search: Globe,
  searchfree_search: Globe,
  generate_image: Image,
  generate_video: Video,
  memory_search: Brain,
  memory_get: BookOpen,
  acp_runner: Plug,
  cronjob_list: ListChecks,
  cronjob_get: Eye,
  cronjob_create: Plus,
  cronjob_update: CalendarClock,
  cronjob_delete: Trash2,
  cronjob_run_now: Play,
  search_knowledge: Library,
  mobile_screenshot: Smartphone,
  mobile_tap: MousePointerClick,
  mobile_swipe: Move,
  mobile_launch_app: AppWindow,
  mobile_ui_dump: Code2,
  mobile_handoff_to_user: Handshake,
  agent_list: Users,
  ask_agent: MessageCircle,
};

function toolNameBase(name: string): string {
  const trimmed = name.trim();
  const slash = trimmed.lastIndexOf("/");
  return slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
}

/** Resolve a Lucide icon for a built-in tool; unknown tools fall back to wrench. */
export function builtinToolIcon(toolName: string): LucideIcon {
  const base = toolNameBase(toolName).toLowerCase();
  return BUILTIN_TOOL_ICONS[base] ?? Wrench;
}
