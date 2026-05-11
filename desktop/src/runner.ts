/**
 * 后端 / 前端子进程管理：spawn + 健康检查 + 优雅退出。
 */
import { spawn, ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { backendExe, backendDir, frontendServer, frontendDir, dataDir, desktopLogDir } from "./paths";
import { waitForHttp } from "./port";

let backendProc: ChildProcess | null = null;
let frontendProc: ChildProcess | null = null;

function openLog(filename: string): number {
  const fp = path.join(desktopLogDir, filename);
  return fs.openSync(fp, "a");
}

export async function startBackend(port: number): Promise<void> {
  if (!fs.existsSync(backendExe)) {
    throw new Error(`后端可执行文件不存在：${backendExe}`);
  }
  const out = openLog("backend.stdout.log");
  const err = openLog("backend.stderr.log");

  backendProc = spawn(backendExe, [], {
    cwd: backendDir,
    env: {
      ...process.env,
      XCRAWL_DATA_DIR: dataDir,
      XCRAWL_PORT: String(port),
      XCRAWL_HOST: "127.0.0.1",
    },
    stdio: ["ignore", out, err],
    windowsHide: true,
  });

  backendProc.on("exit", (code, signal) => {
    console.log(`[backend] exited code=${code} signal=${signal}`);
    backendProc = null;
  });

  await waitForHttp(`http://127.0.0.1:${port}/docs`, 60_000);
}

export async function startFrontend(port: number, backendPort: number): Promise<void> {
  if (!fs.existsSync(frontendServer)) {
    throw new Error(`前端 server.js 不存在：${frontendServer}`);
  }
  const out = openLog("frontend.stdout.log");
  const err = openLog("frontend.stderr.log");

  frontendProc = spawn(process.execPath, [frontendServer], {
    cwd: frontendDir,
    env: {
      ...process.env,
      NODE_ENV: "production",
      ELECTRON_RUN_AS_NODE: "1",
      PORT: String(port),
      HOSTNAME: "127.0.0.1",
      XCRAWL_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
    },
    stdio: ["ignore", out, err],
    windowsHide: true,
  });

  frontendProc.on("exit", (code, signal) => {
    console.log(`[frontend] exited code=${code} signal=${signal}`);
    frontendProc = null;
  });

  await waitForHttp(`http://127.0.0.1:${port}/`, 30_000);
}

export async function stopAll(): Promise<void> {
  const kills: Promise<void>[] = [];
  if (backendProc) kills.push(killProc(backendProc, "backend"));
  if (frontendProc) kills.push(killProc(frontendProc, "frontend"));
  await Promise.all(kills);
}

function killProc(proc: ChildProcess, label: string): Promise<void> {
  return new Promise((resolve) => {
    if (proc.exitCode !== null || proc.signalCode) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      console.warn(`[${label}] SIGTERM 后 5s 未退出，发送 SIGKILL`);
      try {
        proc.kill("SIGKILL");
      } catch {
        /* ignore */
      }
      resolve();
    }, 5000);

    proc.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });

    try {
      proc.kill("SIGTERM");
    } catch {
      clearTimeout(timer);
      resolve();
    }
  });
}
