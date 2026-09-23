/*!
 * web-driver-fix.js —— WOBKEY 网页驱动（wobwxe.com）浏览器端补丁
 *
 * 修的是官方前端自己的几个 bug，和操作系统、和键盘固件都无关。
 * 本文件不包含任何厂商代码，也不修改任何厂商文件；
 * 它只在你的浏览器里、对当前页面生效，随时可关。
 *
 * ⚠️ 必须在【页面脚本执行之前】注入才有效（注册表在 app 启动时就建好了）。
 *    在 Console 里粘贴来不及生效。用法见 README。
 *
 * MIT License
 */
(() => {
  'use strict';

  /* ══════════════════════════════════════════════════════════════════
   *  ①  配置区 —— 要适配新型号，改这里就够了
   * ══════════════════════════════════════════════════════════════════ */

  /* 控制接口规则：官网前端用 `collections[下标] === usagePage/usage` 来认设备。
   * 而 Chrome 在不同操作系统上暴露的 collection 顺序不一样（macOS 会把键盘
   * collection 单独拆走，导致控制接口的下标往前移），于是这个写死的下标就对不上了。
   *
   * 这里的做法：按 vendorId 找到对应规则，把控制接口挪到前端期望的下标上。
   *
   * 加新型号：先看官网 JS 里的白名单条件（搜 `collections[`），照着填一行。
   */
  const CONTROL_RULES = [
    // 0x320F 系设备（已验证）
    { vendorId: 0x320F, usagePage: 0xFF1C, usage: 0x92, index: 2 },
    // 0x36B0 系（官网白名单里的另一条产品线；未验证）
    { vendorId: 0x36B0, usagePage: 0xFF60, usage: 0x61, index: 0 },
  ];

  /* 是否自动纠正设备模块的方法签名问题（见 ③）。
   * 补丁是防御式的：只在检测到方法确实缺失 / 返回值形状不对时才动手，
   * 所以对没这个 bug 的型号完全无害。 */
  const FIX_DEVICE_METHODS = true;

  /* 是否在 Console 打印日志 */
  const VERBOSE = true;

  const log = (...a) => { if (VERBOSE) console.log('[wdf]', ...a); };

  /* ══════════════════════════════════════════════════════════════════
   *  ②  修 collections 下标错位
   * ══════════════════════════════════════════════════════════════════ */

  const fixCollections = (dev) => {
    try {
      const rule = CONTROL_RULES.find((r) => r.vendorId === dev.vendorId);
      const cs = dev.collections;
      if (!rule || !cs || !cs.length) return dev;

      const ctl = cs.find((c) => c.usagePage === rule.usagePage && c.usage === rule.usage);
      if (!ctl) return dev;                        // 不是这个控制接口，别碰
      if (cs[rule.index] === ctl) return dev;      // 位置本来就对

      const rest = cs.filter((c) => c !== ctl);
      const out = rest.slice();
      out.splice(rule.index, 0, ctl);              // 挪到期望下标
      Object.defineProperty(dev, 'collections', { get: () => out, configurable: true });
      log('collections 已重排 → 下标' + rule.index + ' =',
          ctl.usagePage.toString(16) + '/' + ctl.usage.toString(16));
    } catch (e) { /* 失败不影响原本行为 */ }
    return dev;
  };

  try {
    if (navigator.hid && !navigator.hid.__wdfFixed) {
      const hid = navigator.hid;
      const wrap = (fn) => async function (...a) {
        const r = await fn.apply(hid, a);
        return (r || []).map(fixCollections);
      };
      hid.getDevices = wrap(hid.getDevices.bind(hid));
      hid.requestDevice = wrap(hid.requestDevice.bind(hid));
      Object.defineProperty(hid, '__wdfFixed', { value: true });
      log('collections 补丁已安装');
    }
  } catch (e) {}

  /* ══════════════════════════════════════════════════════════════════
   *  ③  修设备模块的方法签名
   *
   *  背景：官方把「设备」写成一个模块
   *        { id: productId, config: {...}, methods: {...} }
   *  收进一张注册表，页面用 execute(productId, 方法名) 调用。
   *  注册表在 `Object.entries(module.methods)` 处构建 —— 就在这里下手。
   *
   *  已知两处问题（都只出现在 productId 20565 这个模块里）：
   *    [a] **官方有两个组件，对 getCharReplaceOpenList 的返回值期望不一致**：
   *           · 按键映射页（chunk 953）把 t.data 直接当数组用 → 要【裸数组】
   *           · 另一个组件（app~9f41190c）读 t.data.charReplaceOpenList → 要【包一层】
   *        20565 模块返回的是裸数组，于是前者正常、后者抛 undefined[3]。
   *        改成包一层会让按键映射页的侧栏类别全部消失，所以只能两头兼容地修。
   *        → 解法：仍然返回裸数组，但给它挂一个指向自己的 charReplaceOpenList 属性。
   *          数组下标访问和属性访问于是同时成立，两个调用方都满足。
   *    [b] 整个漏掉了 getKeyLightNavsOpenList
   *        → execute 抛「方法不存在」→ 页面挂载失败
   *
   *  两者都做成「只在确实坏掉时才修」，对别的型号无害。
   * ══════════════════════════════════════════════════════════════════ */

  if (!FIX_DEVICE_METHODS || Object.entries.__wdfFixed) return;
  const origEntries = Object.entries;

  const entries = function (o) {
    const out = origEntries.call(Object, o);
    try {
      if (!o || typeof o !== 'object' || Array.isArray(o)) return out;
      const keys = out.map((p) => p[0]);

      // 只认「设备模块的 methods 对象」——它一定同时有这两个方法
      if (!keys.includes('getDeviceStatus') || !keys.includes('getDeviceReportInfo')) return out;

      // [a] 两个调用方期望不一致 → 裸数组 + 自引用属性，两头兼容
      const i1 = keys.indexOf('getCharReplaceOpenList');
      if (i1 >= 0) {
        const orig = out[i1][1];
        out[i1][1] = function (...a) {
          const v = orig.apply(this, a);
          // 其它型号本来就返回 {charReplaceOpenList: ...}，原样放行
          if (v && typeof v === 'object' && 'charReplaceOpenList' in v) return v;
          // 裸数组：挂一个自引用属性，让「当数组用」和「取 .charReplaceOpenList」同时成立。
          // 注意不能改成包一层对象 —— 那会让按键映射页的侧栏类别全部消失。
          try {
            if (Array.isArray(v) && !v.charReplaceOpenList) v.charReplaceOpenList = v;
          } catch (e) {}
          return v;
        };
      }

      // [b] 方法整个缺失，补一个
      if (!keys.includes('getKeyLightNavsOpenList')) {
        out.push(['getKeyLightNavsOpenList', function () {
          let cfg = null;
          try { cfg = this.getConfig && this.getConfig(); } catch (e) {}
          for (const k of ['keyLightNavsOpenList', 'navsOpenList']) {
            if (cfg && Array.isArray(cfg[k])) return cfg[k];
          }
          return new Array(10).fill(true);   // 兜底：全开
        }]);
      }

      log('已修正设备模块:', keys.slice(0, 4).join(',') + ' …');
    } catch (e) {}
    return out;
  };
  entries.__wdfFixed = true;
  Object.entries = entries;
  log('补丁已安装');
})();
