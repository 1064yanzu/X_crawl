"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type SelectFieldOption<T extends string> = { value: T; label: string; hint?: string };

export function SelectField<T extends string>({
    label,
    value,
    options,
    onChange,
}: {
    label: string;
    value: T;
    options: SelectFieldOption<T>[];
    onChange: (value: T) => void;
}) {
    return (
        <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{label}</span>
            <select
                value={value}
                onChange={(event) => onChange(event.target.value as T)}
                className={cn(
                    "h-11 rounded-xl border border-border/60 bg-background px-3 text-sm",
                    "focus:border-primary/40 focus:ring-2 focus:ring-primary/20",
                )}
            >
                {options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                        {opt.label}
                    </option>
                ))}
            </select>
        </label>
    );
}
