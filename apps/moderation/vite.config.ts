import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@evalnexa/ui/styles': path.resolve(__dirname, '../../packages/ui/src/styles/index.css'),
      '@evalnexa/ui': path.resolve(__dirname, '../../packages/ui/src/index.ts'),
      '@evalnexa/types': path.resolve(__dirname, '../../packages/types/src/index.ts'),
    },
  },
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://localhost:5000', changeOrigin: true },
      '/socket.io': { target: 'http://localhost:5000', ws: true },
    },
  },
});
