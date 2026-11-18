// 詳細画面で保存していない変更があるかどうか。共通のナビゲーションから移動するときにも警告するため、
// 画面をまたいで 1 か所で持つ（同時に編集できる画面は 1 つだけなので、ただの変数で足りる）
let dirty = false;

export const UNSAVED_MESSAGE = "変更が保存されていません。破棄して移動しますか？";

export function setUnsaved(value: boolean) {
  dirty = value;
}

// <Link onNavigate> から呼ぶ。移動してよければ true
export function confirmLeave(): boolean {
  return !dirty || confirm(UNSAVED_MESSAGE);
}
