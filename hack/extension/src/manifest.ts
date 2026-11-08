import { defineManifest } from "@crxjs/vite-plugin";

// Dev builds (CRX_FIXTURES=1) also match the local fixture pages so E2E tests
// can drive the content scripts without touching the real platforms.
const fixtureMatches = process.env.CRX_FIXTURES === "1" ? ["http://localhost:8899/*"] : [];

export default defineManifest({
  manifest_version: 3,
  name: "Tomate — trieur de feed",
  version: "0.1.0",
  description: "Un petit bonhomme jette des tomates sur les vidéos hors sujet.",
  permissions: ["storage", "sidePanel", "activeTab", "scripting", "contextMenus"],
  host_permissions: [
    "*://*.youtube.com/*",
    "*://*.tiktok.com/*",
    "*://*.instagram.com/*",
    "http://localhost:8787/*",
    "http://localhost:8790/*",
  ],
  background: { service_worker: "src/sw.ts" },
  side_panel: { default_path: "src/panel/index.html" },
  action: { default_title: "Tomate" },
  web_accessible_resources: [
    { resources: ["fonts/*"], matches: ["<all_urls>"] },
  ],
  content_scripts: [
    {
      matches: [
        "*://*.youtube.com/*",
        "*://*.tiktok.com/*",
        "*://*.instagram.com/*",
        ...fixtureMatches,
      ],
      js: ["src/content/index.ts"],
      run_at: "document_idle",
    },
  ],
});
