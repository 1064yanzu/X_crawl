import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cn } from "@/lib/utils"

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    asChild?: boolean
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link"
    size?: "default" | "sm" | "lg" | "icon"
    isLoading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = "default", size = "default", asChild = false, isLoading, children, ...props }, ref) => {
        const Comp = asChild ? Slot : "button"

        const base =
 "relative inline-flex select-none items-center justify-center whitespace-nowrap font-medium " +
 "transition-[color,background-color,border-color,transform,box-shadow] duration-200 " +
 "[transition-timing-function:cubic-bezier(0.22,1,0.36,1)] " +
 "focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"

        const variants = {
            default:
 "bg-[var(--accent)] text-[var(--accent-contrast)] hover:bg-[var(--accent-strong)] active:translate-y-[0.5px]",
            destructive:
 "bg-[var(--danger)] text-[var(--accent-contrast)] hover:opacity-90 active:translate-y-[0.5px]",
            outline:
 "border border-[var(--line-strong)] bg-transparent text-foreground hover:border-[var(--fg-muted)] hover:bg-[var(--surface-sunk)]",
            secondary:
 "bg-[var(--surface-2)] text-foreground hover:bg-[color:var(--surface-sunk)]",
            ghost:
 "text-[color:var(--fg-muted)] hover:bg-[var(--surface-2)] hover:text-foreground",
            link:
 "text-[var(--accent)] underline-offset-[6px] decoration-[1.5px] hover:underline",
        }

        const sizes = {
            default: "h-10 rounded-md px-4 text-[13px]",
            sm: "h-8 rounded-md px-3 text-[12px]",
            lg: "h-11 rounded-md px-6 text-sm",
            icon: "h-9 w-9 rounded-md",
        }

        return (
            <Comp
                className={cn(base, variants[variant], sizes[size], className)}
                ref={ref}
                disabled={isLoading || props.disabled}
                {...props}
            >
                {isLoading && (
                    <svg
                        className="-ml-1 mr-2 h-3.5 w-3.5 animate-spin text-current"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        aria-hidden
                    >
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                    </svg>
                )}
                {children}
            </Comp>
        )
    }
)
Button.displayName = "Button"

export { Button }
