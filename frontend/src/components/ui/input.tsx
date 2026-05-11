import * as React from "react"
import { cn } from "@/lib/utils"

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ className, type, ...props }, ref) => {
        return (
            <input
                type={type}
                className={cn(
 "flex h-10 w-full border-b border-[var(--line-strong)] bg-transparent px-1 py-2 text-sm",
 "transition-[border-color,box-shadow] duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
 "placeholder:text-[color:var(--fg-subtle)]",
 "hover:border-[color:var(--fg-muted)]",
 "focus-visible:border-[var(--accent)] focus-visible:outline-none focus-visible:[box-shadow:inset_0_-1px_0_0_var(--accent)]",
 "disabled:cursor-not-allowed disabled:opacity-50",
 "file:border-0 file:bg-transparent file:text-sm file:font-medium",
                    className,
                )}
                ref={ref}
                {...props}
            />
        )
    }
)
Input.displayName = "Input"

export { Input }
