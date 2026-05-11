/**
 * 桌面端运行时代理：把 `/xapi/<path>` 转发到后端
 * （后端端口由 Electron 启动时动态分配，通过 XCRAWL_BACKEND_URL 注入）。
 *
 * 开发模式下也可以用：把后端跑在 8000，设 `XCRAWL_BACKEND_URL=http://127.0.0.1:8000`。
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function backendBase(): string {
  return (
    process.env.XCRAWL_BACKEND_URL ||
    process.env.BACKEND_URL ||
 "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

async function forward(req: NextRequest, segments: string[]): Promise<Response> {
  const search = req.nextUrl.search ?? "";
  const target = `${backendBase()}/${segments.join("/")}${search}`;

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: cleanHeaders(req.headers),
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = req.body as unknown as BodyInit;
    init.duplex = "half";
  }

  try {
    const upstream = await fetch(target, init);
    const headers = new Headers();
    upstream.headers.forEach((v, k) => {
      // 一些 hop-by-hop 头不能透传
      if (!["transfer-encoding", "connection", "keep-alive"].includes(k.toLowerCase())) {
        headers.set(k, v);
      }
    });
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return new Response(
      JSON.stringify({ detail: `桌面端代理失败：${msg}`, target }),
      { status: 502, headers: { "content-type": "application/json" } }
    );
  }
}

function cleanHeaders(input: Headers): Headers {
  const out = new Headers();
  input.forEach((v, k) => {
    const lower = k.toLowerCase();
    if (["host", "connection", "content-length"].includes(lower)) return;
    out.set(k, v);
  });
  return out;
}

type Ctx = { params: Promise<{ path?: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  const { path = [] } = await ctx.params;
  return forward(req, path);
}
