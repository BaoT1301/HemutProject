import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/upload": "http://localhost:8000",
      "/status": "http://localhost:8000",
      "/download": "http://localhost:8000",
      "/jobs": "http://localhost:8000",
    },
  },
});
