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
    port: 5174,
    proxy: {
      '/api': { target: 'https://evalnexa.onrender.com', changeOrigin: true, secure: true },
      '/socket.io': { target: 'https://evalnexa.onrender.com', ws: true, changeOrigin: true, secure: true },
    },
  },
});
