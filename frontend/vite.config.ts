import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // polling agar hot reload jalan di bind mount Docker (Windows)
    watch: { usePolling: true, interval: 300 },
  },
});
