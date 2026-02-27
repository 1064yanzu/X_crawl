"use client";
import { CrawlerTaskBuilder } from "./CrawlerTaskBuilder";

/**
 * 向后兼容组件：统一入口为 CrawlerTaskBuilder，避免重复实现分叉。
 */
export function SearchForm() {
    return <CrawlerTaskBuilder />;
}

