# vault_menu_setup.py
"""
Windows 右键菜单注册工具（兼容源码运行和 PyInstaller 打包）
- Win10 传统右键菜单 ✓
- Win11 "显示更多选项" 菜单 ✓
"""
import os
import sys

MENU_LABEL_ENC = "PersonalVault 加密"
MENU_LABEL_DEC = "PersonalVault 解密"
MENU_LABEL_DIR = "PersonalVault 加密此文件夹"
MENU_LABEL_BG = "PersonalVault 打开"


def _is_frozen() -> bool:
    """是否由 PyInstaller 打包运行"""
    return getattr(sys, 'frozen', False)


def _get_app_dir() -> str:
    """返回程序所在目录（打包后为 exe 所在目录）"""
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _find_cli_exe() -> str:
    """在打包模式下，寻找 CLI 可执行文件"""
    app_dir = _get_app_dir()
    for name in ("PersonalVaultCLI.exe", "PersonalVaultCLI", "vault_cli.exe"):
        p = os.path.join(app_dir, name)
        if os.path.exists(p):
            return p
    return ""


def _find_gui_exe() -> str:
    """在打包模式下，寻找 GUI 可执行文件"""
    app_dir = _get_app_dir()
    for name in ("PersonalVault.exe", "PersonalVault", "vault.exe"):
        p = os.path.join(app_dir, name)
        if os.path.exists(p):
            return p
    return ""


def _build_cli_command(action: str, target: str) -> str:
    """
    生成右键菜单 command 值，兼容打包/源码两种模式：
    - 打包模式：  "C:\...\PersonalVaultCLI.exe" encrypt "%1"
    - 源码模式：  "C:\...\python.exe" "C:\...\vault_cli.py" encrypt "%1"
    """
    if _is_frozen():
        cli_exe = _find_cli_exe()
        if cli_exe:
            return f'"{cli_exe}" {action} "{target}"'
        # 找不到 CLI 时退回到同目录下的 python
        return f'"{sys.executable}" {action} "{target}"'

    py = sys.executable
    cli = os.path.join(_get_app_dir(), "vault_cli.py")
    return f'"{py}" "{cli}" {action} "{target}"'


def _build_gui_command() -> str:
    """生成 GUI 启动命令"""
    if _is_frozen():
        gui_exe = _find_gui_exe()
        if gui_exe:
            return f'"{gui_exe}"'
        return f'"{sys.executable}"'
    py = sys.executable
    gui = os.path.join(_get_app_dir(), "integrated_vault_gui.py")
    return f'"{py}" "{gui}"'


def _icon() -> str:
    """图标路径"""
    d = _get_app_dir()
    for name in ("vault.ico", "vault.png"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    # 打包模式下，尝试直接使用 exe 自身作为图标来源
    if _is_frozen():
        exe = _find_gui_exe() or _find_cli_exe()
        if exe:
            return exe
    return ""


def register_menu():
    if sys.platform != "win32":
        print("仅支持 Windows")
        return False
    try:
        import winreg
    except ImportError:
        return False

    icon = _icon()
    HKCU = winreg.HKEY_CURRENT_USER

    def _create(key_path, default=None, **values):
        k = winreg.CreateKey(HKCU, key_path)
        if default is not None:
            winreg.SetValue(k, "", winreg.REG_SZ, default)
        for name, val in values.items():
            if val is not None:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        return k

    try:
        # === 文件：加密 ===
        _create(r"Software\Classes\*\shell\PersonalVaultEncrypt",
                default=MENU_LABEL_ENC, Icon=icon, MultiSelectModel="Player")
        _create(r"Software\Classes\*\shell\PersonalVaultEncrypt\command",
                default=_build_cli_command("encrypt", "%1"))

        # === 文件：解密 ===
        _create(r"Software\Classes\*\shell\PersonalVaultDecrypt",
                default=MENU_LABEL_DEC, Icon=icon, MultiSelectModel="Player")
        _create(r"Software\Classes\*\shell\PersonalVaultDecrypt\command",
                default=_build_cli_command("decrypt", "%1"))

        # === 目录：加密此文件夹 ===
        _create(r"Software\Classes\Directory\shell\PersonalVaultEncryptDir",
                default=MENU_LABEL_DIR, Icon=icon)
        _create(r"Software\Classes\Directory\shell\PersonalVaultEncryptDir\command",
                default=_build_cli_command("encrypt", "%1"))

        # === 目录背景：打开 GUI ===
        _create(r"Software\Classes\Directory\Background\shell\PersonalVaultBg",
                default=MENU_LABEL_BG, Icon=icon)
        _create(r"Software\Classes\Directory\Background\shell\PersonalVaultBg\command",
                default=_build_gui_command())

        # === .enc / .vault 文件：解密 ===
        for ext in (".enc", ".vault"):
            _create(rf"Software\Classes\{ext}\shell\PersonalVaultDecrypt",
                    default=MENU_LABEL_DEC, Icon=icon)
            _create(rf"Software\Classes\{ext}\shell\PersonalVaultDecrypt\command",
                    default=_build_cli_command("decrypt", "%1"))

        _refresh_shell()
        return True
    except Exception as e:
        print(f"注册失败: {e}")
        return False


def unregister_menu():
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    HKCU = winreg.HKEY_CURRENT_USER
    keys = [
        r"Software\Classes\*\shell\PersonalVaultEncrypt\command",
        r"Software\Classes\*\shell\PersonalVaultEncrypt",
        r"Software\Classes\*\shell\PersonalVaultDecrypt\command",
        r"Software\Classes\*\shell\PersonalVaultDecrypt",
        r"Software\Classes\Directory\shell\PersonalVaultEncryptDir\command",
        r"Software\Classes\Directory\shell\PersonalVaultEncryptDir",
        r"Software\Classes\Directory\Background\shell\PersonalVaultBg\command",
        r"Software\Classes\Directory\Background\shell\PersonalVaultBg",
        r"Software\Classes\.enc\shell\PersonalVaultDecrypt\command",
        r"Software\Classes\.enc\shell\PersonalVaultDecrypt",
        r"Software\Classes\.vault\shell\PersonalVaultDecrypt\command",
        r"Software\Classes\.vault\shell\PersonalVaultDecrypt",
    ]
    for k in keys:
        try:
            winreg.DeleteKey(HKCU, k)
        except FileNotFoundError:
            pass
        except Exception:
            pass
    _refresh_shell()
    return True


def _refresh_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def register_win11_top_menu():
    print("=" * 60)
    print("Win11 一级菜单注册说明")
    print("=" * 60)
    print("Win11 一级菜单需要 MSIX 稀疏包 + COM IExplorerCommand 组件，")
    print("纯 Python 无法直接注册。")
    print()
    print("当前方案已注册的菜单会出现在：")
    print("  - Win10 传统右键菜单（一级）")
    print("  - Win11 右键菜单 → '显示更多选项'")
    print("=" * 60)
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: PersonalVaultCLI menu register | unregister")
        print("或:  python vault_menu_setup.py register | unregister | win11")
        sys.exit(1)
    act = sys.argv[1]
    if act == "register":
        if register_menu():
            print("右键菜单注册成功")
            print("  Win10：右键即可看到")
            print("  Win11：请点击右键菜单底部的 '显示更多选项'")
            if _is_frozen():
                print(f"  CLI 路径: {_find_cli_exe() or '(未找到 PersonalVaultCLI.exe)'}")
        else:
            print("注册失败")
    elif act == "unregister":
        unregister_menu()
        print("已卸载")
    elif act == "win11":
        register_win11_top_menu()
    else:
        print("未知命令")