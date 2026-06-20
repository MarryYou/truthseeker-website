import { marked } from 'marked';
import katex from 'katex';

// 配置 marked 的渲染器，确保生成的 HTML 链接能安全地在新窗口打开
marked.use({
  gfm: true,
  breaks: true,
  renderer: {
    link(token) {
      const href = token.href || '#';
      const title = token.title ? `title="${token.title}"` : '';
      const text = token.text || '';
      return `<a href="${href}" ${title} target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline underline-offset-4 transition-colors font-medium">${text}</a>`;
    }
  }
});

export const renderMarkdown = (text: string): string => {
  if (!text) return '';

  let processedText = text;

  // 1. 预提取块级公式 $$ ... $$ 和行内公式 $ ... $，避免被 marked 强行转义
  const placeholders: string[] = [];

  const decodeHtmlEntities = (str: string) => {
    return str
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");
  };

  // 匹配块级公式 $$ ... $$ (支持跨行)
  processedText = processedText.replace(/\$\$\s*([\s\S]*?)\s*\$\$/g, (_, math) => {
    try {
      const decodedMath = decodeHtmlEntities(math);
      const html = katex.renderToString(decodedMath, { displayMode: true, throwOnError: false });
      const placeholder = `BLOCKMATHPLACEHOLDER${placeholders.length}`;
      placeholders.push(html);
      return placeholder;
    } catch (e) {
      console.error('[LaTeX Block Error]', e);
      return _;
    }
  });

  // 匹配行内公式 $ ... $ (排除了可能包含 $ 的普通文字和换行，行内公式一般不换行)
  processedText = processedText.replace(/\$(?!\s)([^\$\n]+?)(?<!\s)\$/g, (_, math) => {
    try {
      const decodedMath = decodeHtmlEntities(math);
      const html = katex.renderToString(decodedMath, { displayMode: false, throwOnError: false });
      const placeholder = `INLINEMATHPLACEHOLDER${placeholders.length}`;
      placeholders.push(html);
      return placeholder;
    } catch (e) {
      console.error('[LaTeX Inline Error]', e);
      return _;
    }
  });

  // 0. 解除反引号包裹的 markdown 链接：`[text](url)` → [text](url)
  // Agent 有时会输出带反引号的链接，marked 会解析为内联代码块导致链接不渲染
  processedText = processedText.replace(/`\[([^\]]*)\]\(([^)]*)\)`/g, '[$1]($2)');

  // 0.1 预处理 URL：转义 markdown 链接中的特殊字符，防止解析失败
  // 匹配 [text](url) 中的 url 部分
  processedText = processedText.replace(
    /\[([^\]]*)\]\(([^)]*)\)/g,
    (_, title: string, rawUrl: string) => {
      // 只编码 URL 中的特殊字符，保留已有合法编码
      let safeUrl = rawUrl;
      try {
        // 只对 URL 路径和查询参数中的不安全字符编码
        // 但保留合法结构的字符
        safeUrl = rawUrl.replace(
          /[一-鿿　-〿＀-￯\"<>\\^`{|}~ ]/g,
          (c: string) => encodeURIComponent(c)
        );
      } catch {
        safeUrl = rawUrl;
      }
      return `[${title}](${safeUrl})`;
    }
  );

  // 1. 将裸 URL 转为 markdown 链接（避免被 marked 的链接识别干扰，放在 URL 转义之后）
  processedText = processedText.replace(
    /(?<!\]\()\bhttps?:\/\/[^\s<>"']+(?![^)]*\))/gi,
    (url: string) => {
      // 排除已经是 markdown 链接中的 URL（前面有 [text](）
      const before = url;
      // 截断尾部标点
      const cleanUrl = before.replace(/[。，、！？；：,.!?;:\"\'""''”“]+$/, '');
      return `[${cleanUrl}](${cleanUrl})`;
    }
  );

  // 2. 处理已闭合的 <think>...</think>
  const closedThinkRegex = /<think>([\s\S]*?)<\/think>/gi;
  processedText = processedText.replace(closedThinkRegex, (_, content) => {
    return `<details class="think-container mb-4 bg-slate-800/20 border border-slate-700/30 rounded-xl overflow-hidden transition-all duration-300 shadow-inner"><summary class="think-summary cursor-pointer select-none px-4 py-2 bg-slate-800/40 hover:bg-slate-800/60 text-slate-400 text-xs font-semibold hover:text-slate-300 flex items-center gap-2 list-none outline-none"><span>🤔</span> 思考过程 (点击展开)</summary><div class="think-content px-4 py-3 text-slate-400/80 text-xs leading-relaxed border-t border-slate-700/20 whitespace-pre-wrap font-mono">${content}</div></details>`;
  });

  // 2. 处理流式中未闭合的 <think>
  if (processedText.toLowerCase().includes('<think>')) {
    const parts = processedText.split(/<think>/i);
    const beforeThink = parts[0];
    const thinkContent = parts.slice(1).join('<think>');
    processedText = `${beforeThink}<details open class="think-container mb-4 bg-blue-950/10 border border-blue-800/30 rounded-xl overflow-hidden transition-all duration-300 shadow-inner"><summary class="think-summary cursor-pointer select-none px-4 py-2 bg-blue-950/30 text-blue-400 text-xs font-semibold flex items-center gap-2 list-none outline-none"><span>⚡</span> 正在思考中...</summary><div class="think-content px-4 py-3 text-slate-400/80 text-xs leading-relaxed border-t border-slate-700/20 whitespace-pre-wrap font-mono">${thinkContent}</div></details>`;
  }

  // marked.parse(text) 同步执行并返回 HTML 字符串
  let html = marked.parse(processedText) as string;

  // 将占位符还原为 KaTeX 渲染生成的 HTML 字符串
  placeholders.forEach((mathHtml, idx) => {
    html = html.replace(`BLOCKMATHPLACEHOLDER${idx}`, mathHtml);
    html = html.replace(`INLINEMATHPLACEHOLDER${idx}`, mathHtml);
  });

  return html;
};
