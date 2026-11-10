import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

// li の先頭（"- [ ] ..." の位置）にあるチェックの状態を反転した Markdown を返す
export function toggleTask(source: string, offset: number): string {
  const rest = source.slice(offset);
  const m = rest.match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\]/);
  if (!m) return source;
  const mark = m[2] === " " ? "x" : " ";
  return source.slice(0, offset) + `${m[1]}[${mark}]` + rest.slice(m[0].length);
}

// メモの表示用。HTML の直書きは react-markdown の既定で無効（<script> などは実行されない）
// onChange を渡すとチェックボックスが押せるようになり、書き換え後の Markdown を受け取れる
export default function Markdown({
  children,
  onChange,
}: {
  children: string;
  onChange?: (next: string) => void;
}) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          // HTML の直書きは無効なので、input が出てくるのはチェックリストだけ
          input: ({ type, checked }) =>
            type === "checkbox" ? (
              <input
                type="checkbox"
                checked={!!checked}
                disabled={!onChange}
                // 実際の書き換えは li の onClick で行う
                onChange={() => {}}
                className={onChange ? "cursor-pointer" : undefined}
              />
            ) : null,
          li: ({ node, ...props }) => {
            const offset = node?.position?.start.offset;
            if (!onChange || offset === undefined) return <li {...props} />;
            return (
              <li
                {...props}
                onClick={(e) => {
                  const target = e.target as HTMLElement;
                  // 入れ子のリストでは、押したチェックボックスに一番近い li だけが反応する
                  if (target instanceof HTMLInputElement && target.type === "checkbox" &&
                      target.closest("li") === e.currentTarget) {
                    onChange(toggleTask(children, offset));
                  }
                }}
              />
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
