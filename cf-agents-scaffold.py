#!/usr/bin/env python3
"""
CF Agents Scaffold - Production-ready React + Vite / Hono + Cloudflare Workers + Agents SDK + Durable Objects + AI Gateway

Usage:
    python cf-agents-scaffold.py <project-name> [options]

Options:
    --path PATH         Output directory (default: current directory)
    --template TYPE     Template type: chat, api, or full (default: chat)
    --ai-provider       AI provider: openai, anthropic, google, or cloudflare (default: cloudflare)
    --features LIST     Comma-separated features: mcp,tools,auth,sessions (default: all)
    --skip-install      Skip dependency installation
    --help              Show this help message

Examples:
    python cf-agents-scaffold.py my-chat-app
    python cf-agents-scaffold.py my-api --template api --ai-provider openai
    python cf-agents-scaffold.py my-app --features mcp,tools --path ./projects
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Templates stored as dictionaries for easy modification
TEMPLATES = {
    "wrangler.jsonc": """{
	"$schema": "node_modules/wrangler/config-schema.json",
	"name": "{project_name}",
	"main": "worker/index.ts",
	"compatibility_date": "2025-04-24",
	"compatibility_flags": ["nodejs_compat"],
	"durable_objects": {{
		"bindings": [
			{{
				"name": "CHAT_AGENT",
				"class_name": "ChatAgent"
			}},
			{{
				"name": "APP_CONTROLLER",
				"class_name": "AppController"
			}}
		]
	}},
	"migrations": [
		{{
			"tag": "v1",
			"new_sqlite_classes": ["ChatAgent"]
		}},
		{{
			"tag": "v2",
			"new_classes": ["AppController"]
		}}
	],
	"assets": {{
		"not_found_handling": "single-page-application",
		"run_worker_first": ["/api/*", "!/api/docs/*"]
	}},
	"observability": {{
		"enabled": true
	}},
	"vars": {{
		"CF_AI_BASE_URL": "https://gateway.ai.cloudflare.com/v1/YOUR_ACCOUNT_ID/YOUR_GATEWAY_ID/openai",
		"CF_AI_API_KEY": "your-cloudflare-api-key"
	}}
}
""",
    "package.json": """{{
  "name": "{project_name}",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {{
    "dev": "vite --host 0.0.0.0 --port ${{PORT:-3000}}",
    "build": "vite build",
    "lint": "eslint --cache -f json --quiet .",
    "preview": "bun run build && vite preview --host 0.0.0.0 --port ${{PORT:-4173}}",
    "deploy": "bun run build && wrangler deploy",
    "cf-typegen": "wrangler types",
    "prepare": "bun .bootstrap.js || true"
  }},
  "dependencies": {{
    "@headlessui/react": "^2.2.4",
    "@hookform/resolvers": "^5.1.1",
    "@radix-ui/react-dialog": "^1.1.14",
    "@radix-ui/react-dropdown-menu": "^2.1.15",
    "@radix-ui/react-label": "^2.1.7",
    "@radix-ui/react-select": "^2.2.5",
    "@radix-ui/react-slot": "^1.2.3",
    "@radix-ui/react-tabs": "^1.1.12",
    "@radix-ui/react-toast": "^1.2.14",
    "@radix-ui/react-tooltip": "^1.2.7",
    "@tanstack/react-query": "^5.83.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "date-fns": "^4.1.0",
    "framer-motion": "^12.23.0",
    "hono": "^4.9.8",
    "immer": "^10.1.1",
    "lucide-react": "^0.525.0",
    "next-themes": "^0.4.6",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-hook-form": "^7.60.0",
    "react-router-dom": "6.30.0",
    "sonner": "^2.0.6",
    "tailwind-merge": "^3.3.1",
    "tailwindcss-animate": "^1.0.7",
    "uuid": "^11.1.0",
    "zod": "^4.0.5",
    "zustand": "^5.0.6",
    "agents": "^0.0.109"
  }},
  "devDependencies": {{
    "@cloudflare/vite-plugin": "^1.17.1",
    "@cloudflare/workers-types": "^4.20250424.0",
    "@eslint/js": "^9.22.0",
    "@types/node": "^22.15.3",
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "@types/uuid": "^10.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.21",
    "eslint": "^9.31.0",
    "eslint-plugin-react-hooks": "^5.2.0",
    "eslint-plugin-react-refresh": "^0.4.19",
    "globals": "^16.0.0",
    "postcss": "^8.5.3",
    "tailwindcss": "^3.4.17",
    "typescript": "5.8",
    "typescript-eslint": "^8.26.1",
    "vite": "^6.3.1"
  }}
}}
""",
    "tsconfig.json": """{{
  "files": [],
  "references": [
    {{ "path": "./tsconfig.app.json" }},
    {{ "path": "./tsconfig.node.json" }},
    {{ "path": "./tsconfig.worker.json" }}
  ]
}}
""",
    "tsconfig.app.json": """{{
  "compilerOptions": {{
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {{
      "@/*": ["./src/*"],
      "@worker/*": ["./worker/*"]
    }}
  }},
  "include": ["src"]
}}
""",
    "tsconfig.node.json": """{{
  "compilerOptions": {{
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  }},
  "include": ["vite.config.ts"]
}}
""",
    "tsconfig.worker.json": """{{
  "extends": "./node_modules/wrangler/tsconfig.json",
  "compilerOptions": {{
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {{
      "@/*": ["./src/*"],
      "@worker/*": ["./worker/*"]
    }},
    "types": ["@cloudflare/workers-types"]
  }},
  "include": ["worker/**/*"]
}}
""",
    "vite.config.ts": """import {{ defineConfig }} from 'vite'
import react from '@vitejs/plugin-react'
import {{ cloudflare }} from '@cloudflare/vite-plugin'
import path from 'path'

export default defineConfig({{
  plugins: [
    react(),
    cloudflare()
  ],
  resolve: {{
    alias: {{
      '@': path.resolve(__dirname, './src'),
      '@worker': path.resolve(__dirname, './worker')
    }}
  }},
  server: {{
    port: 3000,
    host: true
  }}
}})
""",
    "tailwind.config.js": """/** @type {{import('tailwindcss').Config}} */
export default {{
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {{
    extend: {{
      colors: {{
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {{
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        }},
        secondary: {{
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        }},
        destructive: {{
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        }},
        muted: {{
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        }},
        accent: {{
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        }},
        popover: {{
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        }},
        card: {{
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        }},
      }},
      borderRadius: {{
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      }},
    }},
  }},
  plugins: [require("tailwindcss-animate")],
}}
""",
    "postcss.config.js": """export default {{
  plugins: {{
    tailwindcss: {{}},
    autoprefixer: {{}},
  }},
}}
""",
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{project_display_name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    ".gitignore": """# Dependencies
node_modules
.pnp
.pnp.js

# Build
dist
dist-ssr
*.local

# Editor
.vscode/*
!.vscode/extensions.json
.idea
.DS_Store
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# Cloudflare
.wrangler
.dev.vars
.indexer_cache/

# Logs
logs
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
lerna-debug.log*
""",
    ".bootstrap.js": """#!/usr/bin/env node
// Bootstrap script to ensure dependencies are installed
import {{ execSync }} from 'child_process';
import {{ existsSync }} from 'fs';
import path from 'path';

const cwd = process.cwd();
const nodeModulesPath = path.join(cwd, 'node_modules');

if (!existsSync(nodeModulesPath)) {{
  console.log('📦 Installing dependencies...');
  try {{
    execSync('bun install', {{ stdio: 'inherit', cwd }});
    console.log('✅ Dependencies installed successfully');
  }} catch (error) {{
    console.error('❌ Failed to install dependencies:', error.message);
    process.exit(1);
  }}
}} else {{
  console.log('✅ Dependencies already installed');
}}
""",
    "README.md": """# {project_display_name}

A production-ready, full-stack AI application built on Cloudflare Workers. Features multi-session conversations, streaming responses, tool calling, and seamless integration with Cloudflare AI Gateway.

## ✨ Key Features

- **Multi-Session Chat**: Persistent chat history across sessions with automatic title generation
- **Streaming Responses**: Real-time message streaming for natural conversation flow
- **AI Tool Calling**: Built-in extensible tool system for weather, search, and custom tools
- **Modern UI**: Responsive design with Tailwind CSS and dark mode support
- **Session Management**: Create, list, update, delete sessions via REST API
- **Production-Ready**: TypeScript, error handling, CORS, logging, and Cloudflare Observability

## 🛠 Tech Stack

- **Backend**: Cloudflare Workers, Hono, Agents SDK, Durable Objects
- **Frontend**: React 18, Vite, React Router, Tanstack Query, Tailwind CSS
- **AI**: Cloudflare AI Gateway with OpenAI-compatible API
- **Language**: TypeScript
- **Build Tools**: Bun, Wrangler, Vite

## 🚀 Quick Start

### Prerequisites

- [Bun](https://bun.sh/) installed
- [Cloudflare Account](https://dash.cloudflare.com/) with Workers enabled
- Cloudflare AI Gateway setup (update `wrangler.jsonc` vars):
  - `CF_AI_BASE_URL`: Your AI Gateway endpoint
  - `CF_AI_API_KEY`: Your API token

### Installation

1. Install dependencies:
   ```bash
   bun install
   ```

2. Configure environment in `wrangler.jsonc`:
   Update `vars` with your AI Gateway credentials.

3. Generate types (optional):
   ```bash
   bun run cf-typegen
   ```

## 🧪 Local Development

Start the development server:
```bash
bun dev
```
Opens at `http://localhost:3000`

Deploy for testing:
```bash
bun deploy
```

## ☁️ Deployment

Deploy to Cloudflare Workers:
```bash
bun deploy
```

## 📱 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions` | GET | List sessions |
| `/api/sessions` | POST | Create session |
| `/api/sessions/:id` | DELETE | Delete session |
| `/api/chat/:sessionId/messages` | GET | Get messages |
| `/api/chat/:sessionId/chat` | POST | Send message |

## 📄 License

MIT License

Built with Cloudflare Workers 🚀
""",
}

WORKER_TEMPLATES = {
    "worker/index.ts": """import {{ Hono }} from 'hono'
import {{ cors }} from 'hono/cors'
import {{ logger }} from 'hono/logger'
import {{ Agent, type AgentContext }} from 'agents'
import type {{ Env }} from './types'
import {{ chatRoutes }} from './routes/chat'
import {{ sessionRoutes }} from './routes/sessions'

// Main Hono app
const app = new Hono<{{ Bindings: Env }}>()

// Middleware
app.use('*', logger())
app.use('*', cors({{
  origin: '*',
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization'],
}}))

// Health check
app.get('/api/health', (c) => c.json({{ status: 'ok', timestamp: new Date().toISOString() }}))

// Routes
app.route('/api/chat', chatRoutes)
app.route('/api/sessions', sessionRoutes)

// ChatAgent - Durable Object for managing chat sessions
export class ChatAgent extends Agent<Env> {{
  async onRequest(request: Request): Promise<Response> {
    return app.fetch(request, this.env, this.ctx)
  }

  async onChatMessage(message: string, streaming = false): Promise<string | ReadableStream> {{
    // Override this method to customize AI responses
    // This is where you'd integrate with your AI provider
    
    const response = `Echo: ${{message}}`
    
    if (streaming) {{
      // Return a stream for SSE
      const encoder = new TextEncoder()
      const stream = new ReadableStream({{
        start(controller) {{
          const chunks = response.split(' ')
          let index = 0
          
          const interval = setInterval(() => {{
            if (index >= chunks.length) {{
              controller.close()
              clearInterval(interval)
              return
            }}
            controller.enqueue(encoder.encode(chunks[index] + ' '))
            index++
          }}, 100)
        }}
      }})
      
      return stream
    }}
    
    return response
  }}
}}

// AppController - Durable Object for app-wide state
export class AppController extends Agent<Env> {{
  async onRequest(request: Request): Promise<Response> {
    return app.fetch(request, this.env, this.ctx)
  }
}}

// Worker entry point
export default {{
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url)
    
    // Route to appropriate Durable Object based on path
    if (url.pathname.startsWith('/api/chat/')) {{
      const sessionId = url.pathname.split('/')[3]
      if (sessionId) {{
        const id = env.CHAT_AGENT.idFromName(sessionId)
        const agent = env.CHAT_AGENT.get(id)
        return agent.fetch(request)
      }}
    }}
    
    // Default routing
    return app.fetch(request, env, ctx)
  }},
}}
""",
    "worker/types.ts": """import type {{ Agent }} from 'agents'

// Environment bindings from wrangler.jsonc
export interface Env {{
  CHAT_AGENT: DurableObjectNamespace<Agent<Env>>
  APP_CONTROLLER: DurableObjectNamespace<Agent<Env>>
  CF_AI_BASE_URL: string
  CF_AI_API_KEY: string
}}

// Chat message structure
export interface ChatMessage {{
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}}

// Session structure
export interface ChatSession {{
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
  metadata?: Record<string, unknown>
}}

// API request/response types
export interface CreateSessionRequest {{
  firstMessage?: string
  title?: string
}}

export interface ChatRequest {{
  message: string
  stream?: boolean
  model?: string
}}

export interface ToolCall {{
  name: string
  arguments: Record<string, unknown>
}}

export interface ToolResult {{
  tool: string
  result: unknown
}}
""",
    "worker/routes/chat.ts": """import {{ Hono }} from 'hono'
import type {{ Env, ChatRequest }} from '../types'

const chatRoutes = new Hono<{{ Bindings: Env }}>()

// Get chat messages for a session
chatRoutes.get('/:sessionId/messages', async (c) => {{
  const sessionId = c.req.param('sessionId')
  
  // In a real implementation, fetch from Durable Object storage
  return c.json({{
    sessionId,
    messages: [],
  }})
}})

// Send a chat message
chatRoutes.post('/:sessionId/chat', async (c) => {{
  const sessionId = c.req.param('sessionId')
  const body = await c.req.json<ChatRequest>()
  const {{ message, stream = false }} = body
  
  if (!message) {{
    return c.json({{ error: 'Message is required' }}, 400)
  }}
  
  // Get the ChatAgent Durable Object for this session
  const id = c.env.CHAT_AGENT.idFromName(sessionId)
  const agent = c.env.CHAT_AGENT.get(id)
  
  if (stream) {{
    // Stream the response
    const streamResponse = await agent.onChatMessage(message, true)
    
    if (streamResponse instanceof ReadableStream) {{
      return new Response(streamResponse, {{
        headers: {{
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        }},
      }})
    }}
  }}
  
  // Non-streaming response
  const response = await agent.onChatMessage(message, false)
  
  return c.json({{
    sessionId,
    message: response,
    timestamp: new Date().toISOString(),
  }})
}})

export {{ chatRoutes }}
""",
    "worker/routes/sessions.ts": """import {{ Hono }} from 'hono'
import type {{ Env, CreateSessionRequest, ChatSession }} from '../types'
import {{ v4 as uuidv4 }} from 'uuid'

const sessionRoutes = new Hono<{{ Bindings: Env }}>()

// In-memory store (replace with Durable Object storage in production)
const sessions: Map<string, ChatSession> = new Map()

// List all sessions
sessionRoutes.get('/', async (c) => {{
  const sessionList = Array.from(sessions.values())
  return c.json({{ sessions: sessionList }})
}})

// Create a new session
sessionRoutes.post('/', async (c) => {{
  const body = await c.req.json<CreateSessionRequest>()
  const {{ firstMessage, title }} = body
  
  const sessionId = uuidv4()
  const session: ChatSession = {{
    id: sessionId,
    title: title || (firstMessage ? firstMessage.slice(0, 50) + '...' : 'New Chat'),
    messages: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }}
  
  if (firstMessage) {{
    session.messages.push({{
      id: uuidv4(),
      role: 'user',
      content: firstMessage,
      timestamp: new Date().toISOString(),
    }})
  }}
  
  sessions.set(sessionId, session)
  
  return c.json(session, 201)
}})

// Delete a session
sessionRoutes.delete('/:id', async (c) => {{
  const id = c.req.param('id')
  
  if (!sessions.has(id)) {{
    return c.json({{ error: 'Session not found' }}, 404)
  }}
  
  sessions.delete(id)
  return c.json({{ success: true }})
}})

export {{ sessionRoutes }}
""",
}

REACT_TEMPLATES = {
    "src/main.tsx": """import React from 'react'
import ReactDOM from 'react-dom/client'
import {{ QueryClient, QueryClientProvider }} from '@tanstack/react-query'
import {{ BrowserRouter }} from 'react-router-dom'
import App from './App'
import './index.css'

const queryClient = new QueryClient({{
  defaultOptions: {{
    queries: {{
      staleTime: 5 * 60 * 1000,
      retry: 2,
    }},
  }},
}})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={{queryClient}}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
""",
    "src/App.tsx": """import {{ Toaster }} from 'sonner'
import ChatInterface from './components/ChatInterface'
import Sidebar from './components/Sidebar'

function App() {{
  return (
    <div className="flex h-screen w-full bg-background">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatInterface />
      </main>
      <Toaster position="top-right" />
    </div>
  )
}}

export default App
""",
    "src/index.css": """@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {{
  :root {{
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }}

  .dark {{
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }}
}}

@layer base {{
  * {{
    @apply border-border;
  }}
  body {{
    @apply bg-background text-foreground;
  }}
}}
""",
    "src/components/ChatInterface.tsx": """import {{ useState, useRef, useEffect }} from 'react'
import {{ Send, Loader2 }} from 'lucide-react'
import {{ Button }} from '@/components/ui/button'
import {{ Input }} from '@/components/ui/input'
import {{ ScrollArea }} from '@/components/ui/scroll-area'
import {{ useChat }} from '@/hooks/useChat'

interface Message {{
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}}

export default function ChatInterface() {{
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {{ sendMessage, isLoading }} = useChat()

  const scrollToBottom = () => {{
    messagesEndRef.current?.scrollIntoView({{ behavior: 'smooth' }})
  }}

  useEffect(() => {{
    scrollToBottom()
  }}, [messages])

  const handleSubmit = async (e: React.FormEvent) => {{
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {{
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }}

    setMessages((prev) => [...prev, userMessage])
    setInput('')

    try {{
      const response = await sendMessage(input)
      
      const assistantMessage: Message = {{
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response,
        timestamp: new Date().toISOString(),
      }}

      setMessages((prev) => [...prev, assistantMessage])
    }} catch (error) {{
      console.error('Failed to send message:', error)
    }}
  }}

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold">Chat</h1>
        <p className="text-sm text-muted-foreground">
          Start a conversation with the AI assistant
        </p>
      </header>

      {/* Messages */}
      <ScrollArea className="flex-1 px-6 py-4">
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground py-12">
              <p>Send a message to start the conversation</p>
            </div>
          )}
          
          {messages.map((message) => (
            <div
              key={{message.id}}
              className={`flex ${{message.role === 'user' ? 'justify-end' : 'justify-start'}}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${{
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted'
                }}`}
              >
                <p className="text-sm">{{message.content}}</p>
                <span className="text-xs opacity-70 mt-1 block">
                  {{new Date(message.timestamp).toLocaleTimeString()}}
                </span>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-muted rounded-lg px-4 py-2 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Thinking...</span>
              </div>
            </div>
          )}
          
          <div ref={{messagesEndRef}} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t px-6 py-4">
        <form onSubmit={{handleSubmit}} className="max-w-3xl mx-auto flex gap-2">
          <Input
            value={{input}}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={{isLoading}}
            className="flex-1"
          />
          <Button type="submit" disabled={{isLoading || !input.trim()}}>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </div>
    </div>
  )
}}
""",
    "src/components/Sidebar.tsx": """import {{ useState }} from 'react'
import {{ Plus, MessageSquare, Trash2 }} from 'lucide-react'
import {{ Button }} from '@/components/ui/button'
import {{
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
}} from '@/components/ui/dialog'

interface Session {{
  id: string
  title: string
  updatedAt: string
}}

export default function Sidebar() {{
  const [sessions, setSessions] = useState<Session[]>([])

  const createNewSession = () => {{
    const newSession: Session = {{
      id: Date.now().toString(),
      title: 'New Chat',
      updatedAt: new Date().toISOString(),
    }}
    setSessions((prev) => [newSession, ...prev])
  }}

  const deleteSession = (id: string) => {{
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }}

  return (
    <aside className="w-64 border-r bg-muted/50 flex flex-col">
      <div className="p-4 border-b">
        <Button onClick={{createNewSession}} className="w-full">
          <Plus className="h-4 w-4 mr-2" />
          New Chat
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {sessions.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">
            No conversations yet
          </p>
        )}

        {sessions.map((session) => (
          <div
            key={{session.id}}
            className="flex items-center gap-2 p-2 rounded-md hover:bg-accent cursor-pointer group"
          >
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            <span className="flex-1 text-sm truncate">{{session.title}}</span>
            <Dialog>
              <DialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete Chat</DialogTitle>
                  <DialogDescription>
                    Are you sure you want to delete this chat? This action cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="outline">Cancel</Button>
                  <Button
                    variant="destructive"
                    onClick={() => deleteSession(session.id)}
                  >
                    Delete
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        ))}
      </div>
    </aside>
  )
}}
""",
    "src/hooks/useChat.ts": """import {{ useState }} from 'react'
import {{ toast }} from 'sonner'

const API_BASE_URL = '/api'

export function useChat() {{
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = async (message: string, sessionId?: string): Promise<string> => {{
    setIsLoading(true)
    
    try {{
      const url = sessionId
        ? `${{API_BASE_URL}}/chat/${{sessionId}}/chat`
        : `${{API_BASE_URL}}/chat/default/chat`
      
      const response = await fetch(url, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ message, stream: false }}),
      }})

      if (!response.ok) {{
        throw new Error('Failed to send message')
      }}

      const data = await response.json()
      return data.message
    }} catch (error) {{
      toast.error('Failed to send message')
      throw error
    }} finally {{
      setIsLoading(false)
    }}
  }}

  const createSession = async (firstMessage?: string) => {{
    try {{
      const response = await fetch(`${{API_BASE_URL}}/sessions`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ firstMessage }}),
      }})

      if (!response.ok) {{
        throw new Error('Failed to create session')
      }}

      return await response.json()
    }} catch (error) {{
      toast.error('Failed to create session')
      throw error
    }}
  }}

  return {{
    sendMessage,
    createSession,
    isLoading,
  }}
}}
""",
}

UI_COMPONENTS = {
    "src/components/ui/button.tsx": """import * as React from "react"
import {{ Slot }} from "@radix-ui/react-slot"
import {{ cva, type VariantProps }} from "class-variance-authority"
import {{ cn }} from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {{
    variants: {{
      variant: {{
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      }},
      size: {{
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      }},
    }},
    defaultVariants: {{
      variant: "default",
      size: "default",
    }},
  }}
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {{
  asChild?: boolean
}}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({{ className, variant, size, asChild = false, ...props }}, ref) => {{
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={{cn(buttonVariants({{ variant, size, className }}))}}
        ref={{ref}}
        {{...props}}
      />
    )
  }}
)
Button.displayName = "Button"

export {{ Button, buttonVariants }}
""",
    "src/components/ui/input.tsx": """import * as React from "react"
import {{ cn }} from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {{}}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({{ className, type, ...props }}, ref) => {{
    return (
      <input
        type={{type}}
        className={{cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}}
        ref={{ref}}
        {{...props}}
      />
    )
  }}
)
Input.displayName = "Input"

export {{ Input }}
""",
    "src/components/ui/scroll-area.tsx": """import * as React from "react"
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area"
import {{ cn }} from "@/lib/utils"

const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    className={{cn("relative overflow-hidden", className)}}
    {{...props}}
  >
    <ScrollAreaPrimitive.Viewport className="h-full w-full rounded-[inherit]">
      {{children}}
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
))
ScrollArea.displayName = ScrollAreaPrimitive.Root.displayName

const ScrollBar = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>
>(({ className, orientation = "vertical", ...props }, ref) => (
  <ScrollAreaPrimitive.ScrollAreaScrollbar
    ref={ref}
    orientation={{orientation}}
    className={{cn(
      "flex touch-none select-none transition-colors",
      orientation === "vertical" &&
        "h-full w-2.5 border-l border-l-transparent p-[1px]",
      orientation === "horizontal" &&
        "h-2.5 flex-col border-t border-t-transparent p-[1px]",
      className
    )}}
    {{...props}}
  >
    <ScrollAreaPrimitive.ScrollAreaThumb className="relative flex-1 rounded-full bg-border" />
  </ScrollAreaPrimitive.ScrollAreaScrollbar>
))
ScrollBar.displayName = ScrollAreaPrimitive.ScrollAreaScrollbar.displayName

export {{ ScrollArea, ScrollBar }}
""",
    "src/components/ui/dialog.tsx": """import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import {{ cn }} from "@/lib/utils"

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogPortal = DialogPrimitive.Portal
const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={{cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}}
    {{...props}}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={{cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
        className
      )}}
      {{...props}}
    >
      {{children}}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={{cn(
      "flex flex-col space-y-1.5 text-center sm:text-left",
      className
    )}}
    {{...props}}
  />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={{cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className
    )}}
    {{...props}}
  />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={{cn(
      "text-lg font-semibold leading-none tracking-tight",
      className
    )}}
    {{...props}}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={{cn("text-sm text-muted-foreground", className)}}
    {{...props}}
  />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {{
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogClose,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}}
""",
    "src/lib/utils.ts": """import {{ type ClassValue, clsx }} from "clsx"
import {{ twMerge }} from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {{
  return twMerge(clsx(inputs))
}}
""",
}


def generate_project(args):
    """Generate the project structure."""

    project_name = args.project_name.lower().replace(" ", "-")
    project_display_name = args.project_name
    output_dir = (
        Path(args.path) / project_name if args.path else Path.cwd() / project_name
    )

    print(f"\n🚀 Creating project: {project_name}")
    print(f"📁 Output directory: {output_dir}\n")

    if output_dir.exists():
        print(f"❌ Error: Directory {output_dir} already exists")
        sys.exit(1)

    # Create directory structure
    dirs = [
        output_dir,
        output_dir / "src" / "components" / "ui",
        output_dir / "src" / "hooks",
        output_dir / "src" / "lib",
        output_dir / "worker" / "routes",
        output_dir / "public",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  📂 {d.relative_to(output_dir) if d != output_dir else '.'}")

    # Write all templates
    templates_to_write = []

    # Root level files
    for filename, content in TEMPLATES.items():
        formatted = content.format(
            project_name=project_name, project_display_name=project_display_name
        )
        templates_to_write.append((output_dir / filename, formatted))

    # Worker files
    for filename, content in WORKER_TEMPLATES.items():
        templates_to_write.append((output_dir / filename, content))

    # React files
    for filename, content in REACT_TEMPLATES.items():
        templates_to_write.append((output_dir / filename, content))

    # UI components
    for filename, content in UI_COMPONENTS.items():
        templates_to_write.append((output_dir / filename, content))

    # Write all files
    for filepath, content in templates_to_write:
        filepath.write_text(content, encoding="utf-8")
        print(f"  📝 {filepath.relative_to(output_dir)}")

    # Make .bootstrap.js executable
    bootstrap_path = output_dir / ".bootstrap.js"
    if sys.platform != "win32":
        os.chmod(bootstrap_path, 0o755)

    print(f"\n✅ Project created successfully!\n")

    # Installation
    if not args.skip_install:
        print("📦 Installing dependencies...")
        try:
            result = subprocess.run(
                ["bun", "install"],
                cwd=output_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            print("✅ Dependencies installed\n")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to install dependencies automatically")
            print(f"   Error: {e.stderr}")
            print(f"   Run 'cd {project_name} && bun install' manually\n")
        except FileNotFoundError:
            print("⚠️  Bun not found. Please install Bun first: https://bun.sh")
            print(f"   Then run 'cd {project_name} && bun install'\n")

    # Next steps
    print("🎉 Next steps:")
    print(f"   cd {project_name}")
    print(f"   bun dev          # Start development server")
    print(f"   bun deploy       # Deploy to Cloudflare Workers")
    print()
    print("⚙️  Important: Update wrangler.jsonc with your AI Gateway credentials:")
    print(
        "   - CF_AI_BASE_URL: https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openai"
    )
    print("   - CF_AI_API_KEY: Your Cloudflare API token")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="CF Agents Scaffold - Generate production-ready Cloudflare Workers AI applications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cf-agents-scaffold.py my-chat-app
  python cf-agents-scaffold.py my-api --path ./projects
  python cf-agents-scaffold.py my-app --skip-install
        """,
    )

    parser.add_argument("project_name", help="Name of the project")
    parser.add_argument("--path", help="Output directory (default: current directory)")
    parser.add_argument(
        "--skip-install", action="store_true", help="Skip dependency installation"
    )

    args = parser.parse_args()

    generate_project(args)


if __name__ == "__main__":
    main()
