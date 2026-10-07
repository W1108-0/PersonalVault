# PersonalVault

一个基于 Python 的个人文件加密工具，支持 AES-256-GCM 加密、拖放操作、批量加密、健康检查、恢复密钥、双空间、隐写术等功能。

提供 **图形界面** 和 **命令行** 两种使用方式。

---

## 目录

- [功能特性](#功能特性)
- [依赖](#依赖)
- [文件结构](#文件结构)
- [快速开始](#快速开始)
- [使用说明](#使用说明)
- [打包为 exe](#打包为-exe)
- [安全说明](#安全说明)
- [常见问题](#常见问题)
- [许可](#许可)
- [免责声明](#免责声明)

---

## 功能特性

### 加密核心

- **AES-256-GCM** 分块加密（每块 8 MB）
- **PBKDF2-HMAC-SHA256** 密钥派生（20 万次迭代，自动加盐）
- **主密钥 + 文件密钥** 两层结构，批量加密只算一次 PBKDF2，速度快
- **文件头 HMAC-SHA256 认证**，防篡改，兼作密码快速校验器
- **原子写入**（tmp + `os.replace`），避免崩溃时产生半成品 `.enc` 文件
- **SHA-256 完整性校验**，解密后自动比对

### 数据保护

- **恢复密钥**：忘记密码时的救命稻草（64 位十六进制）
- **双空间**：真实密码解真数据，假密码解诱饵数据，防胁迫
- **隐写术**：把 `.enc` 文件藏进 PNG 图片，外表看不出来
- **过期时间锁**：设定天数或日期，过期后无法解密
- **阅后自毁**：解密到临时目录，打开后安全删除
- **安全删除原文件**：随机数据覆写 3 次后删除，防恢复
- **坏块跳过**：文件部分损坏时尽力抢救剩余数据

### 使用体验

- **图形界面**（tkinter）：加密 / 解密 / 健康检查 / 工具，四个独立标签页
- **命令行**：`PersonalVaultCLI.exe`，支持所有功能
- **拖放**：拖文件或文件夹到窗口，自动路由到正确的标签页
- **深色主题**：跟随系统或手动切换
- **密码强度条**：实时反馈
- **强密码生成器**：一键生成 16 位含符号随机密码
- **批量加密**：进度条 + 彩色日志（时间戳 + 分级）
- **中断恢复**：意外关闭后再次打开可继续未完成任务
- **Windows 右键菜单**：右键文件/文件夹直接加密解密
- **文件头预览**：不解密即可查看原文件名、大小、过期时间

---

## 依赖

```bash
pip install cryptography tkinterdnd2 stegano
```

| 库 | 用途 | 是否必需 |
|---|---|---|
| `cryptography` | AES-256-GCM、PBKDF2 | **必需** |
| `tkinterdnd2` | 拖放功能 | 可选（缺失则无法拖放） |
| `stegano` | 隐写术 | 可选（使用时才需要） |

Python 版本要求：**3.8 或更高**（推荐 3.10+）。

---

## 文件结构

```
.
├── file_scanner.py            # 文件扫描模块（遍历磁盘按扩展名过滤）
├── personal_vault.py          # 核心加密模块
├── integrated_vault_gui.py    # 图形界面主程序
├── vault_cli.py               # 命令行入口
├── vault_menu_setup.py        # Windows 右键菜单注册
├── build_exe.py               # 一键打包脚本
├── PersonalVault.spec         # PyInstaller spec（GUI 版）
├── PersonalVaultCLI.spec      # PyInstaller spec（CLI 版）
├── README.md
└── LICENSE
```

---

## 快速开始

### 图形界面

```bash
python integrated_vault_gui.py
```

打开后会看到 4 个标签页：

| 标签页 | 用途 |
|---|---|
| **加密** | 添加文件/文件夹、扫描磁盘、设置密码、过期时间、生成恢复密钥 |
| **解密** | 选择 `.enc` / `.vault` 文件、恢复密钥解密、坏块跳过、阅后自毁 |
| **健康检查** | 检查加密文件完整性，逐块验证 |
| **工具** | 恢复密钥生成器、隐写术、双空间、右键菜单注册 |

### 命令行

```bash
# 查看所有子命令
python vault_cli.py --help

# 加密文件（交互输入密码）
python vault_cli.py encrypt path/to/file

# 加密时带密码和恢复密钥
python vault_cli.py encrypt path/to/file -p "MyPwd123!" --recovery auto

# 加密时设置 30 天过期
python vault_cli.py encrypt path/to/file -p "MyPwd123!" -e 30

# 加密并安全删除原文件
python vault_cli.py encrypt path/to/file -p "MyPwd123!" -r

# 解密
python vault_cli.py decrypt path/to/file.enc -p "MyPwd123!" -o output_dir

# 用恢复密钥解密
python vault_cli.py decrypt path/to/file.enc --recovery-key "xxxx-xxxx-..."

# 查看文件头（不需要密码）
python vault_cli.py info path/to/file.enc

# 健康检查（完整校验每个分块）
python vault_cli.py check path/to/file.enc -p "MyPwd123!" --full

# 隐写：把 .enc 藏进 PNG
python vault_cli.py hide path/to/file.enc cover.png secret.png

# 从 PNG 提取
python vault_cli.py reveal secret.png extracted.enc

# 创建双空间
python vault_cli.py dual real.txt fake.txt -o secret.ds

# 用真密码或假密码解密双空间
python vault_cli.py dual-decrypt secret.ds -p "RealPwd!" -o out

# 生成恢复密钥 / 强密码
python vault_cli.py genkey
python vault_cli.py genpwd -l 20

# 启动 GUI
python vault_cli.py gui

# 注册 / 卸载右键菜单
python vault_cli.py menu register
python vault_cli.py menu unregister
```

---

## 使用说明

### 加密模式

- **逐个加密（.enc）**：每个文件生成独立的 `xxx.jpg.enc`，可单独解密
- **打包成 .vault**：所有文件打包成一个加密容器，适合云盘备份

### 加密流程（GUI）

1. 切到 **加密** 标签页
2. 拖入文件/文件夹，或用「添加文件 / 添加文件夹 / 扫描磁盘」
3. 输入密码（建议 ≥ 12 位，含大小写+数字+符号）
4. 选择模式：
   - 逐个加密：原文件旁生成 `.enc`
   - 打包成 .vault：弹窗选择保存位置
5. （可选）勾选「加密后安全删除原文件」
6. （可选）勾选「生成恢复密钥」并抄写弹窗中的密钥
7. （可选）填写过期时间：`30` 表示 30 天，或 `2026-12-31` 指定日期
8. 点击 **▶ 开始加密**

### 解密流程（GUI）

1. 切到 **解密** 标签页
2. 拖入 `.enc` / `.vault` 文件（拖文件夹会递归查找）
3. 选择输出目录
4. 输入密码
   - 若忘记密码，填写恢复密钥
5. 点击 **▶ 开始解密**

### 快捷键

| 快捷键 | 功能 |
|---|---|
| `Ctrl+O` | 添加文件到加密列表 |
| `Ctrl+D` | 添加文件夹到加密列表 |
| `Ctrl+E` | 开始加密 |
| `Ctrl+R` | 开始解密 |
| `F5` | 刷新当前标签页 |
| `Esc` | 停止当前任务 |
| `F1` | 显示快捷键帮助 |
| `Ctrl+Q` | 退出 |
| `Delete` | 移除列表中选中的项 |

### 右键菜单（Windows）

注册后：

- **Win10**：右键任意文件/文件夹即可看到「PersonalVault 加密 / 解密」
- **Win11**：需要点击右键菜单底部的 **「显示更多选项」**

卸载：`python vault_cli.py menu unregister`

---

## 打包为 exe

安装 PyInstaller：

```bash
pip install pyinstaller
```

一键打包：

```bash
python build_exe.py
```

输出到 `dist/`：

| 文件 | 说明 |
|---|---|
| `PersonalVault.exe` | 图形界面（无控制台） |
| `PersonalVaultCLI.exe` | 命令行（带控制台，右键菜单调用） |

### 部署

把两个 exe 放到同一目录，双击 `PersonalVault.exe` 即可运行，目标电脑无需安装 Python。

**首次使用**可注册右键菜单：

```powershell
PersonalVaultCLI.exe menu register
```

### 单文件大小

- `PersonalVault.exe`：约 20 MB
- `PersonalVaultCLI.exe`：约 18 MB

（关闭 UPX 压缩后的大小；启用 UPX 会更小，但容易被杀毒软件误报）

---

## 安全说明

### 加密算法

| 项目 | 参数 |
|---|---|
| 对称加密 | AES-256-GCM |
| 密钥派生 | PBKDF2-HMAC-SHA256，200,000 次迭代 |
| 盐长度 | 32 字节（每文件随机） |
| IV 长度 | 12 字节（每分块随机） |
| 分块大小 | 8 MB |
| 完整性 | GCM 认证标签 + SHA-256 文件哈希 |
| 文件头认证 | HMAC-SHA256（用主密钥） |

### 注意事项

- **忘记密码无法恢复**（除非事先设置了恢复密钥并妥善保管）
- 密码在 Python 内存中以 `str` 形式存在，理论上存在内存取证风险
- 请**自行审计源码**后再用于敏感数据
- 建议搭配 **BitLocker / FileVault / VeraCrypt** 做磁盘级加密
- 本工具**不能**防御键盘记录器、屏幕截图、有 root 权限的恶意软件

---

## 常见问题

### Q1: 提示「未找到 personal_vault.py」

**原因**：文件不在程序目录，或依赖 `cryptography` 未安装。

**排查**：

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

若报错，执行 `pip install cryptography`。

### Q2: 拖放功能不生效

安装 `tkinterdnd2`：

```bash
pip install tkinterdnd2
```

重启程序，状态栏应显示「拖放：已启用」。

### Q3: 隐写术报错

安装 `stegano`：

```bash
pip install stegano
```

载体图片请使用 **PNG**（JPG 有损压缩会破坏 LSB 数据）。

### Q4: Win11 右键菜单看不到

Win11 默认折叠经典菜单，需点击右键菜单底部的 **「显示更多选项」**。如需一级菜单，需 MSIX 稀疏包 + COM 组件（纯 Python 无法实现）。

### Q5: 加密大文件很慢

PBKDF2 20 万次迭代已优化为**每批次只算一次**（主密钥 + 文件密钥两层结构），小文件批量的速度很快。单个 GB 级文件的耗时主要在磁盘 IO 和 AES 计算，属正常范围。

### Q6: 打包后 exe 被杀毒软件误报

PyInstaller 打包的 exe 常被误报。解决方案：

- 添加信任/白名单
- 使用代码签名证书签名
- 关闭 UPX 压缩（spec 里 `upx=False`）

### Q7: 想清空配置

删除：

```
%USERPROFILE%\.personal_vault_gui.json
%USERPROFILE%\.personal_vault_journal.json
```

### Q8: 加密后文件变大了

正常。每个文件约有 100 字节的头部开销（JSON 头部 + HMAC + Salt），每个 8 MB 分块有 32 字节开销（IV + GCM Tag）。对大文件来说开销可忽略。

---

## 许可

[GNU General Public License v3.0](LICENSE)

Copyright (C) 2026 <W1108-0>

本程序是自由软件：你可以根据自由软件基金会发布的 GNU 通用公共许可证
（版本 3 或更高版本）条款重新发布和/或修改它。

本程序的发布是希望它有用，但不提供任何担保，甚至没有适销性或特定用途
适用性的默示担保。详见 GNU 通用公共许可证。

你应该已经随本程序收到一份 GNU 通用公共许可证的副本。如果没有，
请访问 <https://www.gnu.org/licenses/>。
---

## 免责声明

本工具仅供**个人学习与合法用途**。使用者需自行承担因使用本软件造成的任何数据丢失或其他损失。

请遵守当地法律法规，不得用于非法加密或隐藏违法内容。
```
