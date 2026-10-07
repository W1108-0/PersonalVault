# vault_cli.py
"""PersonalVault 命令行版（兼容 PyInstaller 打包）"""
import argparse
import os
import sys
import getpass
import subprocess
from datetime import datetime, timedelta, timezone

from personal_vault import (
    TaskContext, encrypt_file, decrypt_file, read_header,
    encrypt_folder, decrypt_folder,
    encrypt_dualspace, decrypt_dualspace,
    health_check, steganography_hide, steganography_reveal,
    PasswordError, IntegrityError, ExpiredError, RecoveryKeyError,
    generate_strong_password, generate_recovery_key,
)


def _is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def _get_app_dir() -> str:
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _find_gui_exe() -> str:
    """在打包模式下寻找 GUI 可执行文件"""
    d = _get_app_dir()
    for name in ("PersonalVault.exe", "PersonalVault", "vault.exe"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return ""


def _get_pwd(args, prompt="密码: "):
    return args.password or getpass.getpass(prompt)


def _parse_expiry(text):
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


def cmd_encrypt(args):
    pwd = _get_pwd(args)
    ctx = TaskContext(pwd)
    try:
        expiry = _parse_expiry(args.expiry)
    except ValueError as e:
        print(f"[ERR] {e}", file=sys.stderr)
        sys.exit(1)

    recovery = args.recovery
    if recovery == "auto":
        recovery = generate_recovery_key()
        print("=" * 60)
        print("恢复密钥（请抄写并安全保管，丢失后无法找回）：")
        print(f"  {recovery}")
        print("=" * 60)

    for f in args.files:
        try:
            if os.path.isdir(f):
                out = f.rstrip(os.sep + '/') + ".vault"
                encrypt_folder(ctx, f, out, expiry=expiry, recovery_key=recovery)
                print(f"[OK] {f} -> {out}")
            else:
                out = f + ".enc"
                encrypt_file(ctx, f, out, remove_original=args.remove,
                             expiry=expiry, recovery_key=recovery)
                print(f"[OK] {f} -> {out}")
        except Exception as e:
            print(f"[ERR] {f}: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_decrypt(args):
    pwd = _get_pwd(args, "密码（或使用 --recovery-key）: ") if not args.recovery_key else ""
    ctx = TaskContext(pwd) if pwd else None

    for f in args.files:
        try:
            info = read_header(f)
            h = info["header"]
            if h.get("dual"):
                st, out = decrypt_dualspace(pwd, f, args.output or os.path.dirname(f) or ".")
                print(f"[OK] 双空间[{st}] {f} -> {out}")
                continue
            if f.lower().endswith('.vault'):
                out = decrypt_folder(ctx, f, args.output or os.path.dirname(f) or ".")
                print(f"[OK] 容器 {f} -> {out}")
            else:
                name = h.get("filename", os.path.basename(f) + ".dec")
                out_dir = args.output or os.path.dirname(f) or "."
                out_path = os.path.join(out_dir, name)
                r = decrypt_file(ctx, f, out_path,
                                 use_recovery_key=args.recovery_key,
                                 skip_bad_chunks=args.skip_bad)
                msg = f"[OK] {f} -> {out_path}"
                if r["bad_chunks"]:
                    msg += f"  (跳过 {r['bad_chunks']} 个坏块)"
                print(msg)
        except PasswordError:
            print(f"[ERR] {f}: 密码错误", file=sys.stderr)
            sys.exit(2)
        except RecoveryKeyError as e:
            print(f"[ERR] {f}: {e}", file=sys.stderr)
            sys.exit(2)
        except ExpiredError as e:
            print(f"[ERR] {f}: {e}", file=sys.stderr)
            sys.exit(3)
        except Exception as e:
            print(f"[ERR] {f}: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_check(args):
    pwd = args.password
    if args.full and not pwd:
        pwd = getpass.getpass("密码: ")
    ok_all = True
    for f in args.files:
        r = health_check(f, password=pwd, full=args.full)
        status = "OK" if (r["valid_header"] and (r["valid_hmac"] is None or r["valid_hmac"])) else "FAIL"
        if status != "OK":
            ok_all = False
        print(f"[{status}] {f}")
        if r.get("filename"):
            print(f"    原文件名: {r['filename']}")
        if r.get("size") is not None:
            print(f"    大小: {r['size']} bytes")
        if r.get("expiry"):
            print(f"    过期: {r['expiry']}")
        if r.get("is_dual"):
            print(f"    类型: 双空间")
        if r.get("space"):
            print(f"    密码匹配空间: {r['space']}")
        if r.get("bad_chunks") is not None:
            print(f"    坏块: {r['bad_chunks']} / {r.get('total_chunks', '?')}")
        if r.get("error"):
            print(f"    错误: {r['error']}")
    sys.exit(0 if ok_all else 1)


def cmd_info(args):
    for f in args.files:
        try:
            info = read_header(f)
            h = info["header"]
            print(f"=== {f} ===")
            for k, v in h.items():
                if isinstance(v, str) and len(v) > 80:
                    v = v[:77] + "..."
                print(f"  {k}: {v}")
        except Exception as e:
            print(f"[ERR] {f}: {e}", file=sys.stderr)


def cmd_hide(args):
    steganography_hide(args.enc, args.carrier, args.output)
    print(f"[OK] 已隐藏到: {args.output}")


def cmd_reveal(args):
    steganography_reveal(args.image, args.output)
    print(f"[OK] 提取到: {args.output}")


def cmd_dual(args):
    p1 = args.real_pwd or getpass.getpass("真实密码: ")
    p2 = args.fake_pwd or getpass.getpass("假密码: ")
    encrypt_dualspace(args.real, args.fake, p1, p2, args.output)
    print(f"[OK] 双空间已创建: {args.output}")


def cmd_dual_decrypt(args):
    pwd = args.password or getpass.getpass("密码: ")
    st, out = decrypt_dualspace(pwd, args.file, args.output)
    print(f"[OK] 使用 [{st}] 空间 -> {out}")


def cmd_genkey(args):
    print(generate_recovery_key())


def cmd_genpwd(args):
    print(generate_strong_password(args.length))


def cmd_gui(args):
    """启动 GUI：打包模式找 PersonalVault.exe，源码模式启动 Python 脚本"""
    if _is_frozen():
        gui_exe = _find_gui_exe()
        if gui_exe:
            # Windows 下用 DETACHED_PROCESS 让 GUI 独立运行
            if sys.platform == "win32":
                subprocess.Popen([gui_exe],
                                 creationflags=subprocess.DETACHED_PROCESS |
                                                subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen([gui_exe])
            return
        print("[ERR] 未找到 PersonalVault.exe，请确认与 PersonalVaultCLI.exe 在同一目录",
              file=sys.stderr)
        sys.exit(1)
    else:
        script = os.path.join(_get_app_dir(), "integrated_vault_gui.py")
        if not os.path.exists(script):
            print(f"[ERR] 未找到 {script}", file=sys.stderr)
            sys.exit(1)
        subprocess.Popen([sys.executable, script])
        print(f"[OK] 已启动 {script}")


def cmd_menu(args):
    """注册/卸载右键菜单"""
    try:
        from vault_menu_setup import register_menu, unregister_menu
    except ImportError:
        print("[ERR] 未找到 vault_menu_setup.py / .pyc", file=sys.stderr)
        sys.exit(1)

    if args.action == "register":
        ok = register_menu()
        print("注册成功" if ok else "注册失败")
        if ok:
            print("Win11 用户请点击右键菜单底部的 '显示更多选项' 查看。")
            if _is_frozen():
                from vault_menu_setup import _find_cli_exe, _find_gui_exe
                cli = _find_cli_exe()
                gui = _find_gui_exe()
                print(f"  CLI: {cli or '(未找到)'}")
                print(f"  GUI: {gui or '(未找到)'}")
    else:
        ok = unregister_menu()
        print("已卸载" if ok else "未注册")


def main():
    p = argparse.ArgumentParser(prog="PersonalVaultCLI", description="PersonalVault CLI v3")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("encrypt", help="加密")
    pe.add_argument("files", nargs="+")
    pe.add_argument("-p", "--password")
    pe.add_argument("-e", "--expiry", help="天数或 YYYY-MM-DD")
    pe.add_argument("-r", "--remove", action="store_true", help="加密后安全删除原文件")
    pe.add_argument("--recovery", nargs='?', const="auto", help="生成恢复密钥（auto）或指定")
    pe.set_defaults(func=cmd_encrypt)

    pd = sub.add_parser("decrypt", help="解密")
    pd.add_argument("files", nargs="+")
    pd.add_argument("-p", "--password")
    pd.add_argument("-o", "--output")
    pd.add_argument("--recovery-key")
    pd.add_argument("--skip-bad", action="store_true", help="跳过损坏块")
    pd.set_defaults(func=cmd_decrypt)

    pc = sub.add_parser("check", help="健康检查")
    pc.add_argument("files", nargs="+")
    pc.add_argument("-p", "--password")
    pc.add_argument("--full", action="store_true", help="完整校验每个分块")
    pc.set_defaults(func=cmd_check)

    pi = sub.add_parser("info", help="查看文件头")
    pi.add_argument("files", nargs="+")
    pi.set_defaults(func=cmd_info)

    ph = sub.add_parser("hide", help="隐写（加密文件藏进图片）")
    ph.add_argument("enc")
    ph.add_argument("carrier")
    ph.add_argument("output")
    ph.set_defaults(func=cmd_hide)

    pr = sub.add_parser("reveal", help="从图片提取隐藏的加密文件")
    pr.add_argument("image")
    pr.add_argument("output")
    pr.set_defaults(func=cmd_reveal)

    pdu = sub.add_parser("dual", help="创建双空间")
    pdu.add_argument("real")
    pdu.add_argument("fake")
    pdu.add_argument("-p1", "--real-pwd")
    pdu.add_argument("-p2", "--fake-pwd")
    pdu.add_argument("-o", "--output", required=True)
    pdu.set_defaults(func=cmd_dual)

    pdud = sub.add_parser("dual-decrypt", help="解密双空间文件")
    pdud.add_argument("file")
    pdud.add_argument("-p", "--password")
    pdud.add_argument("-o", "--output", required=True)
    pdud.set_defaults(func=cmd_dual_decrypt)

    sub.add_parser("genkey", help="生成恢复密钥").set_defaults(func=cmd_genkey)

    pg = sub.add_parser("genpwd", help="生成强密码")
    pg.add_argument("-l", "--length", type=int, default=16)
    pg.set_defaults(func=cmd_genpwd)

    sub.add_parser("gui", help="启动图形界面").set_defaults(func=cmd_gui)

    pm = sub.add_parser("menu", help="右键菜单管理")
    pm.add_argument("action", choices=["register", "unregister"])
    pm.set_defaults(func=cmd_menu)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()