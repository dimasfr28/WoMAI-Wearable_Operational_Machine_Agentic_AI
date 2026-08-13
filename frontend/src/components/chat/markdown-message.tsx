"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

const components: Components = {
  p: ({ className, ...props }) => (
    <p
      className={cn("text-sm leading-relaxed", className)}
      {...props}
    />
  ),
  a: ({ className, ...props }) => (
    <a
      className={cn(
        "font-medium underline underline-offset-2 hover:text-primary",
        className,
      )}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      className={cn("list-disc space-y-1 pl-5 text-sm leading-relaxed", className)}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn(
        "list-decimal space-y-1 pl-5 text-sm leading-relaxed",
        className,
      )}
      {...props}
    />
  ),
  li: ({ className, ...props }) => (
    <li className={cn("leading-relaxed", className)} {...props} />
  ),
  h1: ({ className, ...props }) => (
    <h1 className={cn("text-base font-semibold", className)} {...props} />
  ),
  h2: ({ className, ...props }) => (
    <h2 className={cn("text-base font-semibold", className)} {...props} />
  ),
  h3: ({ className, ...props }) => (
    <h3 className={cn("text-sm font-semibold", className)} {...props} />
  ),
  strong: ({ className, ...props }) => (
    <strong className={cn("font-semibold", className)} {...props} />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "border-l-2 border-muted-foreground/30 pl-3 text-sm italic text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  code: ({ className, ...props }) => (
    <code
      className={cn(
        "rounded bg-muted px-1 py-0.5 font-mono text-xs",
        className,
      )}
      {...props}
    />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("border-muted-foreground/20", className)} {...props} />
  ),
  table: ({ className, ...props }) => (
    <div className="overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-sm", className)}
        {...props}
      />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        "border border-muted-foreground/20 px-2 py-1 text-left font-semibold",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td
      className={cn("border border-muted-foreground/20 px-2 py-1", className)}
      {...props}
    />
  ),
};

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
