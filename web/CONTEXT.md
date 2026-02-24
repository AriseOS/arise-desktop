# Ami Web Frontend

Vue 3 + TypeScript + Tailwind CSS SPA for Ami Cloud Backend.

## Tech Stack

- Vue 3.5 + TypeScript
- Tailwind CSS 3.4
- Pinia (state management)
- Vue Router 4 (SPA routing with auth guards)
- Axios (HTTP client with JWT auto-refresh interceptor)
- Vite 5 (build tool, dev server with API proxy)

## Directory Structure

- `src/api/` - API client layer (one file per domain: auth, keys, memory, admin)
- `src/stores/` - Pinia stores (auth store with token management)
- `src/views/` - Page-level Vue components
- `src/router/` - Vue Router config with auth guards
- `src/components/` - Reusable components (empty, ready for extraction)

## Pages

- Login, Register, Forgot Password, Reset Password (guest only)
- Dashboard (memory stats cards)
- My Phrases (list, share, delete)
- Community Phrases (public, sort by popular/recent)
- API Keys (list, create, revoke)
- Settings (profile read-only, password change, sessions, plan display)
- Admin (user management via sub2api, system health - admin only)

## Key Patterns

- API client (`src/api/client.ts`): Axios instance with JWT Bearer injection and 401 auto-refresh
- Auth store: Tokens in localStorage, auto-refresh via interceptor, profile fetched from sub2api on app mount
- Router guards: `meta.requiresAuth` redirects to login, `meta.guest` redirects authenticated users to dashboard
- User data: All user info (username, email, role, status, plan) comes from sub2api via Cloud Backend proxy

## Development

```bash
cd web
npm install
npm run dev     # Dev server at :5173 (proxies /api to :9090)
npm run build   # Production build to dist/
```
