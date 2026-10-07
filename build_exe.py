# build_exe.py
"""一键打包脚本"""
import os
import sys
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")


def run(cmd):
    print(f"\n>>> {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=HERE)
    if r.returncode != 0:
        print(f"[ERR] 命令失败，返回码 {r.returncode}")
        sys.exit(1)


def clean():
    for d in (DIST, BUILD):
        if os.path.exists(d):
            print(f"清理 {d}")
            shutil.rmtree(d, ignore_errors=True)


def main():
    clean()

    # 检查 pyinstaller
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("请先安装：pip install pyinstaller")
        sys.exit(1)

    # 1. GUI 版（无控制台）
    run(f'{sys.executable} -m PyInstaller --clean --noconfirm PersonalVault.spec')

    # 2. CLI 版（带控制台）
    run(f'{sys.executable} -m PyInstaller --clean --noconfirm PersonalVaultCLI.spec')

    print("\n" + "=" * 60)
    print("打包完成！输出目录：")
    print(f"  {DIST}")
    print()
    print("生成的文件：")
    for f in os.listdir(DIST):
        p = os.path.join(DIST, f)
        size = os.path.getsize(p) / (1024 * 1024) if os.path.isfile(p) else 0
        print(f"  - {f}  ({size:.1f} MB)" if os.path.isfile(p) else f"  - {f}/")
    print("=" * 60)
    print()
    print("使用方式：")
    print("  1) 双击 PersonalVault.exe 打开 GUI")
    print("  2) 将 PersonalVault.exe 和 PersonalVaultCLI.exe 放到同一目录")
    print("  3) 命令行：PersonalVaultCLI.exe encrypt D:\\a.txt -p 密码")
    print("  4) 注册右键菜单：")
    print("       PersonalVaultCLI.exe menu register")
    print("=" * 60)


if __name__ == "__main__":
    main()