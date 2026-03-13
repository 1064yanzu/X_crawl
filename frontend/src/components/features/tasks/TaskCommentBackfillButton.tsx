"use client";

import { Loader2, MessageCircleMore } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TaskCommentBackfillButton({
    loading,
    disabled,
    onClick,
    className,
    variant = "outline",
    size = "sm",
    fullWidth = false,
}: {
    loading: boolean;
    disabled?: boolean;
    onClick: () => void;
    className?: string;
    variant?: "default" | "outline" | "ghost";
    size?: "sm" | "default";
    fullWidth?: boolean;
}) {
    return (
        <Button
            variant={variant}
            size={size}
            className={className}
            disabled={disabled || loading}
            onClick={onClick}
        >
            {loading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <MessageCircleMore className="mr-1.5 h-3.5 w-3.5" />}
            <span className={fullWidth ? "truncate" : ""}>补采评论（2级）</span>
        </Button>
    );
}
