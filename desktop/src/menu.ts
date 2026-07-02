/**
 * X_crawl 主菜单（中文 + 跨平台）。
 *
 * - macOS 顶部放应用菜单（系统约定）
 * - Win/Linux 放在窗口菜单栏
 */
import { app, BrowserWindow, Menu, MenuItemConstructorOptions, shell } from "electron";

export function buildAppMenu(opts: {
    onOpenLogDir: () => void;
    onOpenDataDir: () => void;
    onResetWindow: () => void;
}): Menu {
    const isMac = process.platform === "darwin";
    const appName = "X_crawl";

    const macAppMenu: MenuItemConstructorOptions = {
        label: appName,
        submenu: [
            { label: `关于 ${appName}`, role: "about" },
            { type: "separator" },
            { label: "隐藏", accelerator: "Cmd+H", role: "hide" },
            { label: "隐藏其他", accelerator: "Cmd+Alt+H", role: "hideOthers" },
            { label: "全部显示", role: "unhide" },
            { type: "separator" },
            { label: `退出 ${appName}`, accelerator: "Cmd+Q", role: "quit" },
        ],
    };

    const fileMenu: MenuItemConstructorOptions = {
        label: "文件",
        submenu: [
            { label: "打开数据目录", click: () => opts.onOpenDataDir() },
            { label: "打开日志目录", click: () => opts.onOpenLogDir() },
            { type: "separator" },
            isMac ? { label: "关闭窗口", accelerator: "Cmd+W", role: "close" } : { label: "退出", accelerator: "Ctrl+Q", role: "quit" },
        ],
    };

    const editMenu: MenuItemConstructorOptions = {
        label: "编辑",
        submenu: [
            { label: "撤销", role: "undo" },
            { label: "重做", role: "redo" },
            { type: "separator" },
            { label: "剪切", role: "cut" },
            { label: "复制", role: "copy" },
            { label: "粘贴", role: "paste" },
            { label: "全选", role: "selectAll" },
        ],
    };

    const viewMenu: MenuItemConstructorOptions = {
        label: "视图",
        submenu: [
            { label: "重新加载", accelerator: isMac ? "Cmd+R" : "Ctrl+R", role: "reload" },
            { label: "强制刷新", accelerator: isMac ? "Cmd+Shift+R" : "Ctrl+Shift+R", role: "forceReload" },
            { type: "separator" },
            { label: "实际大小", role: "resetZoom" },
            { label: "放大", role: "zoomIn" },
            { label: "缩小", role: "zoomOut" },
            { type: "separator" },
            { label: "全屏切换", role: "togglefullscreen" },
            { label: "重置窗口大小", click: () => opts.onResetWindow() },
        ],
    };

    const windowMenu: MenuItemConstructorOptions = {
        label: "窗口",
        role: "windowMenu",
    };

    const helpMenu: MenuItemConstructorOptions = {
        label: "帮助",
        submenu: [
            {
                label: "项目主页",
                click: () => shell.openExternal("https://github.com/anthropics/claude-code"),
            },
            { type: "separator" },
            { label: "切换开发者工具", role: "toggleDevTools" },
        ],
    };

    const template: MenuItemConstructorOptions[] = isMac
        ? [macAppMenu, fileMenu, editMenu, viewMenu, windowMenu, helpMenu]
        : [fileMenu, editMenu, viewMenu, windowMenu, helpMenu];

    void app;  // 保留参数，未来扩展菜单状态依赖 app
    void BrowserWindow;
    return Menu.buildFromTemplate(template);
}
