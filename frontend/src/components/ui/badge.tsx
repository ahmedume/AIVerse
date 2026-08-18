// src/components/ui/badge.tsx — badge primitive.

import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        success: "border-transparent bg-emerald-600 text-white",
        danger: "border-transparent bg-red-600 text-white",
        warning: "border-transparent bg-amber-500 text-black",
        outline: "text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export function verdictBadge(score: number) {
  if (score >= 70) return { label: "AI", variant: "danger" as const };
  if (score >= 40) return { label: "Mixed", variant: "warning" as const };
  return { label: "Human", variant: "success" as const };
}