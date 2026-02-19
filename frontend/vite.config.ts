import path from "path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import electron from "vite-plugin-electron/simple";

export default defineConfig(({ mode }) => {
  const isElectron = mode !== "web";

  return {
    plugins: [
      react(),
      isElectron &&
        electron({
          main: {
            entry: "electron/main.ts",
            vite: {
              build: {
                outDir: "dist/electron",
                // @ts-expect-error rolldownOptions is the Vite 7 replacement for rollupOptions; vite-plugin-electron types lag behind
                rolldownOptions: {
                  external: ["electron"],
                },
              },
            },
          },
          preload: {
            input: "electron/preload.ts",
            vite: {
              build: {
                outDir: "dist/electron",
              },
            },
          },
        }),
    ].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    base: isElectron ? "./" : "/",
    build: {
      outDir: "dist/renderer",
      emptyOutDir: true,
    },
    server: {
      port: 3000,
      fs: {
        allow: [path.resolve(__dirname, "..")],
      },
      proxy: {
        "/api/langgraph": {
          target: "http://localhost:2024",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/langgraph/, ""),
        },
        "/api": {
          target: "http://localhost:8001",
          changeOrigin: true,
        },
      },
    },
    css: {
      postcss: "./postcss.config.js",
    },
  };
});
