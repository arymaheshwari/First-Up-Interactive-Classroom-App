import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'production' ? '/admin/' : '/',
  server: {
    // T9: the shared theme lives in ../shared. Setting allow replaces Vite's default list,
    // so the app root stays in it.
    fs: { allow: ['.', '../shared'] },
    port: 5175,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
}));
