/**
 * 平台注册中心 —— 统一管理所有爬虫平台的元数据
 *
 * 新增平台时只需在 PLATFORMS 数组中追加一条即可，
 * 前端所有按平台分类的 UI 都会自动识别。
 */

export interface PlatformMeta {
  /** 后端 API 使用的平台 ID */
  id: string;
  /** 显示名称 */
  label: string;
  /** 简短描述 */
  description: string;
  /** Lucide 图标名称 (需在组件中映射) */
  iconName: "twitter" | "globe" | "bot" | "rss" | "youtube";
  /** 主题色 Tailwind class */
  color: string;
  /** 背景色 class (浅色) */
  bgLight: string;
  /** 文本色 class */
  textClass: string;
  /** Badge 完整样式 */
  badgeClass: string;
  /** 左侧色条 class */
  barClass: string;
}

export const PLATFORMS: PlatformMeta[] = [
  {
    id: "x",
    label: "𝕏 Twitter",
    description: "X / Twitter 平台爬虫",
    iconName: "twitter",
    color: "blue",
    bgLight: "bg-blue-500/10",
    textClass: "text-blue-600 dark:text-blue-400",
    badgeClass:
 "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    barClass: "bg-blue-500",
  },
  {
    id: "weibo",
    label: "微博",
    description: "新浪微博平台爬虫",
    iconName: "globe",
    color: "orange",
    bgLight: "bg-orange-500/10",
    textClass: "text-orange-600 dark:text-orange-400",
    badgeClass:
 "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    barClass: "bg-orange-500",
  },
  {
    id: "youtube",
    label: "YouTube",
    description: "YouTube 官方 API（Data API v3）",
    iconName: "youtube",
    color: "red",
    bgLight: "bg-red-500/10",
    textClass: "text-red-600 dark:text-red-400",
    badgeClass:
 "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    barClass: "bg-red-500",
  },
];

/** 全部 / 聚合入口的虚拟平台 */
export const ALL_PLATFORM: PlatformMeta = {
  id: "all",
  label: "全部",
  description: "显示所有平台数据",
  iconName: "bot",
  color: "gray",
  bgLight: "bg-muted",
  textClass: "text-foreground",
  badgeClass: "bg-muted text-foreground",
  barClass: "bg-muted-foreground",
};

/**
 * 根据平台 ID 获取元数据（找不到时返回 X 的配置）
 */
export function getPlatformMeta(platformId?: string | null): PlatformMeta {
  if (!platformId) return PLATFORMS[0];
  return PLATFORMS.find((p) => p.id === platformId) ?? PLATFORMS[0];
}

/**
 * 获取带"全部"选项的平台列表
 */
export function getPlatformsWithAll(): PlatformMeta[] {
  return [ALL_PLATFORM, ...PLATFORMS];
}
