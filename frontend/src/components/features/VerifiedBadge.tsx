"use client";
import * as React from "react";
import { cn } from "@/lib/utils";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>;

interface VerifiedBadgeProps {
    author: AnyRecord;
    className?: string;
}

/**
 * X/微博 通用认证徽标组件。
 *
 * X (Twitter):
 * - 蓝勾 (is_blue_verified): 蓝色勾
 * - 官方认证 (verified + verified_type): 金色勾
 * - 关联标签 (affiliate_label): 灰色机器人标识
 *
 * 微博:
 * - 黄V (个人认证): #FAAD14 金色勾
 * - 蓝V (企业/媒体/机构): 蓝色勾
 */
export function VerifiedBadge({ author, className }: VerifiedBadgeProps) {
    if (!author) return null;

    const platform = author.platform || "";
    const isWeibo = platform === "weibo" || !!author.profile_url?.includes("weibo.com");

    if (isWeibo) {
        return <WeiboBadge author={author} className={className} />;
    }
    return <XBadge author={author} className={className} />;
}

/** X/Twitter 认证徽标 */
function XBadge({ author, className }: VerifiedBadgeProps) {
    const isBlue = author.is_blue_verified;
    const isVerified = author.verified;
    const verifiedType = author.verified_type || "";
    const affiliateLabel = author.affiliate_label || "";
    const proType = author.professional_type || "";

    if (!isBlue && !isVerified && !affiliateLabel) return null;

    // 官方认证（Government/Business 的 verified 账号）用金色
    const isGold = isVerified && (verifiedType === "Business" || verifiedType === "Government");
    // 灰色：关联标签（自动化账号）
    const isGray = !!affiliateLabel && !isBlue && !isVerified;

    let fillColor = "fill-blue-500"; // 默认蓝色
    let tooltip = "蓝标认证";

    if (isGold) {
        fillColor = "fill-amber-500";
        tooltip = `官方认证 (${verifiedType})`;
    } else if (isGray) {
        fillColor = "fill-muted-foreground";
        tooltip = affiliateLabel;
    } else if (isBlue) {
        tooltip = proType ? `蓝标认证 · ${proType}` : "蓝标认证";
    } else if (isVerified) {
        tooltip = "已认证";
    }

    return (
        <svg
            viewBox="0 0 24 24"
            aria-label={tooltip}
            className={cn("w-4 h-4 shrink-0", fillColor, className)}
        >
            <title>{tooltip}</title>
            <g>
                <path d="M22.5 12.5c0-1.58-.875-2.95-2.148-3.6.154-.435.238-.905.238-1.4 0-2.21-1.71-3.998-3.918-3.998-.47 0-.92.084-1.336.25C14.818 2.415 13.51 1.5 12 1.5s-2.816.917-3.337 2.25c-.416-.165-.866-.25-1.336-.25-2.21 0-3.918 1.792-3.918 4 0 .495.084.965.238 1.4-1.273.65-2.148 2.02-2.148 3.6 0 1.46.827 2.76 2.044 3.4-.144.42-.224.87-.224 1.33 0 2.21 1.71 4 3.918 4 .47 0 .92-.086 1.336-.25.52 1.33 1.828 2.25 3.337 2.25s2.816-.917 3.337-2.25c.416.164.866.25 1.336.25 2.21 0 3.918-1.792 3.918-4 0-.46-.08-.91-.224-1.33 1.217-.64 2.044-1.94 2.044-3.4zm-13.06 4.312l-3.415-3.414 1.413-1.414 2 2 6.586-6.586 1.414 1.414-8 8z" />
            </g>
        </svg>
    );
}

/** 微博认证徽标 */
function WeiboBadge({ author, className }: VerifiedBadgeProps) {
    const verified = author.verified;
    const verifiedType = author.verified_type || author.verified_type_str || "";
    const verifiedTypeNum = author.verified_type_num ?? author.verified_type ?? -1;
    const verifiedReason = author.verified_reason || "";

    if (!verified) return null;

    // 判断蓝V还是黄V
    const isBlueV =
        verifiedType === "blue" ||
        (typeof verifiedTypeNum === "number" && verifiedTypeNum >= 1);
    const isYellowV =
        verifiedType === "yellow" ||
        (typeof verifiedTypeNum === "number" && verifiedTypeNum === 0);

    let fillColor = "fill-blue-500";
    let label = "微博认证";

    if (isYellowV) {
        fillColor = "fill-amber-500";
        label = verifiedReason ? `黄V: ${verifiedReason}` : "个人认证 (黄V)";
    } else if (isBlueV) {
        fillColor = "fill-blue-500";
        label = verifiedReason ? `蓝V: ${verifiedReason}` : "企业/机构认证 (蓝V)";
    } else if (verifiedReason) {
        label = `认证: ${verifiedReason}`;
    }

    return (
        <svg
            viewBox="0 0 24 24"
            aria-label={label}
            className={cn("w-4 h-4 shrink-0", fillColor, className)}
        >
            <title>{label}</title>
            <g>
                <path d="M22.5 12.5c0-1.58-.875-2.95-2.148-3.6.154-.435.238-.905.238-1.4 0-2.21-1.71-3.998-3.918-3.998-.47 0-.92.084-1.336.25C14.818 2.415 13.51 1.5 12 1.5s-2.816.917-3.337 2.25c-.416-.165-.866-.25-1.336-.25-2.21 0-3.918 1.792-3.918 4 0 .495.084.965.238 1.4-1.273.65-2.148 2.02-2.148 3.6 0 1.46.827 2.76 2.044 3.4-.144.42-.224.87-.224 1.33 0 2.21 1.71 4 3.918 4 .47 0 .92-.086 1.336-.25.52 1.33 1.828 2.25 3.337 2.25s2.816-.917 3.337-2.25c.416.164.866.25 1.336.25 2.21 0 3.918-1.792 3.918-4 0-.46-.08-.91-.224-1.33 1.217-.64 2.044-1.94 2.044-3.4zm-13.06 4.312l-3.415-3.414 1.413-1.414 2 2 6.586-6.586 1.414 1.414-8 8z" />
            </g>
        </svg>
    );
}