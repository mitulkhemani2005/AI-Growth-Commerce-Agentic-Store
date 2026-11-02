import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { officePlugin } from './officePlugin';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'NOVA_');
  const target = env.NOVA_API_TARGET || 'http://127.0.0.1:8000';
  const proxy = Object.fromEntries(['/api', '/.well-known', '/static'].map(prefix => [
    prefix, { target, changeOrigin: true },
  ]));
  return {
    plugins: [react(), officePlugin()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
    build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 },
  };
});
