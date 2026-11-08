"""
DiffEditor — file comparison and editing tool
 Supports .txt, .html, .ipynb, .py files
Windows 10/11, x32/x64
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
import difflib
import json
import os
import sys
import threading

# ─── colour palette ───────────────────────────────────────────────────────────
CLR_BG          = "#1e1e2e"
CLR_PANEL       = "#181825"
CLR_TEXT        = "#cdd6f4"
CLR_TEXT_DIM    = "#6c7086"
CLR_ACCENT      = "#89b4fa"
CLR_BTN         = "#313244"
CLR_BTN_HOVER   = "#45475a"
CLR_ADD         = "#1e4620"   # green bg  (added lines)
CLR_ADD_FG      = "#a6e3a1"
CLR_DEL         = "#4a1010"   # red bg    (removed lines)
CLR_DEL_FG      = "#f38ba8"
CLR_CHANGE      = "#3b3000"   # amber bg  (changed chars in line)
CLR_CHANGE_FG   = "#f9e2af"
CLR_LINENO      = "#45475a"
CLR_SEP         = "#313244"
CLR_STATUS_OK   = "#a6e3a1"
CLR_STATUS_INFO = "#89b4fa"
FONT_MONO       = ("Consolas", 11)
FONT_UI         = ("Segoe UI", 10)
FONT_SMALL      = ("Segoe UI", 9)


# ─── helpers ──────────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Read a file, auto-detect encoding, pretty-print ipynb."""
    for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                raw = f.read()
            if path.lower().endswith(".ipynb"):
                try:
                    obj = json.loads(raw)
                    return json.dumps(obj, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            return raw
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"Cannot read {path}")


def write_file(path: str, text: str) -> None:
    """Write text to file; for ipynb, validate JSON first."""
    if path.lower().endswith(".ipynb"):
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for .ipynb: {e}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def lines_of(text: str):
    return text.splitlines(keepends=True)


# ─── EditorPane  ──────────────────────────────────────────────────────────────

class EditorPane(tk.Frame):
    """A single text editor pane with line numbers."""

    def __init__(self, master, label: str, **kw):
        super().__init__(master, bg=CLR_BG, **kw)
        self.filepath: str | None = None

        # header row
        hdr = tk.Frame(self, bg=CLR_PANEL, pady=4)
        hdr.pack(fill=tk.X)

        self._label_var = tk.StringVar(value=label)
        tk.Label(hdr, textvariable=self._label_var, bg=CLR_PANEL,
                 fg=CLR_ACCENT, font=FONT_UI, anchor="w", padx=8).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._open_btn = tk.Button(hdr, text="📂 Открыть", font=FONT_SMALL,
                                    bg=CLR_BTN, fg=CLR_TEXT, activebackground=CLR_BTN_HOVER,
                                    activeforeground=CLR_TEXT, relief=tk.FLAT, padx=8,
                                    cursor="hand2", command=self._open)
        self._open_btn.pack(side=tk.RIGHT, padx=4)

        self._save_btn = tk.Button(hdr, text="💾 Сохранить", font=FONT_SMALL,
                                    bg=CLR_BTN, fg=CLR_TEXT, activebackground=CLR_BTN_HOVER,
                                    activeforeground=CLR_TEXT, relief=tk.FLAT, padx=8,
                                    cursor="hand2", command=self._save)
        self._save_btn.pack(side=tk.RIGHT, padx=4)

        # editor area
        editor_frame = tk.Frame(self, bg=CLR_BG)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        # line numbers
        self.linenums = tk.Text(editor_frame, width=5, bg=CLR_PANEL,
                                fg=CLR_LINENO, font=FONT_MONO,
                                state=tk.DISABLED, relief=tk.FLAT,
                                selectbackground=CLR_PANEL, pady=2,
                                cursor="arrow", takefocus=False)
        self.linenums.pack(side=tk.LEFT, fill=tk.Y)

        # scrollbar
        vsb = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        # main text widget
        self.text = tk.Text(editor_frame, bg=CLR_BG, fg=CLR_TEXT,
                            font=FONT_MONO, relief=tk.FLAT,
                            insertbackground=CLR_ACCENT,
                            selectbackground="#45475a",
                            undo=True, maxundo=-1,
                            wrap=tk.NONE, pady=2,
                            yscrollcommand=self._on_yscroll,
                            xscrollcommand=hsb.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb.config(command=self._on_vsb)
        hsb.config(command=self.text.xview)

        # diff colour tags
        self.text.tag_configure("add",    background=CLR_ADD,    foreground=CLR_ADD_FG)
        self.text.tag_configure("delete", background=CLR_DEL,    foreground=CLR_DEL_FG)
        self.text.tag_configure("change", background=CLR_CHANGE, foreground=CLR_CHANGE_FG)

        # bind events
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Configure>", lambda _e: self._update_linenums())
        self.text.bind("<MouseWheel>", self._on_mousewheel)

        self._update_cb = None   # external callback on text change

    # ── public ────────────────────────────────────────────────────────────────

    def set_text(self, text: str) -> None:
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._update_linenums()

    def get_text(self) -> str:
        return self.text.get("1.0", tk.END)

    def set_label(self, text: str) -> None:
        self._label_var.set(text)

    def clear_diff_tags(self) -> None:
        for tag in ("add", "delete", "change"):
            self.text.tag_remove(tag, "1.0", tk.END)

    def apply_line_tag(self, lineno: int, tag: str) -> None:
        """Tag an entire line (1-based)."""
        start = f"{lineno}.0"
        end   = f"{lineno}.end+1c"
        self.text.tag_add(tag, start, end)

    def apply_char_tag(self, lineno: int, col_start: int, col_end: int, tag: str) -> None:
        self.text.tag_add(tag, f"{lineno}.{col_start}", f"{lineno}.{col_end}")

    def total_lines(self) -> int:
        return int(self.text.index(tk.END).split(".")[0]) - 1

    def scroll_to_line(self, lineno: int) -> None:
        self.text.see(f"{lineno}.0")

    # ── private ───────────────────────────────────────────────────────────────

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self._update_linenums()
            self.text.edit_modified(False)
            if self._update_cb:
                # debounce: cancel previous scheduled call
                if hasattr(self, "_debounce_id") and self._debounce_id:
                    self.after_cancel(self._debounce_id)
                self._debounce_id = self.after(300, self._update_cb)

    def _update_linenums(self):
        total = self.total_lines()
        nums  = "\n".join(str(i) for i in range(1, total + 2))
        self.linenums.config(state=tk.NORMAL)
        self.linenums.delete("1.0", tk.END)
        self.linenums.insert("1.0", nums)
        self.linenums.config(state=tk.DISABLED)
        # sync scroll
        self.linenums.yview_moveto(self.text.yview()[0])

    def _on_yscroll(self, *args):
        # sync scrollbar + line numbers
        for w in (self.linenums,):
            w.yview_moveto(args[0])

    def _on_vsb(self, *args):
        self.text.yview(*args)
        self.linenums.yview(*args)

    def _on_mousewheel(self, event):
        delta = -1 * (event.delta // 120)
        self.text.yview_scroll(delta, "units")
        self.linenums.yview_scroll(delta, "units")
        return "break"

    def _open(self):
        path = filedialog.askopenfilename(
            title="Открыть файл",
            filetypes=[("Поддерживаемые файлы", "*.txt *.html *.htm *.ipynb *.py"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        try:
            text = read_file(path)
            self.filepath = path
            self.set_label(os.path.basename(path))
            self.set_text(text)
            if self._update_cb:
                self._update_cb()
        except Exception as e:
            messagebox.showerror("Ошибка чтения", str(e))

    def _save(self):
        path = self.filepath or filedialog.asksaveasfilename(
            title="Сохранить файл",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("HTML", "*.html *.htm"),
                       ("Notebook", "*.ipynb"), ("Python", "*.py"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        try:
            write_file(path, self.get_text().rstrip("\n") + "\n")
            self.filepath = path
            self.set_label(os.path.basename(path))
            messagebox.showinfo("Сохранено", f"Файл сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка записи", str(e))


# ─── DiffEngine ───────────────────────────────────────────────────────────────

def compute_diff(left_text: str, right_text: str):
    """
    Returns two lists of tag instructions:
      [ (lineno, tag, col_start, col_end), ... ]
    col_start/col_end == -1 means whole-line tag.
    """
    left_lines  = lines_of(left_text)
    right_lines = lines_of(right_text)

    left_tags  = []
    right_tags = []

    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)

    for op, l1, l2, r1, r2 in matcher.get_opcodes():
        if op == "equal":
            continue

        elif op == "delete":
            for i, ln in enumerate(range(l1 + 1, l2 + 1)):
                left_tags.append((ln, "delete", -1, -1))

        elif op == "insert":
            for ln in range(r1 + 1, r2 + 1):
                right_tags.append((ln, "add", -1, -1))

        elif op == "replace":
            lslice = left_lines[l1:l2]
            rslice = right_lines[r1:r2]

            # pair up lines for intra-line diff
            pairs = max(len(lslice), len(rslice))
            for k in range(pairs):
                lline = lslice[k].rstrip("\n") if k < len(lslice) else None
                rline = rslice[k].rstrip("\n") if k < len(rslice) else None
                lno = l1 + k + 1
                rno = r1 + k + 1

                if lline is None:
                    right_tags.append((rno, "add", -1, -1))
                elif rline is None:
                    left_tags.append((lno, "delete", -1, -1))
                else:
                    # intra-line character diff
                    sm = difflib.SequenceMatcher(None, lline, rline, autojunk=False)
                    ldone = rdone = False
                    for sop, a1, a2, b1, b2 in sm.get_opcodes():
                        if sop == "equal":
                            continue
                        if sop in ("delete", "replace"):
                            left_tags.append((lno, "delete", a1, a2))
                            ldone = True
                        if sop in ("insert", "replace"):
                            right_tags.append((rno, "add", b1, b2))
                            rdone = True
                    # fall back to whole-line if nothing changed (shouldn't happen)
                    if not ldone:
                        left_tags.append((lno, "delete", -1, -1))
                    if not rdone:
                        right_tags.append((rno, "add", -1, -1))

    return left_tags, right_tags


# ─── StatusBar ────────────────────────────────────────────────────────────────

class StatusBar(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=CLR_PANEL, **kw)
        self._var = tk.StringVar(value="Откройте файлы и нажмите «Сравнить»")
        tk.Label(self, textvariable=self._var, bg=CLR_PANEL,
                 fg=CLR_STATUS_INFO, font=FONT_SMALL, anchor="w", padx=10).pack(side=tk.LEFT)

    def set(self, msg: str, colour=CLR_STATUS_INFO):
        self._var.set(msg)
        for child in self.winfo_children():
            child.config(fg=colour)


# ─── App ──────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DiffEditor — сравнение файлов")
        self.geometry("1280x780")
        self.minsize(900, 500)
        self.configure(bg=CLR_BG)

        # icon (skip if not available)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._build_toolbar()
        self._build_main()
        self._build_status()

        # connect change callbacks
        self.left.text.bind("<KeyRelease>", lambda _e: self._auto_diff())
        self.right.text.bind("<KeyRelease>", lambda _e: self._auto_diff())
        self.left._update_cb  = self._do_diff
        self.right._update_cb = self._do_diff

        self._auto_mode = tk.BooleanVar(value=True)
        self._auto_cb.config(variable=self._auto_mode)

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=CLR_PANEL, pady=6)
        bar.pack(fill=tk.X, side=tk.TOP)

        def btn(parent, label, cmd, side=tk.LEFT, pad=4):
            b = tk.Button(parent, text=label, font=FONT_UI,
                          bg=CLR_BTN, fg=CLR_TEXT,
                          activebackground=CLR_BTN_HOVER,
                          activeforeground=CLR_TEXT,
                          relief=tk.FLAT, padx=10, pady=3,
                          cursor="hand2", command=cmd)
            b.pack(side=side, padx=pad)
            return b

        btn(bar, "⟳  Сравнить", self._do_diff)
        btn(bar, "✕  Очистить подсветку", self._clear_diff)

        # separator
        tk.Frame(bar, bg=CLR_SEP, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        btn(bar, "⬆  Пред. изменение", lambda: self._jump(-1))
        btn(bar, "⬇  След. изменение", lambda: self._jump(+1))

        # separator
        tk.Frame(bar, bg=CLR_SEP, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        self._auto_cb = tk.Checkbutton(bar, text="Авто-сравнение",
                                        bg=CLR_PANEL, fg=CLR_TEXT,
                                        selectcolor=CLR_BTN,
                                        activebackground=CLR_PANEL,
                                        activeforeground=CLR_TEXT,
                                        font=FONT_UI, cursor="hand2")
        self._auto_cb.pack(side=tk.LEFT, padx=4)

        # right side
        btn(bar, "?  Справка", self._show_help, side=tk.RIGHT)

        # diff stats label
        self._stats_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._stats_var,
                 bg=CLR_PANEL, fg=CLR_TEXT_DIM, font=FONT_SMALL).pack(side=tk.RIGHT, padx=12)

    def _build_main(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                               bg=CLR_SEP, sashwidth=5,
                               sashrelief=tk.FLAT, handlepad=100)
        paned.pack(fill=tk.BOTH, expand=True)

        self.left  = EditorPane(paned, "← Оригинал (старая версия)")
        self.right = EditorPane(paned, "→ Изменённая (новая версия)")

        paned.add(self.left,  minsize=300, stretch="always")
        paned.add(self.right, minsize=300, stretch="always")

        # set sample text so the app is usable immediately
        sample_old = "Строка 1\nСтрока 2\nСтрока 3 — оригинал\nСтрока 4\nСтрока 5\n"
        sample_new = "Строка 1\nСтрока 2\nСтрока 3 — изменена\nСтрока 4\nНовая строка 5\nСтрока 6\n"
        self.left.set_text(sample_old)
        self.right.set_text(sample_new)

        self._diff_lines: list[int] = []   # sorted line numbers with changes (left side)
        self._diff_idx   = -1

    def _build_status(self):
        self.status = StatusBar(self)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # ── diff logic ────────────────────────────────────────────────────────────

    def _do_diff(self):
        ltext = self.left.get_text()
        rtext = self.right.get_text()

        self.left.clear_diff_tags()
        self.right.clear_diff_tags()

        ltags, rtags = compute_diff(ltext, rtext)

        # apply tags
        for (ln, tag, c0, c1) in ltags:
            if c0 == -1:
                self.left.apply_line_tag(ln, tag)
            else:
                self.left.apply_char_tag(ln, c0, c1, tag)

        for (ln, tag, c0, c1) in rtags:
            if c0 == -1:
                self.right.apply_line_tag(ln, tag)
            else:
                self.right.apply_char_tag(ln, c0, c1, tag)

        # stats — count unique changed lines
        changed_lines_l = {ln for ln, _t, _c0, _c1 in ltags}
        changed_lines_r = {ln for ln, _t, _c0, _c1 in rtags}

        self._diff_lines = sorted({ln for ln, _, _, _ in ltags} |
                                   {ln for ln, _, _, _ in rtags})
        self._diff_idx   = -1

        n_total = len(set(ln for ln, _, _, _ in ltags) | set(ln for ln, _, _, _ in rtags))

        if n_total == 0:
            self.status.set("Файлы идентичны ✓", CLR_STATUS_OK)
            self._stats_var.set("")
        else:
            msg = f"Изменений: {n_total} строк"
            self.status.set(msg, CLR_STATUS_INFO)
            self._stats_var.set(msg)

    def _auto_diff(self):
        if self._auto_mode.get():
            if hasattr(self, "_auto_id"):
                self.after_cancel(self._auto_id)
            self._auto_id = self.after(350, self._do_diff)

    def _clear_diff(self):
        self.left.clear_diff_tags()
        self.right.clear_diff_tags()
        self._diff_lines = []
        self._stats_var.set("")
        self.status.set("Подсветка очищена", CLR_STATUS_INFO)

    def _jump(self, direction: int):
        if not self._diff_lines:
            self.status.set("Нет изменений для навигации", CLR_TEXT_DIM)
            return
        self._diff_idx = (self._diff_idx + direction) % len(self._diff_lines)
        ln = self._diff_lines[self._diff_idx]
        self.left.scroll_to_line(ln)
        self.right.scroll_to_line(ln)
        self.status.set(f"Изменение {self._diff_idx + 1} / {len(self._diff_lines)} — строка {ln}")

    def _show_help(self):
        msg = (
            "DiffEditor — сравнение и редактирование файлов\n"
            "═══════════════════════════════════════════════\n\n"
            "Поддерживаемые форматы:\n"
            "  • .txt  — текстовые файлы\n"
            "  • .html / .htm  — HTML-страницы\n"
            "  • .py  — файлы Python\n"
            "  • .ipynb  — Jupyter Notebooks (отображаются как JSON)\n\n"
            "Цвета подсветки:\n"
            "  🟢 Зелёный — добавленные строки / символы\n"
            "  🔴 Красный — удалённые строки / символы\n"
            "  🟡 Жёлтый  — изменённые символы внутри строки\n\n"
            "Кнопки:\n"
            "  📂 Открыть  — загрузить файл с диска\n"
            "  💾 Сохранить — сохранить текущее содержимое\n"
            "  ⟳ Сравнить  — запустить diff вручную\n"
            "  ⬆ / ⬇       — переходить между изменениями\n\n"
            "Авто-сравнение: diff обновляется автоматически\n"
            "при редактировании (с задержкой 350 мс).\n\n"
            "Запуск на Windows без Python:\n"
            "  pyinstaller --onefile --windowed diffeditor.py\n"
        )
        messagebox.showinfo("Справка", msg)


# ─── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Hi-DPI awareness on Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    app.after(100, app._do_diff)   # run initial diff after window is ready
    app.mainloop()
