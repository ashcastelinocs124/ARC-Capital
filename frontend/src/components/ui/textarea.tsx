import * as React from "react";
import { cn } from "@/lib/cn";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text resize-y min-h-[60px]",
        "placeholder:text-muted-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft-2 focus-visible:border-accent",
        "transition-colors",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
