import path from "node:path"
import tailwindcss from "file:///C:/alberto/Garis/platform-repo-v1.0.0%20(1)/platform/node_modules/.pnpm/@tailwindcss+vite@4.2.3_vite@6.4.2_jiti@2.6.1_lightningcss@1.32.0_tsx@4.21.0_/node_modules/@tailwindcss/vite/dist/index.mjs"
import { TanStackRouterVite } from "file:///C:/alberto/Garis/platform-repo-v1.0.0%20(1)/platform/node_modules/.pnpm/@tanstack+router-plugin@1.167.22_@tanstack+react-router@1.168.23_react-dom@19.2.5_react@19.2._eu2a7pgpttbrpz3dwneab457za/node_modules/@tanstack/router-plugin/dist/esm/vite.js"
import react from "file:///C:/alberto/Garis/platform-repo-v1.0.0%20(1)/platform/node_modules/.pnpm/@vitejs+plugin-react@4.7.0_vite@6.4.2_jiti@2.6.1_lightningcss@1.32.0_tsx@4.21.0_/node_modules/@vitejs/plugin-react/dist/index.js"
// vite.config.ts
import { defineConfig } from "file:///C:/alberto/Garis/platform-repo-v1.0.0%20(1)/platform/node_modules/.pnpm/vite@6.4.2_jiti@2.6.1_lightningcss@1.32.0_tsx@4.21.0/node_modules/vite/dist/node/index.js"
var __vite_injected_original_dirname =
  "C:\\alberto\\Garis\\platform-repo-v1.0.0 (1)\\platform\\apps\\web-student"
var vite_config_default = defineConfig({
  plugins: [
    TanStackRouterVite({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
})
export { vite_config_default as default }
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJDOlxcXFxhbGJlcnRvXFxcXEdhcmlzXFxcXHBsYXRmb3JtLXJlcG8tdjEuMC4wICgxKVxcXFxwbGF0Zm9ybVxcXFxhcHBzXFxcXHdlYi1zdHVkZW50XCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCJDOlxcXFxhbGJlcnRvXFxcXEdhcmlzXFxcXHBsYXRmb3JtLXJlcG8tdjEuMC4wICgxKVxcXFxwbGF0Zm9ybVxcXFxhcHBzXFxcXHdlYi1zdHVkZW50XFxcXHZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9DOi9hbGJlcnRvL0dhcmlzL3BsYXRmb3JtLXJlcG8tdjEuMC4wJTIwKDEpL3BsYXRmb3JtL2FwcHMvd2ViLXN0dWRlbnQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tIFwidml0ZVwiXG5pbXBvcnQgcmVhY3QgZnJvbSBcIkB2aXRlanMvcGx1Z2luLXJlYWN0XCJcbmltcG9ydCB0YWlsd2luZGNzcyBmcm9tIFwiQHRhaWx3aW5kY3NzL3ZpdGVcIlxuaW1wb3J0IHsgVGFuU3RhY2tSb3V0ZXJWaXRlIH0gZnJvbSBcIkB0YW5zdGFjay9yb3V0ZXItcGx1Z2luL3ZpdGVcIlxuaW1wb3J0IHBhdGggZnJvbSBcIm5vZGU6cGF0aFwiXG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtcbiAgICBUYW5TdGFja1JvdXRlclZpdGUoeyB0YXJnZXQ6IFwicmVhY3RcIiwgYXV0b0NvZGVTcGxpdHRpbmc6IHRydWUgfSksXG4gICAgcmVhY3QoKSxcbiAgICB0YWlsd2luZGNzcygpLFxuICBdLFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHtcbiAgICAgIFwiQFwiOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCBcIi4vc3JjXCIpLFxuICAgIH0sXG4gIH0sXG4gIHNlcnZlcjoge1xuICAgIHByb3h5OiB7XG4gICAgICBcIi9hcGlcIjoge1xuICAgICAgICB0YXJnZXQ6IHByb2Nlc3MuZW52LlZJVEVfQVBJX1VSTCB8fCBcImh0dHA6Ly9sb2NhbGhvc3Q6ODAwMFwiLFxuICAgICAgICBjaGFuZ2VPcmlnaW46IHRydWUsXG4gICAgICAgIHJld3JpdGU6IChwKSA9PiBwLnJlcGxhY2UoL15cXC9hcGkvLCBcIlwiKSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSxcbiAgYnVpbGQ6IHtcbiAgICBvdXREaXI6IFwiZGlzdFwiLFxuICAgIHNvdXJjZW1hcDogdHJ1ZSxcbiAgfSxcbiAgdGVzdDoge1xuICAgIGVudmlyb25tZW50OiBcImpzZG9tXCIsXG4gICAgZ2xvYmFsczogdHJ1ZSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQTJZLFNBQVMsb0JBQW9CO0FBQ3hhLE9BQU8sV0FBVztBQUNsQixPQUFPLGlCQUFpQjtBQUN4QixTQUFTLDBCQUEwQjtBQUNuQyxPQUFPLFVBQVU7QUFKakIsSUFBTSxtQ0FBbUM7QUFNekMsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUztBQUFBLElBQ1AsbUJBQW1CLEVBQUUsUUFBUSxTQUFTLG1CQUFtQixLQUFLLENBQUM7QUFBQSxJQUMvRCxNQUFNO0FBQUEsSUFDTixZQUFZO0FBQUEsRUFDZDtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTztBQUFBLE1BQ0wsS0FBSyxLQUFLLFFBQVEsa0NBQVcsT0FBTztBQUFBLElBQ3RDO0FBQUEsRUFDRjtBQUFBLEVBQ0EsUUFBUTtBQUFBLElBQ04sT0FBTztBQUFBLE1BQ0wsUUFBUTtBQUFBLFFBQ04sUUFBUSxRQUFRLElBQUksZ0JBQWdCO0FBQUEsUUFDcEMsY0FBYztBQUFBLFFBQ2QsU0FBUyxDQUFDLE1BQU0sRUFBRSxRQUFRLFVBQVUsRUFBRTtBQUFBLE1BQ3hDO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFBQSxFQUNBLE9BQU87QUFBQSxJQUNMLFFBQVE7QUFBQSxJQUNSLFdBQVc7QUFBQSxFQUNiO0FBQUEsRUFDQSxNQUFNO0FBQUEsSUFDSixhQUFhO0FBQUEsSUFDYixTQUFTO0FBQUEsRUFDWDtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
