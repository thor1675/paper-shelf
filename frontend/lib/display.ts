// 表示の設定（設定 → 表示）。ブラウザごとに Cookie に保存し、サーバーが <html> の data-* 属性にして返す。
// サーバーの時点で反映するので、読み込み直後に一瞬だけ元の表示が出ることがない。

export const DISPLAY_COOKIE = "ps_display";

export const FONT_OPTIONS = [
  { value: "small", label: "小" },
  { value: "normal", label: "標準" },
  { value: "large", label: "大" },
  { value: "xlarge", label: "特大" },
] as const;

export const WIDTH_OPTIONS = [
  { value: "default", label: "標準", note: "中央に寄せて読みやすい幅にする" },
  { value: "wide", label: "余白を減らす", note: "画面の幅いっぱいに広げる" },
] as const;

export const THEME_OPTIONS = [
  { value: "system", label: "OS に合わせる" },
  { value: "light", label: "ライト" },
  { value: "dark", label: "ダーク" },
] as const;

export type Display = {
  font: (typeof FONT_OPTIONS)[number]["value"];
  width: (typeof WIDTH_OPTIONS)[number]["value"];
  theme: (typeof THEME_OPTIONS)[number]["value"];
};

export const DEFAULT_DISPLAY: Display = { font: "normal", width: "default", theme: "system" };

const pick = <T extends string>(options: readonly { value: T }[], v: unknown, fallback: T): T =>
  options.some((o) => o.value === v) ? (v as T) : fallback;

// Cookie の値（"font.width.theme"）を読む。知らない値は既定に戻す（Cookie は利用者が書き換えられるため）
export function parseDisplay(raw: string | undefined): Display {
  const [font, width, theme] = (raw ?? "").split(".");
  return {
    font: pick(FONT_OPTIONS, font, DEFAULT_DISPLAY.font),
    width: pick(WIDTH_OPTIONS, width, DEFAULT_DISPLAY.width),
    theme: pick(THEME_OPTIONS, theme, DEFAULT_DISPLAY.theme),
  };
}

export function serializeDisplay(d: Display): string {
  return `${d.font}.${d.width}.${d.theme}`;
}
