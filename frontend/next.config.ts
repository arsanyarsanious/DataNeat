import type { NextConfig } from "next";
const cloudflareExport = process.env.CLOUDFLARE_EXPORT === "1";
const config: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  ...(cloudflareExport
    ? { output: "export" as const }
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/:path*`,
            },
          ];
        },
      }),
};
export default config;
