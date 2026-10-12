import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy all /api/* requests to the FastAPI backend in dev.
      "/api": {
        target: "http://localhost:7779",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Private modules (src/admin/private/) become /admin/chunks/*.js (+ .map), a path the Vercel
        // middleware password-gates. Everything else keeps the default public /assets/ names.
        chunkFileNames: (chunk) =>
          chunk.facadeModuleId?.includes("/src/admin/private/") ? "admin/chunks/[name]-[hash].js" : "assets/[name]-[hash].js",
      },
    },
  },
});
