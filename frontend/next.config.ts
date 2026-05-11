import type { NextConfig } from "next";

// 桌面端通过 src/app/xapi/[...path]/route.ts 做运行时代理；
// 这里的 rewrites 用于「next dev / next start」模式，把 /xapi 转发给本地后端。
// 注意 destination 是 build-time 固化的，桌面端打包不再依赖它。
const BACKEND_URL =
  process.env.XCRAWL_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // 桌面端启动时由 Route Handler 处理 /xapi，无需 rewrites
  // 开发模式（npm run dev）仍可通过环境变量切换
  async rewrites() {
    if (process.env.XCRAWL_DESKTOP === "1") {
      return [];
    }
    return [
      {
        source: "/xapi/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
