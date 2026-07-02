/**
 * 启动错误中文映射 —— 不暴露 stack 给用户，按已知错误码给出可执行建议。
 *
 * 完整 stack 仍写入 desktop 日志，用户点"打开日志目录"可看。
 */
import { desktopLogDir } from "./paths";

export interface MappedError {
    title: string;
    message: string;
    detail: string;
}

export function mapStartupError(err: unknown): MappedError {
    const msg = err instanceof Error ? err.message : String(err);
    const lower = msg.toLowerCase();

    const logHint = `\n\n完整日志：${desktopLogDir}`;

    if (lower.includes("eaddrinuse") || lower.includes("port") && lower.includes("in use")) {
        return {
            title: "端口被占用",
            message: "X_crawl 检测到端口被其他进程占用",
            detail: "请关闭占用对应端口的程序后重启，或在系统监视器结束相关进程。" + logHint,
        };
    }
    if (lower.includes("等待") && lower.includes("超时")) {
        return {
            title: "后端启动超时",
            message: "后端服务启动较慢，超过等待时间",
            detail:
                "可能是首次运行解压资源或机器负载较高。建议关闭后重新打开；多次失败请前往日志目录查看具体堆栈。" + logHint,
        };
    }
    if (lower.includes("浏览器") || lower.includes("browser")) {
        return {
            title: "未找到可用浏览器",
            message: "X_crawl 需要 Chrome 或 Edge 才能运行",
            detail: "请先安装 Chrome / Edge / Brave 等 Chromium 内核浏览器后再启动。" + logHint,
        };
    }
    if (lower.includes("frontend") || lower.includes("server.js")) {
        return {
            title: "前端启动失败",
            message: "无法启动桌面端内嵌的 Next.js 服务",
            detail: "应用资源可能损坏，请尝试重新安装。" + logHint,
        };
    }
    return {
        title: "启动失败",
        message: "X_crawl 启动时遇到未预料的错误",
        detail: msg + logHint,
    };
}
