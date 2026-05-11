import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * 编辑感 Card 系统
 *
 * 默认 `variant="flat"` — 不带边框、背景、阴影。鼓励用 typography
 * 与分隔线做层级，避免「卡片套娃」。
 *
 * 需要明确的容器感时，显式使用：
 *   - `panel`    单层细线 + surface 底（最常用）
 *   - `outlined` 仅细线，无背景
 *   - `sunken`   略凹陷的二级面，用于输入/数据回显
 */
type CardVariant = "flat" | "panel" | "outlined" | "sunken"

const variantClass: Record<CardVariant, string> = {
    flat: "",
    panel: "border border-[var(--line)] bg-[var(--surface)]",
    outlined: "border border-[var(--line)]",
    sunken: "border border-[var(--line)] bg-[var(--surface-sunk)]",
}

const Card = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & { variant?: CardVariant }
>(({ className, variant = "flat", ...props }, ref) => (
    <div
        ref={ref}
        data-card={variant}
        className={cn("text-foreground", variantClass[variant], className)}
        {...props}
    />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1.5 px-6 pt-6 pb-4", className)} {...props} />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
    HTMLParagraphElement,
    React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
    <h3
        ref={ref}
        className={cn(
 "font-serif text-[1.35rem] font-medium leading-tight tracking-tight text-foreground",
            className,
        )}
        {...props}
    />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
    HTMLParagraphElement,
    React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
    <p
        ref={ref}
        className={cn("text-sm leading-6 text-[color:var(--fg-muted)]", className)}
        {...props}
    />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("px-6 pb-6", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center px-6 pb-6", className)} {...props} />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
