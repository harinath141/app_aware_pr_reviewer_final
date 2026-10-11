import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// root is the directory holding this config, so outDir resolves the same way whether the build
// runs from frontend/ on the host or from /src/frontend in the Docker build stage.
const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  root,
  // Served from the origin root, matching the FastAPI "/" route. A different base would make the
  // emitted index.html request /<base>/assets/*.js, which FastAPI has no route for - the page
  // then loads blank with "Failed to load module script", which looks like a React bug.
  base: '/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../app/static',
    // outDir sits outside root, so Vite's default (empty only when inside root) would leave stale
    // hashed chunks accumulating in app/static/assets forever. app/static is a pure output dir.
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    // Keeps the browser on one origin, so the API needs no CORS middleware. 127.0.0.1 rather than
    // localhost: where localhost resolves to IPv6 first the proxy would hit ::1:8000 while uvicorn
    // is listening on IPv4, giving intermittent ECONNREFUSED.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
