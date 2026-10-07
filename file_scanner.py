"""
文件扫描模块
提供全盘扫描功能，自动排除系统目录，并可过滤常见文件类型。
适合作为模块导入，或在命令行直接运行。
"""

import os
import string
from typing import Optional, Set, Generator, List

# ------------------ 默认配置 ------------------
DEFAULT_EXCLUDE_DIRS: Set[str] = {
    "windows",
    "program files",
    "program files (x86)",
    "windows.old",
    "perflogs",
    "recovery",
    "boot",
    "efi",
    "$recycle.bin",
    "system volume information",
    "config.msi",
    "msocache",
    "appdata",
    "local settings",
    "application data",
    "cookies",
    "nethood",
    "printhood",
    "recent",
    "sendto",
    "start menu",
    "templates",
    "programdata",
    "intel",
    "amd",
    "nvidia",
    "windows update",
    "temp",
    "tmp",
}

DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    # 图片
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg', '.ico',
    # 文档
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv',
    '.rtf', '.odt', '.ods', '.odp', '.md', '.log',
    # 视频
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg',
    # 音频
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus',
    # 压缩包
    '.zip', '.rar', '.7z', '.tar', '.gz',
}

# ------------------ 基础工具 ------------------
def get_drives() -> List[str]:
    """返回系统中所有存在的盘符（仅 Windows）"""
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


# ------------------ 核心生成器 ------------------
def walk_filtered(
    root_path: str,
    exclude_dirs: Optional[Set[str]] = None,
    allowed_extensions: Optional[Set[str]] = None,
) -> Generator[str, None, None]:
    """
    遍历目录树，返回符合条件的文件路径（生成器）。
    
    参数:
        root_path:         起始扫描路径。
        exclude_dirs:      要跳过的文件夹名称集合（名称为小写），默认为 None（不跳过）。
        allowed_extensions:允许的文件扩展名集合（小写，含点），如 {'.txt','.jpg'}；
                           为 None 时不过滤。
    
    生成:
        文件完整路径字符串。
    """
    if exclude_dirs is None:
        exclude_dirs = set()
    # 将排除集合统一转为小写，确保不区分大小写
    exclude_dirs_lower = {d.lower() for d in exclude_dirs}

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
        # 过滤需要排除的目录（通过修改 dirnames 阻止遍历）
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in exclude_dirs_lower
        ]

        for filename in filenames:
            if allowed_extensions is None:
                yield os.path.join(dirpath, filename)
            else:
                ext = os.path.splitext(filename)[1].lower()
                if ext in allowed_extensions:
                    yield os.path.join(dirpath, filename)


def scan_all_drives(
    drives: Optional[List[str]] = None,
    exclude_dirs: Optional[Set[str]] = None,
    allowed_extensions: Optional[Set[str]] = None,
) -> Generator[str, None, None]:
    """
    扫描多个盘符，返回匹配文件的生成器。
    
    参数:
        drives:            要扫描的盘符列表，默认为 None（自动检测所有存在的盘符）。
        exclude_dirs:      同 walk_filtered。
        allowed_extensions:同 walk_filtered。
    
    生成:
        文件路径字符串。
    """
    if drives is None:
        drives = get_drives()
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    if allowed_extensions is None:
        allowed_extensions = DEFAULT_ALLOWED_EXTENSIONS

    for drive in drives:
        try:
            yield from walk_filtered(drive, exclude_dirs, allowed_extensions)
        except Exception as e:
            # 静默跳过无法访问的盘符
            pass


# ------------------ 便捷函数（返回列表）------------------
def list_files(
    drives: Optional[List[str]] = None,
    exclude_dirs: Optional[Set[str]] = None,
    allowed_extensions: Optional[Set[str]] = None,
) -> List[str]:
    """
    一次性获取所有符合条件的文件路径列表。
    参数同 scan_all_drives。
    """
    return list(scan_all_drives(drives, exclude_dirs, allowed_extensions))


# ------------------ 脚本主入口 ------------------
def main():
    print("扫描常见文件（图片、文档、视频、音频等），排除系统目录...\n")
    count = 0
    for file_path in scan_all_drives():
        print(file_path)
        count += 1
    print(f"\n扫描完成，共找到 {count} 个文件。")


if __name__ == "__main__":
    main()