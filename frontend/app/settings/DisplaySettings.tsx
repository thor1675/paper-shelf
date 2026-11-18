"use client";

import { useState } from "react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  DISPLAY_COOKIE,
  type Display,
  FONT_OPTIONS,
  THEME_OPTIONS,
  WIDTH_OPTIONS,
  serializeDisplay,
} from "@/lib/display";

// 表示の設定。選んだ瞬間に <html> の data-* 属性を書き換えて反映し、Cookie に保存する（次に開いたときはサーバーが反映する）
export default function DisplaySettings({ initial }: { initial: Display }) {
  const [display, setDisplay] = useState(initial);

  function update<K extends keyof Display>(key: K, value: Display[K] | "") {
    // ToggleGroup は、選んでいるものをもう一度押すと "" を返す。何も選ばれていない状態にはしない
    if (!value) return;
    const next = { ...display, [key]: value };
    setDisplay(next);
    document.documentElement.dataset[key] = value;
    // 1 年間とっておく。画面のスクリプトから読み書きするので HttpOnly にはしない（ログインの情報は入っていない）
    document.cookie = `${DISPLAY_COOKIE}=${serializeDisplay(next)}; Path=/; Max-Age=${365 * 86400}; SameSite=Lax`;
  }

  return (
    <div className="flex flex-col gap-4 text-sm">
      <Row label="文字の大きさ">
        <ToggleGroup
          type="single"
          variant="outline"
          value={display.font}
          onValueChange={(v) => update("font", v as Display["font"])}
          aria-label="文字の大きさ"
        >
          {FONT_OPTIONS.map((o) => (
            <ToggleGroupItem key={o.value} value={o.value} className="px-3">
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Row>
      <Row label="幅" note={WIDTH_OPTIONS.find((o) => o.value === display.width)?.note}>
        <ToggleGroup
          type="single"
          variant="outline"
          value={display.width}
          onValueChange={(v) => update("width", v as Display["width"])}
          aria-label="幅"
        >
          {WIDTH_OPTIONS.map((o) => (
            <ToggleGroupItem key={o.value} value={o.value} className="px-3">
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Row>
      <Row label="テーマ">
        <ToggleGroup
          type="single"
          variant="outline"
          value={display.theme}
          onValueChange={(v) => update("theme", v as Display["theme"])}
          aria-label="テーマ"
        >
          {THEME_OPTIONS.map((o) => (
            <ToggleGroupItem key={o.value} value={o.value} className="px-3">
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Row>
      <p className="text-xs text-muted-foreground">このブラウザだけの設定です</p>
    </div>
  );
}

function Row({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-medium">{label}</span>
      {children}
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  );
}
