import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  // `vite preview` does not inherit server.proxy, so the production bundle
  // would 404 on /api without this.
  preview: {
    port: 4173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
