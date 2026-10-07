# integrated_vault_gui.py
"""
PersonalVault GUI v3（打包兼容版）
标签页：加密 / 解密 / 健康检查 / 工具
"""
import os
import sys
import json
import shutil
import platform
import subprocess
import threading
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime, timezone, timedelta

# ---------- 拖放 ----------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False


# ---------- 打包路径兼容 ----------
def get_app_dir() -> str:
    """返回程序所在目录（兼容 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def _fatal(title, msg):
    r = tk.Tk()
    r.withdraw()
    messagebox.showerror(title, msg)
    r.destroy()
    sys.exit(1)


# ---------- 扫描模块 ----------
try:
    from file_scanner import scan_all_drives, get_drives
    HAS_SCANNER = True
except ImportError:
    HAS_SCANNER = False


# ---------- 加密模块 ----------
try:
    from personal_vault import (
        TaskContext, encrypt_file, decrypt_file, read_header,
        encrypt_folder, decrypt_folder, batch_encrypt, batch_decrypt,
        health_check, encrypt_dualspace, decrypt_dualspace,
        steganography_hide, steganography_reveal,
        PasswordError, IntegrityError, ExpiredError, RecoveryKeyError,
        generate_strong_password, generate_recovery_key,
        password_strength, secure_delete,
    )
except ModuleNotFoundError as e:
    if e.name == "personal_vault":
        _fatal("缺少文件", "未找到 personal_vault.py")
    elif e.name == "cryptography":
        _fatal("缺少依赖", "缺少 cryptography。\n\n    pip install cryptography")
    else:
        _fatal("缺少依赖", f"缺少 {e.name}")


CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".personal_vault_gui.json")
JOURNAL_PATH = os.path.join(os.path.expanduser("~"), ".personal_vault_journal.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def write_journal(op, mode, completed, pending):
    try:
        with open(JOURNAL_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                "operation": op, "mode": mode, "completed": completed,
                "pending": pending, "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_journal():
    if os.path.exists(JOURNAL_PATH):
        try:
            os.remove(JOURNAL_PATH)
        except Exception:
            pass


def parse_expiry(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        days = int(text)
        if days <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(days=days)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"无法解析过期时间: {text}")


# ==================== 主题 ====================
COLORS_DARK = {
    "bg": "#1e1e1e", "fg": "#e0e0e0", "sel_bg": "#3a3a3a",
    "entry_bg": "#2b2b2b", "entry_fg": "#e0e0e0",
    "btn_bg": "#333333", "btn_active": "#444444",
    "log_bg": "#1a1a1a", "log_fg": "#e0e0e0",
    "ok": "#4ec94e", "err": "#ff6b6b", "warn": "#ffb84d", "title": "#66b3ff",
}
COLORS_LIGHT = {
    "bg": "#f0f0f0", "fg": "#000000", "sel_bg": "#cce8ff",
    "entry_bg": "#ffffff", "entry_fg": "#000000",
    "btn_bg": "#e1e1e1", "btn_active": "#cccccc",
    "log_bg": "#ffffff", "log_fg": "#000000",
    "ok": "#008000", "err": "#cc0000", "warn": "#cc6600", "title": "#0055aa",
}


class ThemeManager:
    def __init__(self):
        self.dark = False
        self.colors = COLORS_LIGHT
        self.panels = []

    def register(self, panel):
        self.panels.append(panel)
        panel.apply_theme(self.colors)

    def apply(self, root, dark):
        self.dark = dark
        self.colors = COLORS_DARK if dark else COLORS_LIGHT
        c = self.colors
        style = ttk.Style(root)

        try:
            if dark:
                style.theme_use('clam')
            else:
                for t in ('vista', 'winnative', 'clam', 'default'):
                    if t in style.theme_names():
                        style.theme_use(t)
                        break
        except Exception:
            pass

        style.configure('.', background=c['bg'], foreground=c['fg'])
        style.configure('TFrame', background=c['bg'])
        style.configure('TLabel', background=c['bg'], foreground=c['fg'])
        style.configure('TLabelframe', background=c['bg'], foreground=c['fg'])
        style.configure('TLabelframe.Label', background=c['bg'], foreground=c['fg'])
        style.configure('TButton', background=c['btn_bg'], foreground=c['fg'])
        style.map('TButton',
                  background=[('active', c['btn_active'])],
                  foreground=[('active', c['fg'])])
        style.configure('TCheckbutton', background=c['bg'], foreground=c['fg'])
        style.map('TCheckbutton', background=[('active', c['bg'])])
        style.configure('TRadiobutton', background=c['bg'], foreground=c['fg'])
        style.map('TRadiobutton', background=[('active', c['bg'])])
        style.configure('TEntry',
                        fieldbackground=c['entry_bg'], foreground=c['entry_fg'])
        style.configure('TNotebook', background=c['bg'])
        style.configure('TNotebook.Tab',
                        background=c['btn_bg'], foreground=c['fg'])
        style.map('TNotebook.Tab',
                  background=[('selected', c['bg'])],
                  foreground=[('selected', c['fg'])])

        root.configure(bg=c['bg'])
        for p in self.panels:
            p.apply_theme(c)


THEME = ThemeManager()


# ==================== 日志 ====================
class LogPanel(ttk.Frame):
    def __init__(self, master, title="日志", height=8):
        super().__init__(master)
        lf = ttk.LabelFrame(self, text=title)
        lf.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(lf, height=height, wrap=tk.WORD)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        sb = ttk.Scrollbar(lf, command=self.text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 5))
        self.text.config(yscrollcommand=sb.set)
        self.text.tag_config("ts", foreground="#888888")

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_row, text="清空", command=self.clear).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="导出", command=self.export).pack(side=tk.LEFT, padx=3)
        THEME.register(self)

    def apply_theme(self, c):
        self.text.config(bg=c['log_bg'], fg=c['log_fg'],
                         insertbackground=c['log_fg'])
        self.text.tag_config("info", foreground=c['log_fg'])
        self.text.tag_config("ok", foreground=c['ok'])
        self.text.tag_config("err", foreground=c['err'])
        self.text.tag_config("warn", foreground=c['warn'])
        self.text.tag_config("title", foreground=c['title'], font=("", 9, "bold"))

    def clear(self):
        self.text.delete('1.0', tk.END)

    def log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert(tk.END, f"[{ts}] ", "ts")
        self.text.insert(tk.END, msg + "\n", level)
        self.text.see(tk.END)
        self.update_idletasks()

    def export(self):
        content = self.text.get('1.0', tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "日志为空")
            return
        fp = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"vault_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        if fp:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("提示", f"已保存到：{fp}")


class PasswordStrengthBar(ttk.Frame):
    def __init__(self, master, password_var):
        super().__init__(master)
        self.password_var = password_var
        self.bar = ttk.Progressbar(self, length=120, maximum=6, mode='determinate')
        self.bar.pack(side=tk.LEFT, padx=(4, 4))
        self.label = ttk.Label(self, text="", width=6)
        self.label.pack(side=tk.LEFT)
        password_var.trace_add('write', self._update)

    def _update(self, *args):
        pwd = self.password_var.get()
        score, text = password_strength(pwd)
        self.bar['value'] = score
        colors = {0: "gray", 1: "red", 2: "red", 3: "orange",
                  4: "orange", 5: "green", 6: "green"}
        self.label.config(text=text, foreground=colors.get(score, "gray"))


# ==================== 加密页 ====================
class EncryptTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.password_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="batch")
        self.remove_orig_var = tk.BooleanVar(value=False)
        self.expiry_var = tk.StringVar(value="")
        self.use_recovery_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_text = tk.StringVar(value="就绪")
        self.file_list = []
        self._stop_flag = False
        self._worker = None
        self._build_ui()
        self._load_cfg()

    def _build_ui(self):
        # ① 列表
        lf = ttk.LabelFrame(self, text="① 待加密文件（可拖拽文件/文件夹）")
        lf.pack(fill=tk.BOTH, expand=True, pady=4)
        body = ttk.Frame(lf)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        self.listbox = tk.Listbox(body, selectmode=tk.EXTENDED, height=6, activestyle="none")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(body, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind('<Delete>', lambda e: self._remove_selected())
        self.listbox.bind('<Double-Button-1>', lambda e: self._preview_header())
        self.listbox.bind('<Button-3>', self._show_list_menu)

        bar = ttk.Frame(lf)
        bar.pack(fill=tk.X, padx=5, pady=(0, 4))
        ttk.Button(bar, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="添加文件夹", command=self._add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="扫描磁盘", command=self._scan_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="清空", command=self._clear_list).pack(side=tk.LEFT, padx=2)
        self.count_label = ttk.Label(bar, text="共 0 项", foreground="gray")
        self.count_label.pack(side=tk.RIGHT)

        # ② 加密设置
        enc = ttk.LabelFrame(self, text="② 加密设置")
        enc.pack(fill=tk.X, pady=4)

        row = ttk.Frame(enc)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="密码：", width=8).pack(side=tk.LEFT)
        self.pwd_entry = ttk.Entry(row, textvariable=self.password_var, show='*', width=26)
        self.pwd_entry.pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="显示/隐藏", command=self._toggle_pwd).pack(side=tk.LEFT)
        PasswordStrengthBar(row, self.password_var).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="生成强密码", command=self._gen_pwd).pack(side=tk.LEFT, padx=3)

        row = ttk.Frame(enc)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="模式：", width=8).pack(side=tk.LEFT)
        ttk.Radiobutton(row, text="逐个加密 (.enc)", variable=self.mode_var,
                        value="batch").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row, text="打包成 .vault", variable=self.mode_var,
                        value="vault").pack(side=tk.LEFT, padx=4)

        row = ttk.Frame(enc)
        row.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(row, text="加密后安全删除原文件",
                        variable=self.remove_orig_var).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(row, text="生成恢复密钥（需抄写保管）",
                        variable=self.use_recovery_var).pack(side=tk.LEFT, padx=4)

        row = ttk.Frame(enc)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="过期时间：", width=10).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.expiry_var, width=20).pack(side=tk.LEFT, padx=3)
        ttk.Label(row, text="留空=不过期；数字=天数；或日期 2026-12-31",
                  foreground="gray").pack(side=tk.LEFT)

        # ③ 进度
        pf = ttk.LabelFrame(self, text="③ 进度")
        pf.pack(fill=tk.X, pady=4)
        ttk.Progressbar(pf, variable=self.progress_var, maximum=100).pack(
            fill=tk.X, padx=5, pady=4)
        ttk.Label(pf, textvariable=self.status_text, anchor=tk.W,
                  foreground="#444444").pack(fill=tk.X, padx=5, pady=(0, 4))

        # ④ 日志
        self.log_panel = LogPanel(self, title="④ 日志", height=7)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=4)

        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=4)
        self.start_btn = ttk.Button(row, text="▶ 开始加密", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        self.stop_btn = ttk.Button(row, text="■ 停止", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="🔑 恢复密钥生成器",
                   command=self.app.show_recovery_dialog).pack(side=tk.LEFT, padx=4)

    # ---------- 配置 ----------
    def _load_cfg(self):
        e = load_config().get('encrypt', {})
        self.mode_var.set(e.get('mode', 'batch'))
        self.remove_orig_var.set(e.get('remove_orig', False))
        self.expiry_var.set(e.get('expiry', ''))
        self.use_recovery_var.set(e.get('use_recovery', False))

    def _save_cfg(self):
        cfg = load_config()
        cfg['encrypt'] = {
            'mode': self.mode_var.get(),
            'remove_orig': self.remove_orig_var.get(),
            'expiry': self.expiry_var.get(),
            'use_recovery': self.use_recovery_var.get(),
        }
        save_config(cfg)

    # ---------- 工具 ----------
    def log(self, msg, level="info"):
        self.log_panel.log(msg, level)

    def _update_count(self):
        self.count_label.config(text=f"共 {len(self.file_list)} 项")

    def _toggle_pwd(self):
        self.pwd_entry.config(show='' if self.pwd_entry.cget('show') == '*' else '*')

    def _gen_pwd(self):
        pwd = generate_strong_password(16)
        self.password_var.set(pwd)
        self.clipboard_clear()
        self.clipboard_append(pwd)
        messagebox.showinfo("强密码", f"已生成并复制到剪贴板：\n\n{pwd}")

    def _show_list_menu(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="预览文件头信息",
                         command=lambda: self._preview_header(idx))
        menu.add_command(label="打开所在文件夹",
                         command=lambda: self._open_folder(idx))
        menu.add_command(label="复制路径",
                         command=lambda: self._copy_path(idx))
        menu.add_separator()
        menu.add_command(label="移除此项",
                         command=lambda: self._remove_one(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def _preview_header(self, idx=None):
        if idx is None:
            sel = self.listbox.curselection()
            if not sel:
                return
            idx = sel[0]
        path = self.file_list[idx]
        if not os.path.isfile(path):
            return
        if not path.lower().endswith(('.enc', '.vault')):
            messagebox.showinfo("提示", "仅 .enc/.vault 文件可预览头部")
            return
        try:
            info = read_header(path)
            h = info["header"]
            lines = [
                f"版本: v{h.get('version')}",
                f"原文件名: {h.get('filename', '?')}",
                f"原始大小: {h.get('size', 0)} bytes",
                f"加密时间: {h.get('timestamp', '?')}",
                f"过期时间: {h.get('expiry') or '无'}",
                f"提示信息: {h.get('hint') or '无'}",
                f"恢复密钥: {'已设置' if h.get('recovery_wrapped_fk') else '未设置'}",
                f"类型: {'双空间' if h.get('dual') else '普通'}",
                f"SHA-256: {h.get('filehash', '?')}",
            ]
            messagebox.showinfo(f"文件头: {os.path.basename(path)}", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _open_folder(self, idx):
        path = self.file_list[idx]
        d = os.path.dirname(path) if os.path.isfile(path) else path
        if platform.system() == 'Windows':
            os.startfile(d)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', d])
        else:
            subprocess.Popen(['xdg-open', d])

    def _copy_path(self, idx):
        self.clipboard_clear()
        self.clipboard_append(self.file_list[idx])

    def _remove_one(self, idx):
        self.listbox.delete(idx)
        del self.file_list[idx]
        self._update_count()

    def _remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for idx in sorted(sel, reverse=True):
            self.listbox.delete(idx)
            del self.file_list[idx]
        self._update_count()

    def _clear_list(self):
        self.listbox.delete(0, tk.END)
        self.file_list.clear()
        self._update_count()

    # ---------- 添加 ----------
    def add_paths(self, paths):
        added = 0
        skipped = 0
        for p in paths:
            if not os.path.exists(p):
                continue
            if p in self.file_list:
                continue
            if os.path.isfile(p) and p.lower().endswith(('.enc', '.vault')):
                skipped += 1
                continue
            self.file_list.append(p)
            disp = f"[文件夹] {p}" if os.path.isdir(p) else p
            self.listbox.insert(tk.END, disp)
            added += 1
        self._update_count()
        if added:
            self.log(f"已添加 {added} 项，共 {len(self.file_list)} 项", "ok")
        if skipped:
            self.log(f"跳过 {skipped} 个加密文件", "warn")

    def _add_files(self):
        fs = filedialog.askopenfilenames(title="选择要加密的文件")
        if fs:
            self.add_paths(list(fs))

    def _add_folder(self):
        d = filedialog.askdirectory(title="选择要加密的文件夹")
        if d:
            self.add_paths([d])

    def _scan_dialog(self):
        if not HAS_SCANNER:
            messagebox.showwarning("提示", "未找到 file_scanner.py，扫描功能不可用。")
            return
        dlg = tk.Toplevel(self)
        dlg.title("扫描磁盘")
        dlg.geometry("560x380")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        f = ttk.Frame(dlg, padding=10)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="选择盘符：").pack(anchor=tk.W)
        df = ttk.Frame(f)
        df.pack(fill=tk.X, pady=3)
        drive_vars = {}
        try:
            drives = get_drives()
        except Exception:
            drives = []
        if not drives and os.path.exists("/"):
            drives = ["/"]
        for d in drives:
            v = tk.BooleanVar(value=False)
            drive_vars[d] = v
            ttk.Checkbutton(df, text=d, variable=v).pack(side=tk.LEFT, padx=3)

        ttk.Label(f, text="文件扩展名（空格分隔）：").pack(anchor=tk.W, pady=(10, 0))
        ext_var = tk.StringVar(value=".jpg .jpeg .png .pdf .docx .xlsx .pptx .txt .md")
        ttk.Entry(f, textvariable=ext_var).pack(fill=tk.X, pady=3)

        ttk.Label(f, text="排除目录名（逗号分隔）：").pack(anchor=tk.W, pady=(10, 0))
        excl_var = tk.StringVar(value="windows, program files, program files (x86), programdata, temp")
        ttk.Entry(f, textvariable=excl_var).pack(fill=tk.X, pady=3)

        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, pady=10)

        def do_scan():
            sel = [d for d, v in drive_vars.items() if v.get()]
            if not sel:
                messagebox.showwarning("提示", "请至少选择一个盘符", parent=dlg)
                return
            exts = set(e.strip().lower() for e in ext_var.get().split() if e.strip())
            excls = set(e.strip().lower() for e in excl_var.get().split(',') if e.strip())
            dlg.destroy()
            self._run_scan(sel, exts, excls)

        ttk.Button(bar, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=3)
        ttk.Button(bar, text="开始扫描", command=do_scan).pack(side=tk.RIGHT, padx=3)

    def _run_scan(self, drives, exts, excls):
        self.log("开始扫描磁盘...", "title")

        def worker():
            count = 0
            try:
                for fp in scan_all_drives(drives=drives, exclude_dirs=excls,
                                          allowed_extensions=exts):
                    if self._stop_flag:
                        break
                    if fp in self.file_list:
                        continue
                    self.file_list.append(fp)
                    self.listbox.insert(tk.END, fp)
                    count += 1
                    if count % 100 == 0:
                        self._update_count()
                        self.log(f"已扫描 {count} 个文件...", "info")
                self._update_count()
                self.log(f"扫描完成，共添加 {count} 个文件", "ok")
            except Exception as e:
                self.log(f"扫描出错: {e}", "err")

        self._stop_flag = False
        threading.Thread(target=worker, daemon=True).start()

    # ---------- 开始 ----------
    def start(self):
        pwd = self.password_var.get()
        if not pwd or not pwd.strip():
            messagebox.showwarning("提示", "请输入密码")
            return
        if len(pwd) < 8:
            if not messagebox.askyesno("弱密码", "密码少于 8 位，是否继续？"):
                return
        if not self.file_list:
            messagebox.showwarning("提示", "请先添加要加密的文件或文件夹")
            return
        if not self.app.acquire_task("加密"):
            return

        try:
            expiry = parse_expiry(self.expiry_var.get())
        except ValueError as e:
            self.app.release_task()
            messagebox.showerror("错误", str(e))
            return

        vault_path = None
        if self.mode_var.get() == "vault":
            vault_path = filedialog.asksaveasfilename(
                title="保存加密容器为",
                defaultextension=".vault",
                initialfile="my_vault.vault",
                filetypes=[("Vault 文件", "*.vault")])
            if not vault_path:
                self.app.release_task()
                return

        recovery = generate_recovery_key() if self.use_recovery_var.get() else None
        if recovery:
            self._show_recovery_key(recovery)
            if not messagebox.askyesno("确认", "您已经抄写并安全保存了恢复密钥吗？"):
                self.app.release_task()
                return

        self._save_cfg()
        self._stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.log_panel.clear()
        self._worker = threading.Thread(
            target=self._do_encrypt,
            args=(pwd, list(self.file_list), vault_path, expiry, recovery),
            daemon=True)
        self._worker.start()

    def _show_recovery_key(self, key):
        dlg = tk.Toplevel(self)
        dlg.title("恢复密钥")
        dlg.geometry("560x260")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        f = ttk.Frame(dlg, padding=15)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="⚠ 请立即抄写并妥善保存此恢复密钥",
                  font=("", 11, "bold"), foreground="#cc0000").pack(anchor=tk.W)
        ttk.Label(f, text="忘记密码时，只能用它解密文件。丢失后无法找回。",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 10))
        txt = tk.Text(f, height=3, wrap=tk.WORD, font=("Consolas", 11))
        txt.pack(fill=tk.X, pady=5)
        txt.insert('1.0', key)
        txt.config(state=tk.DISABLED)
        ttk.Button(f, text="复制到剪贴板",
                   command=lambda: (self.clipboard_clear(),
                                    self.clipboard_append(key))).pack(pady=5)
        ttk.Button(f, text="我已抄写", command=dlg.destroy).pack(pady=5)
        self.wait_window(dlg)

    def stop(self):
        self._stop_flag = True
        self.status_text.set("正在停止...")

    def _finish(self, msg, color="#008000"):
        self.status_text.set(msg)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.app.release_task()

    def _do_encrypt(self, pwd, items, vault_path, expiry, recovery):
        try:
            ctx = TaskContext(pwd)
            mode = self.mode_var.get()

            self.log("正在收集文件...", "title")
            all_files = []
            for item in items:
                if os.path.isfile(item):
                    all_files.append(item)
                elif os.path.isdir(item):
                    for root, _, files in os.walk(item):
                        for fn in files:
                            if fn.lower().endswith(('.enc', '.vault')):
                                continue
                            all_files.append(os.path.join(root, fn))
            self.log(f"共 {len(all_files)} 个文件", "info")
            if not all_files:
                self._finish("没有可加密的文件", "#cc6600")
                return

            if mode == "batch":
                completed = []
                pending = list(all_files)
                write_journal("encrypt", "batch", completed, pending)
                total_ok = 0
                total_err = 0
                batch = []
                for i, fp in enumerate(all_files, 1):
                    if self._stop_flag:
                        break
                    batch.append(fp)
                    if len(batch) >= 20 or i == len(all_files):
                        for one in batch:
                            try:
                                dst = one + ".enc"
                                encrypt_file(ctx, one, dst,
                                             remove_original=self.remove_orig_var.get(),
                                             expiry=expiry, recovery_key=recovery)
                                completed.append(one)
                                total_ok += 1
                                self.log(f"[OK] {one}", "ok")
                            except Exception as e:
                                total_err += 1
                                self.log(f"[ERR] {one}: {e}", "err")
                        pending = [f for f in all_files if f not in completed]
                        write_journal("encrypt", "batch", completed, pending)
                        batch = []
                        self.progress_var.set(i / len(all_files) * 100)
                        self.status_text.set(
                            f"进度 {i}/{len(all_files)}  成功 {total_ok}  失败 {total_err}")
                self.progress_var.set(100)
                clear_journal()
                self._finish(f"完成：成功 {total_ok}，失败 {total_err}" +
                             ("（已停止）" if self._stop_flag else ""),
                             "#008000" if total_err == 0 else "#cc6600")
            else:  # vault
                self.log("正在打包 + 加密...", "title")
                write_journal("encrypt", "vault", [], all_files)
                import tarfile
                with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
                    tar_path = tmp.name
                try:
                    with tarfile.open(tar_path, 'w:gz') as tar:
                        for fp in all_files:
                            if self._stop_flag:
                                break
                            try:
                                tar.add(fp, arcname=os.path.basename(fp))
                            except Exception as e:
                                self.log(f"[SKIP] {fp}: {e}", "warn")
                    encrypt_file(ctx, tar_path, vault_path,
                                 remove_original=True, expiry=expiry,
                                 recovery_key=recovery)
                    self.progress_var.set(100)
                    clear_journal()
                    self.log(f"[OK] 加密容器: {vault_path}", "ok")
                    self._finish(f"完成: {vault_path}", "#008000")
                finally:
                    if os.path.exists(tar_path):
                        try:
                            os.remove(tar_path)
                        except Exception:
                            pass
        except Exception as e:
            import traceback
            self.log(traceback.format_exc(), "err")
            self._finish(f"错误：{e}", "#cc0000")


# ==================== 解密页 ====================
class DecryptTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.password_var = tk.StringVar()
        self.recovery_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_text = tk.StringVar(value="就绪")
        self.output_dir = tk.StringVar(value="")
        self.skip_bad_var = tk.BooleanVar(value=False)
        self.selected_files = []
        self._stop_flag = False
        self._worker = None
        self._build_ui()
        self._load_cfg()

    def _build_ui(self):
        lf = ttk.LabelFrame(self, text="① 待解密文件（可拖拽 .enc / .vault 到此处）")
        lf.pack(fill=tk.BOTH, expand=True, pady=4)
        body = ttk.Frame(lf)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        self.listbox = tk.Listbox(body, selectmode=tk.EXTENDED, height=6, activestyle="none")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(body, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind('<Delete>', lambda e: self._remove_selected())
        self.listbox.bind('<Double-Button-1>', lambda e: self._preview_header())
        self.listbox.bind('<Button-3>', self._show_list_menu)

        bar = ttk.Frame(lf)
        bar.pack(fill=tk.X, padx=5, pady=(0, 4))
        ttk.Button(bar, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="添加文件夹", command=self._add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="清空", command=self._clear_list).pack(side=tk.LEFT, padx=2)
        self.count_label = ttk.Label(bar, text="共 0 项", foreground="gray")
        self.count_label.pack(side=tk.RIGHT)

        out = ttk.LabelFrame(self, text="② 输出目录")
        out.pack(fill=tk.X, pady=4)
        row = ttk.Frame(out)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="解密到：", width=8).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.output_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        ttk.Button(row, text="浏览...", command=self._pick_output).pack(side=tk.LEFT, padx=3)

        pwd_lf = ttk.LabelFrame(self, text="③ 密码 / 恢复密钥")
        pwd_lf.pack(fill=tk.X, pady=4)
        row = ttk.Frame(pwd_lf)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="密码：", width=8).pack(side=tk.LEFT)
        self.pwd_entry = ttk.Entry(row, textvariable=self.password_var, show='*', width=26)
        self.pwd_entry.pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="显示/隐藏", command=self._toggle_pwd).pack(side=tk.LEFT)

        row = ttk.Frame(pwd_lf)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="恢复密钥：", width=8).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.recovery_var, width=52).pack(side=tk.LEFT, padx=3)
        ttk.Label(row, text="（可选，忘记密码时使用）", foreground="gray").pack(side=tk.LEFT)

        row = ttk.Frame(pwd_lf)
        row.pack(fill=tk.X, pady=3)
        ttk.Checkbutton(row, text="跳过损坏块（尽力恢复数据）",
                        variable=self.skip_bad_var).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="临时查看(阅后自毁)",
                   command=self._temp_view).pack(side=tk.LEFT, padx=6)

        pf = ttk.LabelFrame(self, text="④ 进度")
        pf.pack(fill=tk.X, pady=4)
        ttk.Progressbar(pf, variable=self.progress_var, maximum=100).pack(
            fill=tk.X, padx=5, pady=4)
        ttk.Label(pf, textvariable=self.status_text, anchor=tk.W,
                  foreground="#444444").pack(fill=tk.X, padx=5, pady=(0, 4))

        self.log_panel = LogPanel(self, title="⑤ 日志", height=7)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=4)

        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=4)
        self.start_btn = ttk.Button(row, text="▶ 开始解密", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        self.stop_btn = ttk.Button(row, text="■ 停止", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4)

    def _load_cfg(self):
        d = load_config().get('decrypt', {})
        self.output_dir.set(d.get('output_dir', ''))

    def _save_cfg(self):
        cfg = load_config()
        cfg['decrypt'] = {'output_dir': self.output_dir.get()}
        save_config(cfg)

    def log(self, msg, level="info"):
        self.log_panel.log(msg, level)

    def _update_count(self):
        self.count_label.config(text=f"共 {len(self.selected_files)} 项")

    def _toggle_pwd(self):
        self.pwd_entry.config(show='' if self.pwd_entry.cget('show') == '*' else '*')

    def _pick_output(self):
        d = filedialog.askdirectory(title="选择解密输出目录")
        if d:
            self.output_dir.set(d)

    def _show_list_menu(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="预览文件头", command=lambda: self._preview_header(idx))
        menu.add_command(label="打开所在文件夹", command=lambda: self._open_folder(idx))
        menu.add_command(label="复制路径", command=lambda: self._copy_path(idx))
        menu.add_separator()
        menu.add_command(label="移除此项", command=lambda: self._remove_one(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def _preview_header(self, idx=None):
        if idx is None:
            sel = self.listbox.curselection()
            if not sel:
                return
            idx = sel[0]
        path = self.selected_files[idx]
        try:
            info = read_header(path)
            h = info["header"]
            lines = [
                f"版本: v{h.get('version')}",
                f"类型: {'双空间' if h.get('dual') else '普通'}",
                f"原文件名: {h.get('filename', '（双空间）')}",
                f"原始大小: {h.get('size', 0)} bytes",
                f"加密时间: {h.get('timestamp', '?')}",
                f"过期时间: {h.get('expiry') or '无'}",
                f"恢复密钥: {'已设置' if h.get('recovery_wrapped_fk') or h.get('dual') else '未设置'}",
            ]
            if not h.get("dual"):
                lines.append(f"SHA-256: {h.get('filehash', '?')}")
            messagebox.showinfo(f"文件头: {os.path.basename(path)}", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _open_folder(self, idx):
        path = self.selected_files[idx]
        d = os.path.dirname(path) if os.path.isfile(path) else path
        if platform.system() == 'Windows':
            os.startfile(d)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', d])
        else:
            subprocess.Popen(['xdg-open', d])

    def _copy_path(self, idx):
        self.clipboard_clear()
        self.clipboard_append(self.selected_files[idx])

    def _remove_one(self, idx):
        self.listbox.delete(idx)
        del self.selected_files[idx]
        self._update_count()

    def _remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for idx in sorted(sel, reverse=True):
            self.listbox.delete(idx)
            del self.selected_files[idx]
        self._update_count()

    def _clear_list(self):
        self.listbox.delete(0, tk.END)
        self.selected_files.clear()
        self._update_count()

    def add_paths(self, paths):
        added = 0
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        if fn.lower().endswith(('.enc', '.vault')):
                            fp = os.path.join(root, fn)
                            if fp not in self.selected_files:
                                self.selected_files.append(fp)
                                self.listbox.insert(tk.END, fp)
                                added += 1
            elif os.path.isfile(p) and p.lower().endswith(('.enc', '.vault')):
                if p not in self.selected_files:
                    self.selected_files.append(p)
                    self.listbox.insert(tk.END, p)
                    added += 1
            else:
                self.log(f"跳过非加密文件: {p}", "warn")
        self._update_count()
        if added:
            self.log(f"已添加 {added} 项，共 {len(self.selected_files)} 项", "ok")

    def _add_files(self):
        fs = filedialog.askopenfilenames(
            title="选择要解密的文件",
            filetypes=[("加密文件", "*.enc *.vault"), ("所有文件", "*.*")])
        if fs:
            self.add_paths(list(fs))

    def _add_folder(self):
        d = filedialog.askdirectory(title="选择包含 .enc / .vault 的文件夹")
        if d:
            self.add_paths([d])

    def _temp_view(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个 .enc 文件")
            return
        fp = self.selected_files[sel[0]]
        if not fp.lower().endswith('.enc'):
            messagebox.showwarning("提示", "临时查看仅支持 .enc")
            return
        pwd = self.password_var.get() or simpledialog.askstring("密码", "输入密码:", show='*')
        if not pwd:
            return

        tmpdir = None
        try:
            ctx = TaskContext(pwd)
            info = read_header(fp)
            filename = info["header"]["filename"]
            tmpdir = tempfile.mkdtemp(prefix="vault_view_")
            out_path = os.path.join(tmpdir, filename)
            decrypt_file(ctx, fp, out_path, check_expiry=True)
            if platform.system() == 'Windows':
                os.startfile(out_path)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', out_path])
            else:
                subprocess.Popen(['xdg-open', out_path])
            messagebox.showinfo("临时查看",
                                f"文件已打开：\n{out_path}\n\n"
                                f"点击确定后将安全删除临时文件。")
        except PasswordError:
            messagebox.showerror("错误", "密码错误")
            return
        except ExpiredError as e:
            messagebox.showerror("已过期", str(e))
            return
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        finally:
            if tmpdir and os.path.exists(tmpdir):
                try:
                    for root, dirs, files in os.walk(tmpdir):
                        for f in files:
                            try:
                                secure_delete(os.path.join(root, f))
                            except Exception:
                                pass
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass

    def start(self):
        pwd = self.password_var.get()
        rk = self.recovery_var.get().strip()
        if not pwd and not rk:
            messagebox.showwarning("提示", "请输入密码或恢复密钥")
            return
        if not self.selected_files:
            messagebox.showwarning("提示", "请先添加要解密的文件")
            return
        out_dir = self.output_dir.get().strip()
        if not out_dir:
            messagebox.showwarning("提示", "请选择解密输出目录")
            return
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录：{e}")
                return
        if not self.app.acquire_task("解密"):
            return

        self._save_cfg()
        self._stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.log_panel.clear()
        self._worker = threading.Thread(
            target=self._do_decrypt,
            args=(pwd, rk, list(self.selected_files), out_dir, self.skip_bad_var.get()),
            daemon=True)
        self._worker.start()

    def stop(self):
        self._stop_flag = True
        self.status_text.set("正在停止...")

    def _finish(self, msg, color="#008000"):
        self.status_text.set(msg)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.app.release_task()

    def _do_decrypt(self, pwd, rk, files, out_dir, skip_bad):
        try:
            ctx = TaskContext(pwd) if pwd else None
            n = len(files)
            total_ok = 0
            total_err = 0
            completed = []
            write_journal("decrypt", "batch", completed, list(files))
            self.log(f"共 {n} 个文件待解密", "title")
            self.log(f"输出目录：{out_dir}", "info")

            for i, fp in enumerate(files, 1):
                if self._stop_flag:
                    break
                try:
                    info = read_header(fp)
                    h = info["header"]
                    if h.get("dual"):
                        st, out = decrypt_dualspace(ctx.password if ctx else pwd, fp, out_dir)
                        self.log(f"[OK] 双空间[{st}] {fp} -> {out}", "ok")
                        total_ok += 1
                    elif fp.lower().endswith('.vault'):
                        decrypt_folder(ctx, fp, out_dir)
                        self.log(f"[OK] 容器 {fp} -> {out_dir}", "ok")
                        total_ok += 1
                    else:
                        filename = h.get("filename", os.path.basename(fp) + ".dec")
                        out_path = os.path.join(out_dir, filename)
                        r = decrypt_file(ctx, fp, out_path,
                                         use_recovery_key=rk or None,
                                         skip_bad_chunks=skip_bad)
                        msg = f"[OK] {fp} -> {out_path}"
                        if r["bad_chunks"]:
                            msg += f"  (跳过 {r['bad_chunks']} 个坏块)"
                        self.log(msg, "ok")
                        total_ok += 1
                    completed.append(fp)
                except PasswordError:
                    self.log(f"[ERR] {fp}: 密码错误", "err")
                    total_err += 1
                except RecoveryKeyError as e:
                    self.log(f"[ERR] {fp}: {e}", "err")
                    total_err += 1
                except ExpiredError as e:
                    self.log(f"[ERR] {fp}: {e}", "err")
                    total_err += 1
                except IntegrityError as e:
                    self.log(f"[ERR] {fp}: 完整性失败 ({e})", "err")
                    total_err += 1
                except Exception as e:
                    self.log(f"[ERR] {fp}: {e}", "err")
                    total_err += 1

                pending = [f for f in files if f not in completed]
                write_journal("decrypt", "batch", completed, pending)
                self.progress_var.set(i / n * 100)
                self.status_text.set(f"进度 {i}/{n}  成功 {total_ok}  失败 {total_err}")

            self.progress_var.set(100)
            clear_journal()
            self._finish(f"完成：成功 {total_ok}，失败 {total_err}" +
                         ("（已停止）" if self._stop_flag else ""),
                         "#008000" if total_err == 0 else "#cc6600")
        except Exception as e:
            import traceback
            self.log(traceback.format_exc(), "err")
            self._finish(f"错误：{e}", "#cc0000")


# ==================== 健康检查页 ====================
class HealthTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.files = []
        self.password_var = tk.StringVar()
        self.full_var = tk.BooleanVar(value=False)
        self._stop_flag = False

        lf = ttk.LabelFrame(self, text="① 待检查文件")
        lf.pack(fill=tk.BOTH, expand=True, pady=4)
        body = ttk.Frame(lf)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        self.listbox = tk.Listbox(body, selectmode=tk.EXTENDED, height=6, activestyle="none")
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(body, command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=sb.set)

        bar = ttk.Frame(lf)
        bar.pack(fill=tk.X, padx=5, pady=(0, 4))
        ttk.Button(bar, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="添加文件夹", command=self._add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="清空", command=self._clear).pack(side=tk.LEFT, padx=2)

        pwd_lf = ttk.LabelFrame(self, text="② 密码（可选）")
        pwd_lf.pack(fill=tk.X, pady=4)
        row = ttk.Frame(pwd_lf)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="密码：", width=8).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.password_var, show='*', width=26).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(row, text="完整校验（逐块验证）",
                        variable=self.full_var).pack(side=tk.LEFT, padx=10)

        self.log_panel = LogPanel(self, title="③ 检查结果", height=12)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=4)

        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=4)
        ttk.Button(row, text="▶ 开始检查", command=self.start).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="■ 停止", command=self.stop).pack(side=tk.LEFT, padx=4)

    def log(self, msg, level="info"):
        self.log_panel.log(msg, level)

    def _add_files(self):
        fs = filedialog.askopenfilenames(
            title="选择加密文件",
            filetypes=[("加密文件", "*.enc *.vault"), ("所有文件", "*.*")])
        for f in fs:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert(tk.END, f)

    def _add_folder(self):
        d = filedialog.askdirectory(title="选择包含 .enc / .vault 的文件夹")
        if not d:
            return
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(('.enc', '.vault')):
                    fp = os.path.join(root, fn)
                    if fp not in self.files:
                        self.files.append(fp)
                        self.listbox.insert(tk.END, fp)

    def _clear(self):
        self.listbox.delete(0, tk.END)
        self.files.clear()

    def start(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加要检查的文件")
            return
        self._stop_flag = False
        self.log_panel.clear()
        threading.Thread(target=self._do_check, daemon=True).start()

    def stop(self):
        self._stop_flag = True

    def _do_check(self):
        pwd = self.password_var.get()
        full = self.full_var.get()
        self.log(f"开始检查 {len(self.files)} 个文件...", "title")
        ok_count = 0
        fail_count = 0
        for i, fp in enumerate(self.files, 1):
            if self._stop_flag:
                break
            try:
                r = health_check(fp, password=pwd or None, full=full)
                if r["valid_header"] and (r["valid_hmac"] is None or r["valid_hmac"]):
                    ok_count += 1
                    info = f"[OK] {os.path.basename(fp)}"
                    if r.get("filename"):
                        info += f"  原文件: {r['filename']}"
                    if r.get("size") is not None:
                        info += f"  {r['size']}B"
                    if r.get("expiry"):
                        info += f"  过期: {r['expiry']}"
                    if r.get("is_dual"):
                        info += "  [双空间]"
                    if r.get("space"):
                        info += f"  空间: {r['space']}"
                    if r.get("bad_chunks") is not None:
                        info += f"  坏块: {r['bad_chunks']}/{r.get('total_chunks', '?')}"
                    self.log(info, "ok")
                else:
                    fail_count += 1
                    err = r.get("error") or "校验失败"
                    self.log(f"[FAIL] {fp}: {err}", "err")
            except Exception as e:
                fail_count += 1
                self.log(f"[FAIL] {fp}: {e}", "err")
            self.update_idletasks()
        self.log(f"检查完成：成功 {ok_count}，失败 {fail_count}", "title")


# ==================== 工具页 ====================
class ToolsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app

        rk_lf = ttk.LabelFrame(self, text="① 恢复密钥生成器")
        rk_lf.pack(fill=tk.X, pady=4)
        row = ttk.Frame(rk_lf)
        row.pack(fill=tk.X, pady=4, padx=5)
        ttk.Button(row, text="生成恢复密钥",
                   command=self._gen_recovery).pack(side=tk.LEFT, padx=3)
        self.rk_text = tk.Text(rk_lf, height=3, wrap=tk.WORD, font=("Consolas", 11))
        self.rk_text.pack(fill=tk.X, padx=5, pady=4)
        ttk.Button(rk_lf, text="复制到剪贴板",
                   command=self._copy_rk).pack(pady=4)

        stg_lf = ttk.LabelFrame(self, text="② 隐写术（把加密文件藏进图片）")
        stg_lf.pack(fill=tk.X, pady=4)
        row = ttk.Frame(stg_lf)
        row.pack(fill=tk.X, pady=3, padx=5)
        ttk.Button(row, text="隐藏：加密文件 → 图片",
                   command=self._stego_hide).pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="提取：图片 → 加密文件",
                   command=self._stego_reveal).pack(side=tk.LEFT, padx=3)
        ttk.Label(stg_lf, text="提示：需要 pip install stegano；载体建议用 PNG（无损）",
                  foreground="gray").pack(anchor=tk.W, padx=5, pady=(0, 4))

        dual_lf = ttk.LabelFrame(self, text="③ 双空间（假密码 / 真密码）")
        dual_lf.pack(fill=tk.X, pady=4)
        ttk.Label(dual_lf,
                  text="真实密码解出真实文件，假密码解出诱饵文件。\n"
                       "两者都有效，攻击者无法分辨。",
                  justify=tk.LEFT).pack(anchor=tk.W, padx=5, pady=4)
        row = ttk.Frame(dual_lf)
        row.pack(fill=tk.X, pady=4, padx=5)
        ttk.Button(row, text="创建双空间文件",
                   command=self._dual_create).pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="解密双空间文件",
                   command=self._dual_decrypt).pack(side=tk.LEFT, padx=3)

        other_lf = ttk.LabelFrame(self, text="④ 其他")
        other_lf.pack(fill=tk.X, pady=4)
        row = ttk.Frame(other_lf)
        row.pack(fill=tk.X, pady=4, padx=5)
        ttk.Button(row, text="生成强密码",
                   command=self._gen_pwd).pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="注册右键菜单（Windows）",
                   command=self._register_menu).pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="卸载右键菜单",
                   command=self._unregister_menu).pack(side=tk.LEFT, padx=3)

    def _gen_recovery(self):
        key = generate_recovery_key()
        self.rk_text.delete('1.0', tk.END)
        self.rk_text.insert('1.0', key)

    def _copy_rk(self):
        content = self.rk_text.get('1.0', tk.END).strip()
        if not content:
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("提示", "已复制到剪贴板")

    def _gen_pwd(self):
        pwd = generate_strong_password(16)
        self.clipboard_clear()
        self.clipboard_append(pwd)
        messagebox.showinfo("强密码", f"已生成并复制：\n\n{pwd}")

    def _stego_hide(self):
        enc = filedialog.askopenfilename(
            title="选择加密文件", filetypes=[("加密文件", "*.enc")])
        if not enc:
            return
        carrier = filedialog.askopenfilename(
            title="选择载体图片", filetypes=[("图片", "*.png *.jpg *.bmp")])
        if not carrier:
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not out:
            return
        try:
            steganography_hide(enc, carrier, out)
            messagebox.showinfo("完成", f"已隐藏到：\n{out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _stego_reveal(self):
        img = filedialog.askopenfilename(
            title="选择隐写图片", filetypes=[("图片", "*.png *.jpg *.bmp")])
        if not img:
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".enc", filetypes=[("加密文件", "*.enc")])
        if not out:
            return
        try:
            steganography_reveal(img, out)
            messagebox.showinfo("完成", f"已提取到：\n{out}\n\n请到'解密'页解密。")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _dual_create(self):
        real = filedialog.askopenfilename(title="选择真实文件（真密码打开）")
        if not real:
            return
        fake = filedialog.askopenfilename(title="选择诱饵文件（假密码打开）")
        if not fake:
            return
        out = filedialog.asksaveasfilename(
            title="保存双空间文件", defaultextension=".ds",
            initialfile="secret.ds")
        if not out:
            return
        p1 = simpledialog.askstring("真实密码", "设置真实密码:", show='*')
        if not p1:
            return
        p2 = simpledialog.askstring("假密码", "设置假密码:", show='*')
        if not p2:
            return
        if p1 == p2:
            messagebox.showerror("错误", "两个密码不能相同")
            return
        try:
            encrypt_dualspace(real, fake, p1, p2, out)
            messagebox.showinfo("完成",
                                f"双空间文件已创建：\n{out}\n\n"
                                f"真实密码 → {os.path.basename(real)}\n"
                                f"假密码 → {os.path.basename(fake)}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _dual_decrypt(self):
        f = filedialog.askopenfilename(
            title="选择双空间文件",
            filetypes=[("双空间", "*.ds"), ("所有文件", "*.*")])
        if not f:
            return
        out = filedialog.askdirectory(title="选择输出目录")
        if not out:
            return
        pwd = simpledialog.askstring("密码", "输入密码:", show='*')
        if not pwd:
            return
        try:
            st, path = decrypt_dualspace(pwd, f, out)
            messagebox.showinfo("完成", f"使用 [{st}] 空间\n输出：{path}")
        except PasswordError:
            messagebox.showerror("错误", "密码错误")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _register_menu(self):
        try:
            from vault_menu_setup import register_menu, _find_cli_exe, _find_gui_exe
            if register_menu():
                msg = ("右键菜单注册成功\n\n"
                       "Win10：右键即可看到\n"
                       "Win11：点击右键菜单底部 '显示更多选项'")
                if is_frozen():
                    cli = _find_cli_exe()
                    gui = _find_gui_exe()
                    msg += f"\n\nCLI: {cli or '(未找到)'}\nGUI: {gui or '(未找到)'}"
                    if not cli:
                        msg += "\n\n⚠ 未找到 PersonalVaultCLI.exe，右键菜单点击后可能无效。"
                messagebox.showinfo("成功", msg)
            else:
                messagebox.showerror("失败", "注册失败，请查看控制台")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _unregister_menu(self):
        try:
            from vault_menu_setup import unregister_menu
            unregister_menu()
            messagebox.showinfo("成功", "已卸载")
        except Exception as e:
            messagebox.showerror("错误", str(e))


# ==================== 主窗口 ====================
BaseTk = TkinterDnD.Tk if HAS_DND else tk.Tk


class VaultGUI(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("PersonalVault - 个人文件加密 v3")
        self.geometry("980x860")
        self.minsize(900, 760)
        self._busy = False
        self._dark = load_config().get('dark', False)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.encrypt_tab = EncryptTab(self.notebook, self)
        self.decrypt_tab = DecryptTab(self.notebook, self)
        self.health_tab = HealthTab(self.notebook, self)
        self.tools_tab = ToolsTab(self.notebook, self)

        self.notebook.add(self.encrypt_tab, text="  加密  ")
        self.notebook.add(self.decrypt_tab, text="  解密  ")
        self.notebook.add(self.health_tab, text="  健康检查  ")
        self.notebook.add(self.tools_tab, text="  工具  ")

        # 菜单
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="打开程序目录", command=self._open_app_dir)
        fm.add_separator()
        fm.add_command(label="退出", command=self.destroy)
        menubar.add_cascade(label="文件", menu=fm)

        vm = tk.Menu(menubar, tearoff=0)
        self._dark_var = tk.BooleanVar(value=self._dark)
        vm.add_checkbutton(label="深色主题", variable=self._dark_var,
                           command=self._toggle_theme)
        menubar.add_cascade(label="视图", menu=vm)

        tm = tk.Menu(menubar, tearoff=0)
        tm.add_command(label="生成恢复密钥", command=self.show_recovery_dialog)
        tm.add_command(label="生成强密码", command=self._menu_gen_pwd)
        tm.add_separator()
        tm.add_command(label="注册右键菜单（Win）", command=self._menu_register)
        tm.add_command(label="卸载右键菜单（Win）", command=self._menu_unregister)
        menubar.add_cascade(label="工具", menu=tm)

        hm = tk.Menu(menubar, tearoff=0)
        hm.add_command(label="快捷键", command=self._show_shortcuts)
        hm.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=hm)
        self.config(menu=menubar)

        # 状态栏
        hint = "拖放：已启用" if HAS_DND else "拖放：未启用 (pip install tkinterdnd2)"
        if not HAS_SCANNER:
            hint += "  |  扫描模块: 缺失"
        if is_frozen():
            hint += "  |  打包版"
        self.status_bar = ttk.Label(self, text=hint, relief=tk.SUNKEN,
                                    anchor=tk.W, foreground="gray")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_global_drop)

        # 快捷键
        self.bind_all('<Control-o>', lambda e: self._focus_encrypt_add_files())
        self.bind_all('<Control-d>', lambda e: self._focus_encrypt_add_folder())
        self.bind_all('<Control-e>', lambda e: self.encrypt_tab.start())
        self.bind_all('<Control-r>', lambda e: self.decrypt_tab.start())
        self.bind_all('<F5>', lambda e: self._refresh_current())
        self.bind_all('<Escape>', lambda e: self._stop_current())
        self.bind_all('<F1>', lambda e: self._show_shortcuts())
        self.bind_all('<Control-q>', lambda e: self.destroy())

        self.after(100, lambda: THEME.apply(self, self._dark))
        self.after(300, self._check_journal)

    # ---------- 主题 ----------
    def _toggle_theme(self):
        self._dark = self._dark_var.get()
        THEME.apply(self, self._dark)
        cfg = load_config()
        cfg['dark'] = self._dark
        save_config(cfg)

    # ---------- 任务互斥 ----------
    def acquire_task(self, label):
        if self._busy:
            messagebox.showwarning("提示", "已有任务在执行中")
            return False
        self._busy = True
        self.status_bar.config(text=f"任务执行中：{label}")
        return True

    def release_task(self):
        self._busy = False
        hint = "拖放：已启用" if HAS_DND else "拖放：未启用"
        if not HAS_SCANNER:
            hint += "  |  扫描模块: 缺失"
        if is_frozen():
            hint += "  |  打包版"
        self.status_bar.config(text=hint)

    # ---------- 全局拖放 ----------
    def _on_global_drop(self, event):
        if self._busy:
            messagebox.showwarning("提示", "有任务正在执行")
            return
        paths = self.tk.splitlist(event.data)
        enc_like, plain, folders = [], [], []
        for p in paths:
            if not os.path.exists(p):
                continue
            if os.path.isdir(p):
                folders.append(p)
            elif p.lower().endswith(('.enc', '.vault', '.ds')):
                enc_like.append(p)
            else:
                plain.append(p)

        if enc_like:
            self.notebook.select(self.decrypt_tab)
            self.decrypt_tab.add_paths(enc_like)
        if plain:
            self.notebook.select(self.encrypt_tab)
            self.encrypt_tab.add_paths(plain)
        if folders:
            ans = messagebox.askyesno(
                "文件夹拖入",
                f"检测到 {len(folders)} 个文件夹。\n\n"
                "是 = 添加到加密列表\n否 = 添加到解密列表")
            if ans:
                self.notebook.select(self.encrypt_tab)
                self.encrypt_tab.add_paths(folders)
            else:
                self.notebook.select(self.decrypt_tab)
                self.decrypt_tab.add_paths(folders)

    # ---------- 中断恢复 ----------
    def _check_journal(self):
        if not os.path.exists(JOURNAL_PATH):
            return
        try:
            with open(JOURNAL_PATH, encoding='utf-8') as f:
                journal = json.load(f)
        except Exception:
            clear_journal()
            return
        pending = journal.get("pending", [])
        if not pending:
            clear_journal()
            return
        ans = messagebox.askyesno(
            "发现未完成任务",
            f"上次有未完成任务：\n"
            f"  操作: {journal.get('operation')}\n"
            f"  模式: {journal.get('mode')}\n"
            f"  已完成: {len(journal.get('completed', []))}\n"
            f"  剩余: {len(pending)}\n\n"
            f"是否加载剩余文件？")
        if ans:
            if journal.get("operation") == "encrypt":
                self.notebook.select(self.encrypt_tab)
                self.encrypt_tab.add_paths(pending)
            else:
                self.notebook.select(self.decrypt_tab)
                self.decrypt_tab.add_paths(pending)
        clear_journal()

    # ---------- 菜单动作 ----------
    def _open_app_dir(self):
        d = get_app_dir()
        if platform.system() == 'Windows':
            os.startfile(d)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', d])
        else:
            subprocess.Popen(['xdg-open', d])

    def _menu_gen_pwd(self):
        pwd = generate_strong_password(16)
        self.clipboard_clear()
        self.clipboard_append(pwd)
        messagebox.showinfo("强密码", f"已复制到剪贴板：\n\n{pwd}")

    def _menu_register(self):
        self.tools_tab._register_menu()

    def _menu_unregister(self):
        self.tools_tab._unregister_menu()

    def show_recovery_dialog(self):
        key = generate_recovery_key()
        dlg = tk.Toplevel(self)
        dlg.title("恢复密钥")
        dlg.geometry("560x280")
        dlg.transient(self)
        dlg.grab_set()
        f = ttk.Frame(dlg, padding=15)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="⚠ 请抄写并妥善保存",
                  font=("", 11, "bold"), foreground="#cc0000").pack(anchor=tk.W)
        ttk.Label(f, text="加密时勾选'生成恢复密钥'可让此密钥生效。",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 8))
        txt = tk.Text(f, height=3, wrap=tk.WORD, font=("Consolas", 11))
        txt.pack(fill=tk.X, pady=5)
        txt.insert('1.0', key)
        ttk.Button(f, text="复制到剪贴板",
                   command=lambda: (self.clipboard_clear(),
                                    self.clipboard_append(key))).pack(pady=5)

    def _show_shortcuts(self):
        msg = """快捷键：
Ctrl+O    添加文件到加密列表
Ctrl+D    添加文件夹到加密列表
Ctrl+E    开始加密
Ctrl+R    开始解密
F5        刷新当前标签页
Esc       停止当前任务
F1        显示此帮助
Ctrl+Q    退出

右键列表项可预览文件头 / 打开目录 / 复制路径"""
        messagebox.showinfo("快捷键", msg)

    def _show_about(self):
        frozen_tag = "（打包版）" if is_frozen() else "（源码版）"
        messagebox.showinfo(
            "关于 PersonalVault",
            f"PersonalVault v3 {frozen_tag}\n\n"
            "AES-256-GCM 分块加密\n"
            "PBKDF2-HMAC-SHA256 (20万次迭代)\n"
            "主密钥 + 文件密钥两层结构\n"
            "恢复密钥 / 双空间 / 隐写术 / 健康检查\n\n"
            f"程序目录：\n{get_app_dir()}\n\n"
            "依赖：cryptography, tkinterdnd2(可选), stegano(可选)")

    def _focus_encrypt_add_files(self):
        self.notebook.select(self.encrypt_tab)
        self.encrypt_tab._add_files()

    def _focus_encrypt_add_folder(self):
        self.notebook.select(self.encrypt_tab)
        self.encrypt_tab._add_folder()

    def _refresh_current(self):
        tab = self.notebook.nametowidget(self.notebook.select())
        if hasattr(tab, '_update_count'):
            tab._update_count()

    def _stop_current(self):
        tab = self.notebook.nametowidget(self.notebook.select())
        if hasattr(tab, 'stop'):
            tab.stop()

    def destroy(self):
        try:
            self.encrypt_tab._save_cfg()
            self.decrypt_tab._save_cfg()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    app = VaultGUI()
    app.mainloop()