import { buildTool, type Tool } from './tool.js'

export type TodoStatus = 'pending' | 'in_progress' | 'completed'

export type TodoItem = {
  content: string
  activeForm: string
  status: TodoStatus
}

export type TodoStore = {
  get(scopeId: string): Promise<TodoItem[]>
  set(scopeId: string, todos: readonly TodoItem[]): Promise<void>
}

export class InMemoryTodoStore implements TodoStore {
  private readonly lists = new Map<string, TodoItem[]>()

  async get(scopeId: string): Promise<TodoItem[]> {
    return structuredClone(this.lists.get(scopeId) ?? [])
  }

  async set(scopeId: string, todos: readonly TodoItem[]): Promise<void> {
    if (todos.length === 0) this.lists.delete(scopeId)
    else this.lists.set(scopeId, structuredClone([...todos]))
  }
}

type TodoWriteInput = { todos: TodoItem[] }

export function createTodoWriteTool({
  store,
  scopeId = 'main',
}: {
  store: TodoStore
  scopeId?: string
}): Tool {
  return buildTool<TodoWriteInput, unknown>({
    name: 'TodoWrite',
    description: 'Replace the current task checklist. Use it to keep parent-agent goals and progress explicit.',
    inputSchema: {
      todos: {
        type: 'array',
        required: true,
        items: {
          type: 'object',
          additionalProperties: false,
          properties: {
            content: { type: 'string', required: true },
            activeForm: { type: 'string', required: true },
            status: { type: 'string', required: true },
          },
        },
      },
    },
    isReadOnly: () => true,
    isConcurrencySafe: () => false,
    validateInput: async input => validateTodos(input.todos),
    async call(input) {
      const normalizedTodos = normalizeTodos(input.todos)
      const oldTodos = await store.get(scopeId)
      const allDone = normalizedTodos.every(todo => todo.status === 'completed')
      await store.set(scopeId, allDone ? [] : normalizedTodos)
      return { old_todos: oldTodos, new_todos: normalizedTodos }
    },
  })
}

function validateTodos(todos: TodoItem[]) {
  if (!Array.isArray(todos)) return Promise.resolve({ result: false as const, message: 'todos must be an array' })
  for (const [index, todo] of todos.entries()) {
    if (!todo || typeof todo !== 'object') {
      return Promise.resolve({ result: false as const, message: `todos[${index}] must be an object` })
    }
    const content = typeof todo.content === 'string' ? todo.content.trim() : ''
    const activeForm = typeof todo.activeForm === 'string' ? todo.activeForm.trim() : ''
    if (!content && !activeForm) {
      return Promise.resolve({ result: false as const, message: `todos[${index}] requires content or activeForm` })
    }
    if (!['pending', 'in_progress', 'completed'].includes(todo.status)) {
      return Promise.resolve({ result: false as const, message: `todos[${index}].status is invalid` })
    }
  }
  return Promise.resolve({ result: true as const })
}

function normalizeTodos(todos: TodoItem[]): TodoItem[] {
  return todos.map(todo => {
    const content = todo.content?.trim() || todo.activeForm?.trim()
    const activeForm = todo.activeForm?.trim() || content
    return { content, activeForm, status: todo.status }
  })
}
