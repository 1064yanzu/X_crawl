/**
 * 桌面端资源路径解析。
 *
 * 开发模式（npm run dev）：
 *   - 后端二进制 = ../backend/dist/xcrawl-backend/xcrawl-backend
 *   - 前端目录   = ../dist-frontend
 *
 * 打包模式（electron-builder 产物）：
 *   - extraResources 指定 backend/ 与 frontend/ → process.resourcesPath
 */
import { app } from "electron";
import path from "node:path";
import fs from "node:fs";

const isPackaged = app.isPackaged;

function repoRoot(): string {
  // dist/main.js → desktop/dist → desktop → repo
  return path.resolve(__dirname, "..", "..");
}

export const backendDir: string = isPackaged
  ? path.join(process.resourcesPath, "backend")
  : path.join(repoRoot(), "backend", "dist", "xcrawl-backend");

export const backendExe: string = path.join(
  backendDir,
  process.platform === "win32" ? "xcrawl-backend.exe" : "xcrawl-backend"
);

export const frontendDir: string = isPackaged
  ? path.join(process.resourcesPath, "frontend")
  : path.join(repoRoot(), "dist-frontend");

export const frontendServer: string = path.join(frontendDir, "server.js");

/** 用户数据根目录：所有可写文件都放这里。 */
export const dataDir: string = path.join(app.getPath("userData"), "data");

export function ensureDataDir(): void {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
}

/** Electron 自身的日志（不是后端日志）。 */
export const desktopLogDir: string = path.join(app.getPath("userData"), "logs");

export function ensureDesktopLogDir(): void {
  if (!fs.existsSync(desktopLogDir)) {
    fs.mkdirSync(desktopLogDir, { recursive: true });
  }
}
