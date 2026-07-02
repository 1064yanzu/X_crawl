/**
 * 极简 HTML 净化：用于 YouTube 评论文本里 Google 已转义后的 `<a>` / `<br>` 标签。
 *
 * 策略（白名单 + 转义所有其它内容）：
 *   - 仅放行 `<a href="...">...</a>` 与 `<br>` / `<br/>`
 *   - `<a>` 的 href 必须以 http:// / https:// / mailto: / # 开头，且不含换行
 *   - 其它一切标签（含 `<script>`、`<img>`、事件属性）按字面文本转义渲染
 *
 * 不引第三方依赖：dompurify 需要 window 且增加打包体积；YouTube API 文本结构稳定，
 * 此处用 ~30 行白名单完全够用、可在 SSR 阶段安全执行。
 */

function escapeText(s: string): string {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

const SAFE_HREF = /^(https?:\/\/|mailto:|#)[^\s"'<>]+$/i;

export function sanitizeReplyHtml(input: string): string {
    if (!input) return "";
    const tokens: string[] = [];
    let i = 0;
    const src = input;
    while (i < src.length) {
        const lt = src.indexOf("<", i);
        if (lt === -1) {
            tokens.push(escapeText(src.slice(i)));
            break;
        }
        if (lt > i) tokens.push(escapeText(src.slice(i, lt)));

        // 尝试匹配 <br>, <br/>, <br />
        const brMatch = src.slice(lt).match(/^<br\s*\/?>/i);
        if (brMatch) {
            tokens.push("<br>");
            i = lt + brMatch[0].length;
            continue;
        }

        // 尝试匹配 <a href="..."> ... </a>
        const aOpen = src.slice(lt).match(/^<a\b([^>]*)>/i);
        if (aOpen) {
            const attrs = aOpen[1];
            const hrefMatch = attrs.match(/\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')/i);
            const closeIdx = src.toLowerCase().indexOf("</a>", lt);
            if (hrefMatch && closeIdx !== -1) {
                const rawHref = (hrefMatch[1] ?? hrefMatch[2] ?? "").trim();
                const inner = src.slice(lt + aOpen[0].length, closeIdx);
                const safeInner = sanitizeReplyHtml(inner);  // 递归处理 <br>
                if (SAFE_HREF.test(rawHref)) {
                    tokens.push(
                        `<a href="${escapeText(rawHref)}" target="_blank" rel="noopener noreferrer">${safeInner}</a>`,
                    );
                } else {
                    tokens.push(safeInner);
                }
                i = closeIdx + 4;
                continue;
            }
        }

        // 其它一切：把这个 < 当作纯字符转义
        tokens.push("&lt;");
        i = lt + 1;
    }
    return tokens.join("");
}
