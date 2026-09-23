# WOBKEY 网页驱动修复（macOS）

让 WOBKEY 键盘（已验证 **Rainy75**，同协议的 Rainy 98 / Zen 65 等可扩展）在 **macOS** 上正常使用官方网页驱动 <https://www.wobwxe.com/>。

官方网页驱动的前端有几个写死的 bug，只在 macOS 上暴露：连接后界面没反应、
首页设备卡片不出现、「灯光设置」「扩展字符」页面打不开。
本项目不改官方文件、不刷固件、不装扩展，只在你的浏览器里补上这几处 —— 随时可撤销。

---

## 使用流程

### 第 0 步：确认前提

| 项 | 要求 |
|---|---|
| 系统 | macOS |
| 浏览器 | 装了 Google Chrome（Chromium / Brave / Edge 也可以） |
| Python | 3.8 以上（终端运行 `python3 -V` 看版本） |
| 键盘连接 | **必须用 USB 线**（2.4G 接收器也可以）——**蓝牙不行**，见下方 FAQ |

### 第 1 步：拿到本项目

```bash
git clone https://github.com/HarryRen47/wobkey-rainy75-web-driver-fix.git
cd wobkey-rainy75-web-driver-fix
```

（也可以直接下载 ZIP 解压。）

### 第 2 步：装依赖（只需一次）

```bash
python3 -m pip install websockets
```

如果提示 `externally-managed-environment`，改用：

```bash
python3 -m pip install --user websockets
```

### 第 3 步：启动

```bash
python3 launch.py
```

终端会打印：

```
==============================================================
  WOBKEY 网页驱动 · 补丁版
  Chrome : /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  补丁   : .../patch/web-driver-fix.js
==============================================================
  1) 键盘用 USB 线连上电脑（蓝牙模式下厂商没暴露控制接口）
  2) 在弹出的窗口里点「授权并连接设备」，选中你的键盘
  3) 按 Ctrl+C 结束（会把那个专用 Chrome 一起关掉）
--------------------------------------------------------------
  [补丁] collections 补丁已安装
  [补丁] 补丁已安装
```

**同时会弹出一个独立的 Chrome 窗口**（用它自己的 profile 目录 `~/.wobkey-webdriver`，
和你日常用的 Chrome 完全隔离，不影响书签和登录状态）。

### 第 4 步：连接键盘

在**新弹出的那个 Chrome 窗口**里：

1. 点「**授权并连接设备**」
2. 在弹出的设备对话框里选中你的键盘
3. 连上后进入主界面，即可配置灯光 / 改键 / 宏

> 看不到设备对话框？确认键盘插在 USB 上，且没有被别的程序（比如旧的驱动窗口）占用。

### 第 5 步：确认生效

终端里应该有这几行：

```
  [补丁] collections 补丁已安装
  [补丁] 补丁已安装
  [补丁] 已修正设备模块: getDeviceStatus,getKeyMappingType,...
```

界面上应该能确认：

- 首页出现**设备卡片**（带 `Enter` 按钮）
- 「**灯光设置**」能打开
- 「**扩展字符**」能打开

**看不到 `[补丁]` 那几行** = 补丁没生效，请提 issue。

### 第 6 步：日常使用

**每次配置键盘都运行 `python3 launch.py`**，然后在弹出的窗口里连键盘。

补丁只在这个窗口里生效，不常驻、不改系统，这是设计如此。

### 结束 / 卸载

- **结束**：在终端按 `Ctrl+C`，专用 Chrome 会一起关掉。
- **卸载**：删掉本目录即可，再顺手删掉 profile：
  ```bash
  rm -rf ~/.wobkey-webdriver
  ```

---

## 它修什么

| 问题 | 现象 | 原因 |
|---|---|---|
| 首页设备卡片不显示 | 点「退出」后回不去，只能重新授权 | 官方写死了 HID `collections` 的下标，而 macOS 上 Chrome 的枚举顺序和 Windows 不同 |
| 「灯光设置」页打不开 | 控制台报 `方法不存在: getKeyLightNavsOpenList` | 官方设备模块缺了这个方法 |
| 「扩展字符」页打不开 | 控制台报 `Cannot read properties of undefined (reading '3')` | 官方两个组件对同一方法的返回值期望不一致（一个当数组、一个当对象） |

三个都是**官方前端自己的 bug**，和 macOS、和键盘固件都无关。补丁只改这三处，
其余保持官方原样。

---

## 兼容性

补丁按 `VID` + 控制接口的 `usagePage/usage` 匹配设备，规则表在
`patch/web-driver-fix.js` 顶部：

| VID / PID | 设备 | 状态 |
|---|---|---|
| `0x320F` / `0x5055` | **WOBKEY Rainy 75**（USB 有线） | ✅ 已验证 |
| `0x320F` / `0x5088` | WOBKEY 2.4G 接收器 | 同协议，未单独验证 |
| `0x36B0` / — | 官网白名单里的另一条产品线 | 规则已备好，未验证 |

**你的键盘不在表里也可以试** —— 很可能只是没人试过。先跑诊断：

```bash
python3 launch.py --diagnose
```

它会打印设备信息（VID / PID / 真实的 collections 顺序）。把输出贴到 issue 里，
或者在 `CONTROL_RULES` 里照着加一行。

---

## 常见问题

**为什么蓝牙不行？**
厂商固件没有在蓝牙通道上暴露配置接口，这是硬件限制，任何软件都做不到。请用 USB 线或 2.4G 接收器。

**会刷我的键盘固件吗？**
不会。只在浏览器里打补丁，不碰键盘、不写固件、不改任何官方文件。

**官网更新后还有效吗？**
有效，每次启动都重新注入。如果厂商改了前端结构导致失效，终端里就不会出现 `[补丁]` 那几行。

---

## 命令

```bash
python3 launch.py                 # 启动
python3 launch.py --diagnose      # 打印诊断信息（提 issue 时请附上）
python3 launch.py --port 9333     # 指定调试端口
python3 launch.py --quiet         # 不转发页面日志
python3 launch.py --profile DIR   # 指定 Chrome profile 目录
```

---

## 免责声明

- 本项目**非官方**，与 WOBKEY 无关联，未获其授权或支持。
- 本项目**不包含、也不分发任何厂商代码**；补丁在运行时作用于你本机浏览器中的页面。
- 仅供个人配置自己的键盘使用。MIT 许可，不提供任何担保。

## English

Unofficial browser-side patch that fixes hardcoded bugs in WOBKEY's web driver
(`wobwxe.com`) so their keyboards can be configured on macOS.

Three fixes: a hardcoded HID `collections` index that only holds on Windows, a
missing device-module method, and a return shape that two official components
disagree about.

`launch.py` opens a dedicated Chrome window and injects the patch before any page
script runs (required — the vendor bundles are Webpack and the device registry is
built at boot). No firmware flashing, no vendor files modified, fully reversible.

**Requirements:** macOS, Google Chrome, Python 3.8+, and a USB (or 2.4G) connection —
Bluetooth does not expose the configuration interface.

```bash
python3 -m pip install websockets
python3 launch.py
```

Verified on the WOBKEY Rainy 75 (USB). Other models can be added through the rule
table in `patch/web-driver-fix.js`. MIT licensed. Not affiliated with WOBKEY.
