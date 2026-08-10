import {
  isWriteTodosToolName,
  parseWriteTodosToolData,
  sortTodoItems,
} from "../utils/parseWriteTodos";
import { TodoListView } from "./TodoProgressPanel";

export function TodoListInline({
  toolName,
  argumentsRaw,
  outputRaw,
  isStreaming = false,
}: {
  toolName?: string;
  argumentsRaw?: string;
  outputRaw?: string;
  isStreaming?: boolean;
}) {
  if (!isWriteTodosToolName(toolName)) return null;
  const items = sortTodoItems(
    parseWriteTodosToolData(argumentsRaw, outputRaw, isStreaming),
  );
  if (items.length === 0) return null;
  return <TodoListView items={items} isStreaming={isStreaming} />;
}
