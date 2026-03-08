"use client";

export function ConfigRow({
    label,
    description,
    value,
    onChange,
    min,
    max,
    step = 0.5,
    unit = "秒",
}: {
    label: string;
    description: string;
    value: number;
    onChange: (v: number) => void;
    min: number;
    max: number;
    step?: number;
    unit?: string;
}) {
    return (
        <div className="flex flex-col gap-3 border-b border-border/50 py-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
                <p className="mt-1 text-[11px] text-muted-foreground/80">范围 {min} - {max} {unit}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
                <input
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    onChange={(e) => onChange(parseFloat(e.target.value) || min)}
                    className="h-11 w-28 rounded-xl border border-input bg-background px-3 text-right font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <span className="min-w-10 text-xs text-muted-foreground">{unit}</span>
            </div>
        </div>
    );
}
