/**
 * Renderer simple de markdown para enunciados de TPs y otros textos largos.
 *
 * Usa `react-markdown` + `remark-gfm` (tablas, strikethrough, task lists, etc.).
 * No depende de `@tailwindcss/typography`: aplicamos estilos manuales con
 * selectores de Tailwind sobre el wrapper, así no introducimos plugins nuevos.
 *
 * Seguridad: react-markdown NO renderiza HTML embebido por default — escapea
 * cualquier `<script>` o atributo peligroso. Si en el futuro alguien habilita
 * `rehype-raw`, revisar XSS.
 */
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface Props {
  content: string
  className?: string
}

const proseClasses = [
  "text-sm",
  "leading-relaxed",
  "[&>*+*]:mt-2",
  "[&_h1]:text-lg",
  "[&_h1]:font-semibold",
  "[&_h1]:mt-4",
  "[&_h2]:text-base",
  "[&_h2]:font-semibold",
  "[&_h2]:mt-3",
  "[&_h3]:text-sm",
  "[&_h3]:font-semibold",
  "[&_h3]:mt-3",
  "[&_p]:my-2",
  "[&_ul]:list-disc",
  "[&_ul]:pl-5",
  "[&_ol]:list-decimal",
  "[&_ol]:pl-5",
  "[&_li]:my-1",
  "[&_a]:text-accent-brand",
  "[&_a]:underline",
  "[&_a:hover]:text-accent-brand-deep",
  "[&_strong]:font-semibold",
  "[&_em]:italic",
  "[&_blockquote]:border-l-4",
  "[&_blockquote]:border-border-strong",
  "[&_blockquote]:pl-3",
  "[&_blockquote]:italic",
  "[&_blockquote]:text-muted",
  "[&_table]:w-full",
  "[&_table]:border-collapse",
  "[&_th]:border",
  "[&_th]:border-border",
  "[&_th]:px-2",
  "[&_th]:py-1",
  "[&_th]:bg-surface-alt",
  "[&_th]:text-ink",
  "[&_td]:border",
  "[&_td]:border-border",
  "[&_td]:px-2",
  "[&_td]:py-1",
  "[&_hr]:my-3",
  "[&_hr]:border-border-soft",
].join(" ")

export function MarkdownRenderer({ content, className }: Props) {
  return (
    <div className={`${proseClasses} ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Override code para distinguir bloque vs inline.
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className ?? "")
            return match ? (
              <pre className="bg-sidebar-bg text-sidebar-text p-3 rounded-md text-xs overflow-x-auto font-mono">
                <code {...props}>{children}</code>
              </pre>
            ) : (
              <code
                className="bg-surface-alt text-ink px-1.5 py-0.5 rounded text-[0.8em] font-mono border border-border-soft"
                {...props}
              >
                {children}
              </code>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
