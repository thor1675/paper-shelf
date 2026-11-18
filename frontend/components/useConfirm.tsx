"use client";

import { useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type Options = { title: string; description?: string; action: string; destructive?: boolean };

/**
 * ブラウザ標準の confirm() の代わりに、shadcn/ui の AlertDialog で確かめる。
 * `if (!(await confirm({...}))) return;` の形で使い、返した `dialog` を画面のどこかに置く。
 * confirm() と違って、画面の見た目に合わせられ、ダイアログが開いている間は後ろの画面を操作できず、
 * Esc か「キャンセル」で閉じる（どちらも false）。
 */
export function useConfirm() {
  const [options, setOptions] = useState<Options | null>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  function confirm(next: Options): Promise<boolean> {
    setOptions(next);
    return new Promise((resolve) => {
      resolver.current = resolve;
    });
  }

  function close(ok: boolean) {
    resolver.current?.(ok);
    resolver.current = null;
    setOptions(null);
  }

  const dialog = (
    <AlertDialog open={options !== null} onOpenChange={(open) => !open && close(false)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title}</AlertDialogTitle>
          {options?.description && <AlertDialogDescription>{options.description}</AlertDialogDescription>}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>キャンセル</AlertDialogCancel>
          <AlertDialogAction variant={options?.destructive ? "destructive" : "default"} onClick={() => close(true)}>
            {options?.action}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, dialog };
}
