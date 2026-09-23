#!/usr/bin/env python3
"""
launch.py —— 启动一个已注入补丁的 Chrome 窗口，用来配置 WOBKEY 键盘

用法:
    python3 launch.py                 # 启动
    python3 launch.py --diagnose      # 顺便打印诊断信息（提 issue 时用）
    python3 launch.py --port 9333     # 指定调试端口（默认自动挑一个空的）
    python3 launch.py --quiet         # 不转发页面日志

环境要求:
    macOS + Google Chrome + Python 3.8+
    pip install websockets

原理:
    官网是 Webpack 打包的单页应用，设备注册表在页面启动那一刻就建好了。
    所以补丁必须在【页面脚本之前】执行 —— 事后再注入（比如在 Console 里粘贴）来不及。
    这里用 Chrome DevTools Protocol 的 Page.addScriptToEvaluateOnNewDocument
    先登记补丁、再导航到官网，保证补丁早于一切页面脚本。

    注入发生在文档层、不经过文件替换，所以官网的 Service Worker 预缓存也绕不过它。

用的是一个独立 profile，不会影响你日常使用的 Chrome。

MIT License
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_FILE = os.path.join(HERE, "patch", "web-driver-fix.js")
SITE = "https://www.wobwxe.com/"
DEFAULT_PROFILE = os.path.expanduser("~/.wobkey-webdriver")

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


def free_port(start=9223):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("找不到可用端口")


class CDP:
    """极简 Chrome DevTools Protocol 客户端，只用到 Runtime / Page。"""

    def __init__(self, ws):
        self.ws = ws
        self._n = 0
        self.pending = []          # 等响应期间收到的事件先存着，别丢

    async def cmd(self, method, params=None, timeout=30):
        self._n += 1
        mid = self._n
        await self.ws.send(json.dumps({"id": mid, "method": method,
                                       "params": params or {}}))
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if msg.get("id") == mid:
                return msg
            self.pending.append(msg)

    async def js(self, expr, await_promise=False, timeout=30):
        r = await self.cmd("Runtime.evaluate", {
            "expression": expr, "awaitPromise": await_promise,
            "userGesture": True, "returnByValue": True}, timeout)
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return {"__error__": str(res["exceptionDetails"]
                                     .get("exception", {}).get("description"))[:300]}
        return res.get("result", {}).get("value")


DIAGNOSE_JS = r"""
(async () => {
  const out = { url: location.href, ua: navigator.userAgent };
  out.scripts = performance.getEntriesByType('resource')
    .map(e => e.name).filter(n => n.includes('/js/'))
    .map(n => n.split('/').pop());
  out.hidAvailable = ('hid' in navigator);
  try {
    const ds = await navigator.hid.getDevices();
    out.granted = ds.map(d => ({
      vendorId: '0x' + d.vendorId.toString(16),
      productId: '0x' + d.productId.toString(16),
      productName: d.productName,
      collections: (d.collections || []).map(c =>
        ['0x' + c.usagePage.toString(16), '0x' + c.usage.toString(16)]),
    }));
  } catch (e) { out.granted = 'ERR ' + e.message; }
  return out;
})()
"""


async def main():
    ap = argparse.ArgumentParser(description="启动补丁版 WOBKEY 网页驱动")
    ap.add_argument("--port", type=int, default=9223)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--diagnose", action="store_true",
                    help="打印诊断信息（提 issue 时请附上）")
    ap.add_argument("--quiet", action="store_true", help="不转发页面日志")
    args = ap.parse_args()

    if sys.platform != "darwin":
        print("本项目目前只支持 macOS。")
        sys.exit(1)

    try:
        import websockets
    except ImportError:
        print("缺少依赖。请先运行：\n\n    python3 -m pip install websockets\n")
        sys.exit(1)

    chrome = find_chrome()
    if not chrome:
        print("没找到 Chrome。请先安装 Google Chrome。")
        sys.exit(1)

    if not os.path.exists(PATCH_FILE):
        print("找不到补丁文件:", PATCH_FILE)
        sys.exit(1)
    patch_src = open(PATCH_FILE, encoding="utf-8").read()

    port = free_port(args.port)
    os.makedirs(args.profile, exist_ok=True)

    print("=" * 62)
    print("  WOBKEY 网页驱动 · 补丁版")
    print("  Chrome : " + chrome)
    print("  补丁   : " + PATCH_FILE)
    print("=" * 62)
    print("  1) 键盘用 USB 线连上电脑（蓝牙模式下厂商没暴露控制接口）")
    print("  2) 在弹出的窗口里点「授权并连接设备」，选中你的键盘")
    print("  3) 按 Ctrl+C 结束（会把那个专用 Chrome 一起关掉）")
    print("-" * 62)

    proc = subprocess.Popen(
        [chrome, "--remote-debugging-port=%d" % port,
         "--user-data-dir=" + args.profile,
         "--no-first-run", "--no-default-browser-check",
         "--restore-last-session=false",
         "--window-size=1280,900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws_url = None
    for _ in range(80):
        if proc.poll() is not None:
            print("Chrome 启动失败（该 profile 可能已被另一个窗口占用）")
            return
        try:
            lst = json.load(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % port, timeout=1))
            for t in lst:
                if t.get("type") == "page":
                    ws_url = t["webSocketDebuggerUrl"]
                    break
            if ws_url:
                break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    if not ws_url:
        print("连不上 Chrome 的调试端口")
        proc.terminate()
        return

    try:
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            cdp = CDP(ws)
            await cdp.cmd("Runtime.enable")
            await cdp.cmd("Page.enable")
            # ★ 顺序很重要：先登记注入，再导航
            await cdp.cmd("Page.addScriptToEvaluateOnNewDocument",
                          {"source": patch_src})
            await cdp.cmd("Page.navigate", {"url": SITE})

            if args.diagnose:
                await asyncio.sleep(6)
                info = await cdp.js(DIAGNOSE_JS, await_promise=True)
                print("\n--- 诊断信息（提 issue 时请附上）---")
                print(json.dumps(info, ensure_ascii=False, indent=2))
                print("--- 结束 ---\n")

            seen = set()
            while True:
                if cdp.pending:
                    msg = cdp.pending.pop(0)
                else:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), 3600))
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
                if args.quiet or msg.get("method") != "Runtime.consoleAPICalled":
                    continue
                text = " ".join(str(a.get("value") or a.get("description"))
                                for a in msg["params"].get("args", []))
                if "[wdf]" in text and text not in seen:
                    seen.add(text)
                    print("  [补丁] " + text.replace("[wdf]", "").strip())
    except KeyboardInterrupt:
        pass
    finally:
        print("\n正在关闭…")
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
