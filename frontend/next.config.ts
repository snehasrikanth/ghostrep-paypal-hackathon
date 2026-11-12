import type { NextConfig } from "next";
import { existsSync, readFileSync } from "node:fs";
import { parseEnv } from "node:util";

// Read only this copy’s public API URL; backend secrets never enter Next config.
const rootEnv = existsSync("../.env") ? parseEnv(readFileSync("../.env", "utf8")) : {};

const nextConfig: NextConfig = {
  distDir: process.env.GHOSTREP_NEXT_DIST || ".next",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || rootEnv.NEXT_PUBLIC_API_URL || "http://localhost:8100",
    // Public Sandbox client ID only. The standard v6 checkout uses public client-ID authentication.
    NEXT_PUBLIC_PAYPAL_CLIENT_ID:
      process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID || rootEnv.NEXT_PUBLIC_PAYPAL_CLIENT_ID || rootEnv.PAYPAL_CLIENT_ID || "",
  },
  cacheComponents: false,
};

export default nextConfig;
