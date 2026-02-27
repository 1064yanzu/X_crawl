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
        <div className="flex items-center justify-between gap-4 border-b py-3 last:border-0">
            <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
                <input
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    onChange={(e) => onChange(parseFloat(e.target.value) || min)}
                    className="h-8 w-24 rounded-md border border-input bg-background px-2 text-right font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <span className="w-10 text-xs text-muted-foreground">{unit}</span>
            </div>
        </div>
    );
}

