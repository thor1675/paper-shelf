import type { NextConfig } from "next";

// 公開版（Vercel）では、ブラウザは API を同じドメインの /api から呼ぶ。
// 別ドメイン（Render）を直接呼ぶと、ログインの Cookie が「ほかのサイトの Cookie」として送られないため。
// API_URL は Next.js のサーバーから見た API の URL（手元の Docker では http://backend:8000）
const apiUrl = process.env.API_URL?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return apiUrl ? [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }] : [];
  },
};

export default nextConfig;
