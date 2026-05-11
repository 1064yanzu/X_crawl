/**
 * 动态分配本机可用端口。无外部依赖，避免引入 get-port 之类的包。
 */
import net from "node:net";

export async function pickPort(preferred?: number): Promise<number> {
  if (preferred && (await isFree(preferred))) {
    return preferred;
  }
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen({ host: "127.0.0.1", port: 0 }, () => {
      const addr = srv.address();
      if (typeof addr === "object" && addr) {
        const port = addr.port;
        srv.close(() => resolve(port));
      } else {
        srv.close();
        reject(new Error("无法分配端口"));
      }
    });
  });
}

function isFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => {
      srv.close(() => resolve(true));
    });
    srv.listen({ host: "127.0.0.1", port });
  });
}

export async function waitForHttp(
  url: string,
  timeoutMs: number,
  intervalMs = 300
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const ok = await probe(url);
      if (ok) return;
    } catch {
      /* ignore */
    }
    await sleep(intervalMs);
  }
  throw new Error(`等待 ${url} 超时 (${timeoutMs}ms)`);
}

function probe(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const parsed = new URL(url);
    const req = require("node:http").request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname,
        method: "GET",
        timeout: 2000,
      },
      (res: { statusCode?: number }) => {
        const code = res.statusCode ?? 0;
        resolve(code >= 200 && code < 500);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
