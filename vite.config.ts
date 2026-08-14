import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
    // NOTE: the Gemini API key is NO LONGER used in the browser. All model calls
    // go through the backend (see ../backend). Configure the backend URL with
    // VITE_API_BASE (defaults to http://localhost:8000).
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
      },
      plugins: [react()],
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
