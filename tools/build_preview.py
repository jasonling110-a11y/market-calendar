# -*- coding: utf-8 -*-
"""生成可在浏览器直接打开的 H5 预览版（数据内嵌，无需服务器）"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "miniprogram", "data")
OUT = os.path.join(ROOT, "preview", "index.html")

# ---- 云版（部署在 WorkBuddy 域名，笔记跨设备同步）----
CLOUD_OUT = os.path.join(ROOT, "webapp", "index.html")
CCFG = os.path.join(HERE, "cloud_config.json")      # 开通云服务后写入
# 数据仍在 GitHub Pages，云版页面运行时从这里加载
DATA_BASE = "https://jasonling110-a11y.github.io/market-calendar/data"
# SDK 官方 CDN（jsdelivr 在国内时通时断，故改为随应用一起自托管）。
# 文件是官方发布的 IIFE 构建，直接下载到 webapp/sdk/，未做任何改写。
# 需要升级时重新下载同名文件即可（不要手写 fetch 封装替代它）。
SDK_CDN = ("https://cdn.jsdelivr.net/npm/"
           "@tencent-ai/workbuddy-cloud-sdk@dev/lib/index.global.js")
SDK_URL = "./sdk/workbuddy-cloud.js"


def load_js_module(name):
    """读取 module.exports = {...}; 形式的 JS 数据模块"""
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        s = f.read()
    s = s[s.index("module.exports = ") + len("module.exports = "):].strip()
    if s.endswith(";"):
        s = s[:-1]
    return json.loads(s)


TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>市场日历 · 预览</title>
<style>
:root{
  --bg:#000; --surface:#1c1c1e; --surface2:#2c2c2e; --sep:#38383a;
  --text:#fff; --text2:#98989f; --text3:#636366;
  --up:#ff453a; --down:#30d158; --accent:#ff3b30; --warn:#ffd60a; --info:#0a84ff;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0;background:#0a0a0b;height:100%;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",sans-serif;color:var(--text)}
body{overflow:hidden}
.app{height:100vh;display:flex;flex-direction:column;position:relative;overflow:hidden}

/* ===== 顶栏 ===== */
.topbar{height:52px;flex-shrink:0;display:flex;align-items:center;gap:18px;padding:0 22px;border-bottom:1px solid var(--sep);background:#101012}
.brand{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:500;letter-spacing:.4px;flex-shrink:0}
.brand-dot{width:7px;height:7px;border-radius:50%;background:var(--accent)}

/* ===== 左右分栏 ===== */
.layout{flex:1;display:flex;min-height:0}
.cal-col{width:396px;flex-shrink:0;border-right:1px solid var(--sep);display:flex;flex-direction:column;padding:14px 18px 0;overflow-y:auto;background:#0d0d0f}
.cal-col::-webkit-scrollbar{width:0}
.content-col{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--bg)}

/* ===== 日历头部 ===== */
.hdr{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:12px}
.m-title{font-size:27px;font-weight:500;color:var(--accent);letter-spacing:.3px}
.m-sub{display:block;font-size:11px;color:var(--text3);margin-top:3px}
.hdr-r{display:flex;align-items:center}
.nav{width:30px;height:30px;line-height:28px;text-align:center;font-size:18px;color:var(--text2);background:var(--surface2);border-radius:50%;margin-left:7px;cursor:pointer;user-select:none;transition:background .16s,color .16s}
.nav:hover{background:#3a3a3c;color:var(--text)}
.today{padding:0 13px;height:30px;line-height:30px;font-size:12.5px;color:var(--text);background:var(--surface2);border-radius:15px;margin-left:7px;cursor:pointer;transition:background .16s}
.today:hover{background:#3a3a3c}

/* ===== 工作台状态（在顶栏内）===== */
.wb{display:flex;align-items:center;gap:9px;font-size:11.5px;color:var(--text3);flex:1;min-width:0}
.wb-dot{width:6px;height:6px;border-radius:50%;background:#30d158;flex-shrink:0;transition:background .3s}
.wb-dot.busy{background:var(--warn);animation:wbPulse 1.3s ease-in-out infinite}
.wb-dot.err{background:var(--up)}
.wb-dot.warn{background:var(--warn)}
@keyframes wbPulse{0%,100%{opacity:1}50%{opacity:.25}}
.wb-t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wb-btn{padding:3px 11px;border-radius:9px;background:var(--surface2);color:var(--text2);cursor:pointer;flex-shrink:0;font-size:11.5px;transition:background .2s,color .2s}
.wb-btn:hover{background:#3a3a3c;color:var(--text)}

/* ===== 分段控件 ===== */
.seg{display:flex;background:var(--surface2);border-radius:10px;padding:3px;margin-bottom:10px}
.seg-i{flex:1;text-align:center;height:32px;line-height:32px;font-size:13px;color:var(--text2);border-radius:8px;cursor:pointer;transition:.18s}
.seg-i:hover{color:var(--text)}
.seg-i.on{background:#3a3a3c;color:var(--text);font-weight:500}

/* ===== 日期网格 ===== */
.wk{display:flex;margin-bottom:2px}
.wk-i{flex:1;text-align:center;font-size:11px;color:var(--text3);padding-bottom:6px}
/* 用 grid 而不是 flex+百分比宽度：14.2857%×7=99.9999%，亚像素舍入会让第 7 格换行（实测导致日历错行） */
.grid{display:grid;grid-template-columns:repeat(7,1fr)}
.cell{height:50px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;position:relative;border-radius:10px;transition:background .15s}
.cell:hover{background:rgba(255,255,255,.055)}
.num{width:34px;height:34px;line-height:34px;text-align:center;font-size:14.5px;border-radius:50%;transition:.15s}
.cell.dim .num{color:#4a4a4c}
.cell.today .num{background:var(--accent);color:#fff;font-weight:500}
.cell.sel{background:rgba(255,255,255,.09)}
.cell.sel .num{color:var(--text);font-weight:500}
/* 今天被选中时用外圈光晕表示，而不是再叠一层背景色 —— 叠背景会让它看起来像块方形色块 */
.cell.today.sel{background:transparent}
.cell.today.sel .num{box-shadow:0 0 0 3px rgba(255,59,48,.3)}
.dots{height:6px;display:flex;align-items:center;justify-content:center;margin-top:2px}
.dot{width:5px;height:5px;border-radius:50%;margin:0 2px}
.dot-h{background:#8e8e93}.dot-u{background:var(--warn)}.dot-n{background:var(--info)}

/* ===== 图例 ===== */
.legend{display:flex;gap:16px;padding:12px 2px 16px;margin-top:auto;font-size:11px;color:var(--text3);flex-shrink:0}
.legend span{display:flex;align-items:center;gap:6px}
.legend i{width:5px;height:5px;border-radius:50%;display:inline-block}
.legend i.h{background:#8e8e93}.legend i.u{background:var(--warn)}.legend i.n{background:var(--info)}

/* ===== 右侧内容区 ===== */
.panel{flex:1;overflow-y:auto;padding:16px 26px 50px}
.panel::-webkit-scrollbar{width:8px}
.panel::-webkit-scrollbar-thumb{background:#2c2c2e;border-radius:4px}
.panel::-webkit-scrollbar-track{background:transparent}
.ph{padding:2px 4px 12px;display:flex;align-items:baseline;max-width:900px;margin:0 auto}
.ph-d{font-size:19px;font-weight:500}
.ph-w{font-size:12px;color:var(--text2);margin-left:9px}
.card{background:var(--surface);border-radius:14px;padding:16px 18px;margin:0 auto 14px;max-width:900px;border:1px solid rgba(255,255,255,.055)}

/* ===== 窄屏回退为上下排布 ===== */
@media (max-width:900px){
  .layout{flex-direction:column}
  .cal-col{width:100%;border-right:none;border-bottom:1px solid var(--sep);max-height:48vh;flex-shrink:0}
  .panel{padding:14px 14px 40px}
  .topbar{padding:0 14px}
}

.card-title{display:flex;align-items:center;justify-content:space-between;font-size:12.5px;color:var(--text2);margin-bottom:12px;letter-spacing:.2px}
.card-title>span:first-child::before{content:'';display:inline-block;width:3px;height:11px;background:var(--text3);border-radius:2px;margin-right:8px;vertical-align:-1px}
.src{font-size:11px;color:var(--text3)}
.two{display:flex}.col{flex:1}.col+.col{margin-left:12px}
.col-t{font-size:11px;color:var(--text2);padding-bottom:5px;border-bottom:1px solid var(--sep);margin-bottom:5px}
.col-t.up{color:var(--up)}.col-t.down{color:var(--down)}
.bk{display:flex;align-items:center;justify-content:space-between;padding:5px 0}
.bk-n{font-size:12.5px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-right:6px}
.bk-p{font-size:12.5px;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}
.breadth{margin-top:10px;padding-top:8px;border-top:1px solid var(--sep);font-size:11.5px;color:var(--text2);text-align:center}
.row{padding:10px 0;border-bottom:1px solid var(--sep)}
.row:last-child{border-bottom:none}
.ev-h{display:flex;align-items:center;flex-wrap:wrap;margin-bottom:4px;gap:6px}
.ev-y{font-size:11px;color:var(--text3);font-variant-numeric:tabular-nums}
.ev-t{font-size:14px;font-weight:500;flex:1}
.ev-d{font-size:12px;color:var(--text2);line-height:18px}
.ev-m{margin-top:5px;font-size:11px;color:var(--text3)}
.tm{color:var(--text2);font-variant-numeric:tabular-nums}
.cd{color:var(--warn)}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;line-height:17px}
.tag-us{background:rgba(10,132,255,.18);color:#6cb6ff}
.tag-cn{background:rgba(255,59,48,.16);color:#ff7b72}
.tag-tech{background:rgba(175,82,222,.18);color:#d0a1ff}
.tag-shock{background:rgba(255,149,0,.18);color:#ffb340}
.tag-policy{background:rgba(48,209,88,.16);color:#5fd980}
.tag-market{background:rgba(255,214,10,.16);color:#ffd60a}
.tag-eu{background:rgba(175,82,222,.18);color:#d0a1ff}
.tag-jp{background:rgba(48,209,88,.16);color:#5fd980}
.tag-kr{background:rgba(255,149,0,.18);color:#ffb340}
/* 地区角标：与分类标签同形但更小、更淡，避免抢视觉 */
.g-us,.g-cn,.g-eu,.g-jp,.g-kr,.g-global{background:rgba(255,255,255,.07);color:var(--text3);font-size:9.5px;padding:1px 6px}
.g-us{background:rgba(10,132,255,.14);color:#6cb6ff}
.g-cn{background:rgba(255,59,48,.13);color:#ff7b72}
.g-eu{background:rgba(175,82,222,.14);color:#d0a1ff}
.g-jp{background:rgba(48,209,88,.13);color:#5fd980}
.g-kr{background:rgba(255,149,0,.14);color:#ffb340}
.g-global{background:rgba(255,255,255,.09);color:#8e8e93}
.conf{font-size:10px;padding:1px 6px;border-radius:4px}
.conf-confirmed{color:#6cb6ff;border:1px solid rgba(10,132,255,.5)}
.conf-estimated{color:#98989f;border:1px solid var(--sep)}
.conf-rumored{color:#ffb340;border:1px solid rgba(255,149,0,.5)}
.dsep{display:flex;align-items:baseline;padding:12px 0 5px;border-top:1px solid var(--sep)}
.dsep-d{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
.dsep-w{font-size:11px;color:var(--text2);margin-left:6px}
.dsep-c{font-size:11px;color:var(--warn);margin-left:auto}
.calf{display:flex;background:var(--surface2);border-radius:6px;padding:2px;margin-bottom:8px}
.calf-i{flex:1;text-align:center;height:28px;line-height:28px;font-size:11.5px;color:var(--text2);border-radius:5px;cursor:pointer;transition:background .22s,color .22s}
.calf-i.on{background:#3a3a3c;color:var(--text);font-weight:500}
.ci{display:flex;align-items:stretch;padding:7px 0}
.ci+.ci{border-top:1px solid rgba(56,56,58,.5)}
.ci-t{width:42px;flex-shrink:0;font-size:10.5px;color:var(--text3);font-variant-numeric:tabular-nums;letter-spacing:-.3px;padding-top:2px}
.ci-bar{width:3px;border-radius:2px;margin:4px 8px 4px 0;flex-shrink:0;background:#48484a;transition:background .2s}
.ci.c3 .ci-bar{background:#ff9f0a}
.ci.c2 .ci-bar{background:#0a84ff}
.ci-b{flex:1;min-width:0}
.ci-h{display:flex;align-items:baseline}
.ci-n{font-size:12.5px;color:var(--text);line-height:18px;flex:1;word-break:break-all}
.ci.c1 .ci-n{color:var(--text2)}
.ci-pd{font-size:9.5px;color:var(--text3);margin-left:5px;flex-shrink:0}
.ci-m{display:flex;align-items:center;margin-top:2px;flex-wrap:wrap}
.ci-co{font-size:9.5px;color:var(--text3);background:rgba(255,255,255,.07);padding:1px 5px;border-radius:3px;margin-right:4px}
.ci-v{display:flex;align-items:baseline;margin-top:4px;flex-wrap:wrap}
.civ{font-size:11.5px;color:var(--text2);margin-right:9px;font-variant-numeric:tabular-nums}
.civ-a{color:var(--warn);font-weight:600;font-size:12.5px}
@keyframes ciIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.ci.anr{animation:ciIn .34s cubic-bezier(.22,.68,.36,1) both}
/* B 站要点是这块页面的正主，字号要比其余卡片明显大一档，读起来才不吃力 */
.up-t{font-size:14px;font-weight:500;color:var(--text);padding-bottom:8px;margin-bottom:7px;border-bottom:1px solid var(--sep);line-height:20px}
.up-pt{display:flex;padding:5px 0}
.up-dot{font-size:15px;color:var(--text3);margin-right:7px;flex-shrink:0;line-height:23px}
.up-tx{font-size:14.5px;line-height:23px;flex:1}
.up-link{margin-top:7px;padding-top:6px;border-top:1px solid var(--sep);font-size:11px;color:#3b9cff;text-align:right;cursor:pointer}
.empty{padding:46px 30px;text-align:center;font-size:13px;color:var(--text3)}
.empty-sub{margin-top:7px;font-size:11px;color:#4a4a4c}
.nodata{padding:3px 20px 8px;font-size:10.5px;color:var(--text3);text-align:center}
.vrow{padding:10px 0;border-bottom:1px solid var(--sep)}
.vrow:last-child{border-bottom:none}
.vhead{display:flex;align-items:center;margin-bottom:7px}
.vdate{font-size:11px;color:var(--text3);font-variant-numeric:tabular-nums;margin-right:8px}
.vname{font-size:14px;font-weight:500;flex:1}
.stars{font-size:10px;color:#4a4a4c;margin-right:5px;letter-spacing:-1px;flex-shrink:0}
.stars.hot{color:var(--warn)}
.bias{font-size:10px;padding:1px 7px;border-radius:4px}
.bias-up{color:#ff9f0a;background:rgba(255,159,10,.14)}
.bias-down{color:#64d2ff;background:rgba(100,210,255,.14)}
.bias-flat{color:var(--text2);background:rgba(142,142,147,.16)}
.vgrid{display:flex}
.vcell{flex:1;display:flex;flex-direction:column}
.vlab{font-size:10px;color:var(--text3);margin-bottom:2px}
.vval{font-size:15px;color:var(--text2);font-variant-numeric:tabular-nums}
.vval.vreal{color:var(--text);font-weight:600;font-size:17px}
.vval.vsub{font-size:14px}
.vsmall{font-size:11px;color:var(--text3);font-weight:400}
.vextra{display:flex;margin-top:6px;font-size:10.5px;color:var(--text3)}
.vextra span{margin-right:10px}
.vanchor{margin-top:6px;padding:8px 9px;background:var(--surface2);border-radius:7px;display:flex;align-items:center;flex-wrap:wrap;gap:6px}
.va-lab{font-size:10px;color:var(--text3)}
.va-val{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.va-src{font-size:10px;color:var(--text3)}
.va-prev,.va-exp{font-size:10px;color:var(--text2)}
.va-wait{font-size:9.5px;color:var(--warn);margin-left:auto}
.foot{padding:18px 0 6px;text-align:center}
.foot-t{font-size:12px;color:var(--info);cursor:pointer}
.sheet{position:absolute;left:0;right:0;top:0;bottom:0;background:var(--bg);z-index:20;display:none;flex-direction:column}
.sheet.on{display:flex}
.sh-hd{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--sep)}
.sh-t{font-size:16px;font-weight:600}
.sh-x{font-size:20px;color:var(--text2);cursor:pointer}
.sh-c,.sh-s{font-size:14px;color:var(--info);cursor:pointer}
.sh-bd{flex:1;overflow-y:auto;padding:14px 18px}
.sh-bd::-webkit-scrollbar{width:0}
.ta{width:100%;height:190px;background:var(--surface);border-radius:10px;padding:12px;font-size:14px;line-height:22px;color:var(--text);border:none;outline:none;resize:none;font-family:inherit}
.nvtools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-bottom:9px;margin-bottom:10px;border-bottom:1px solid var(--sep)}
.nvt{font-size:12px;color:var(--info);padding:5px 11px;border:1px solid var(--sep);border-radius:7px;cursor:pointer;white-space:nowrap}
.nvt:active{opacity:.55}
.nvt-tip{font-size:10.5px;color:var(--text3);margin-left:auto}
.chips{display:flex;flex-wrap:wrap;margin-top:12px}
.chip{padding:5px 14px;font-size:13px;color:var(--text2);background:var(--surface);border:1px solid var(--sep);border-radius:999px;margin:0 8px 8px 0;cursor:pointer}
.chip.on{color:#fff;background:var(--info);border-color:var(--info)}
.sh-ft{display:flex;padding:12px 18px 22px;border-top:1px solid var(--sep)}
.bt{flex:1;height:40px;line-height:40px;text-align:center;border-radius:10px;font-size:15px;cursor:pointer}
.bt.s{background:var(--info);color:#fff;font-weight:600}
.bt.d{flex:0 0 100px;margin-right:12px;background:var(--surface);color:var(--up);font-size:14px}
.sbar{display:flex;align-items:center;background:var(--surface2);border-radius:10px;padding:0 12px;height:34px;margin-bottom:10px}
.sbar input{flex:1;background:transparent;border:none;outline:none;color:var(--text);font-size:13px;font-family:inherit}
.nit{background:var(--surface);border-radius:11px;padding:11px 13px;margin-bottom:10px;cursor:pointer}
.nit-h{display:flex;align-items:center;margin-bottom:5px}
.nit-d{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
.nit-w{font-size:10px;color:var(--text3);margin-left:5px}
.nit-t{font-size:10px;color:#6cb6ff;background:rgba(10,132,255,.14);padding:1px 6px;border-radius:4px;margin-left:8px}
.nit-tm{font-size:10px;color:var(--text3);margin-left:auto}
.nit-x{font-size:13px;color:var(--text2);line-height:20px}
.note-card{margin:12px 14px}
.nrow{padding:9px 0;border-bottom:1px solid var(--sep)}
.nrow:last-child{border-bottom:none}
.nh{display:flex;align-items:center;margin-bottom:3px}
.ntm{font-size:10px;color:var(--text3);font-variant-numeric:tabular-nums}
.ntag{font-size:9px;color:#6cb6ff;background:rgba(10,132,255,.14);padding:1px 6px;border-radius:4px;margin-left:6px}
.ntx{font-size:13px;color:var(--text);line-height:20px;word-break:break-all}
.nem{padding:12px 0 4px;font-size:11.5px;color:var(--text3);text-align:center}
.nbtn{font-size:12px;color:var(--info);cursor:pointer}
.fab{position:absolute;right:18px;bottom:22px;width:46px;height:46px;border-radius:50%;background:var(--info);color:#fff;font-size:26px;line-height:44px;text-align:center;box-shadow:0 4px 12px rgba(10,132,255,.4);cursor:pointer;z-index:5}
.hint{position:absolute;left:0;right:0;bottom:0;background:rgba(28,28,30,.96);border-top:1px solid var(--sep);padding:14px 18px 22px;font-size:12px;color:var(--text2);line-height:19px;display:none;z-index:9}
.hint.on{display:block}
.hint b{color:var(--text)}

/* ===== 云笔记：登录 ===== */
.lg{display:flex;flex-direction:column;gap:11px;padding-bottom:8px}
.lg-tabs{display:flex;gap:8px}
.lg-tab{flex:1;text-align:center;font-size:12.5px;padding:8px 0;border-radius:9px;background:var(--surface2);color:var(--text2);cursor:pointer}
.lg-tab.on{background:var(--info);color:#fff}
.lg-f{display:flex;flex-direction:column;gap:6px}
.lg-f label{font-size:11.5px;color:var(--text3)}
.lg-f input{height:40px;width:100%;border-radius:10px;border:1px solid var(--sep);background:var(--surface2);color:var(--text);padding:0 12px;font-size:14px;outline:none;font-family:inherit}
.lg-f input:focus{border-color:var(--info)}
.lg-row{display:flex;gap:8px;align-items:flex-end}
.lg-row .lg-f{flex:1;min-width:0}
.lg-code{height:40px;padding:0 13px;border-radius:10px;border:1px solid var(--sep);background:var(--surface2);color:var(--info);font-size:12.5px;white-space:nowrap;cursor:pointer;display:flex;align-items:center}
.lg-code.dis{opacity:.45;pointer-events:none}
.lg-btn{height:42px;border-radius:11px;background:var(--info);color:#fff;font-size:14.5px;font-weight:500;display:flex;align-items:center;justify-content:center;cursor:pointer}
.lg-btn.ghost{background:var(--surface2);color:var(--text);font-weight:400;font-size:13.5px}
.lg-btn.dis{opacity:.45;pointer-events:none}
.lg-msg{font-size:12px;color:var(--warn);min-height:17px;line-height:1.45}
.lg-msg.ok{color:var(--down)}
.lg-note{font-size:11px;color:var(--text3);line-height:1.6}
.lg-note b{color:var(--text2)}
.lg-sep{height:1px;background:var(--sep);margin:2px 0}
</style>
__HEAD_SCRIPTS__
</head>
<body>
<div class="app">
  <div class="topbar">
    <div class="brand"><span class="brand-dot"></span>市场日历</div>
    <div class="wb" id="wb" style="display:none">
      <span class="wb-dot" id="wbDot"></span>
      <span class="wb-t" id="wbText">正在连接本地服务…</span>
      <span class="wb-btn" onclick="wbRefresh('quick')">快速刷新</span>
      <span class="wb-btn" onclick="wbRefresh('full')">完整更新</span>
    </div>
  </div>

  <div class="layout">
    <div class="cal-col">
      <div class="hdr">
        <div><span class="m-title" id="mtitle"></span><span class="m-sub" id="msub" style="cursor:pointer" onclick="showUpdateInfo()"></span></div>
        <div class="hdr-r">
          <div class="nav" onclick="go(-1)">‹</div>
          <div class="nav" onclick="go(1)">›</div>
          <div class="today" onclick="goToday()">今天</div>
          <div class="today" style="color:#6cb6ff;background:rgba(10,132,255,.14)" onclick="openNotesView()">笔记</div>
        </div>
      </div>
      <div class="seg">
        <div class="seg-i on" id="segH" onclick="setMode('history')">历史回顾</div>
        <div class="seg-i" id="segU" onclick="setMode('upcoming')">未来预告</div>
      </div>
      <div class="wk"><div class="wk-i">日</div><div class="wk-i">一</div><div class="wk-i">二</div><div class="wk-i">三</div><div class="wk-i">四</div><div class="wk-i">五</div><div class="wk-i">六</div></div>
      <div class="grid" id="grid"></div>
      <div class="legend">
        <span><i class="h"></i>有数据</span>
        <span><i class="u"></i>预告</span>
        <span><i class="n"></i>笔记</span>
      </div>
    </div>

    <div class="content-col">
      <div class="panel" id="panel"></div>
    </div>
  </div>

  <div class="hint" id="hint"></div>

  <div class="sheet" id="noteEditor">
    <div class="sh-hd"><span class="sh-x" onclick="closeEditor()">‹</span><span class="sh-t" id="edDate"></span><span class="sh-s" onclick="saveNote()">保存</span></div>
    <div class="sh-bd">
      <textarea class="ta" id="edText" placeholder="这一天的想法、复盘、计划…"></textarea>
      <div class="chips" id="edTags"></div>
      <div class="bt d" id="edDel" style="margin-top:14px" onclick="deleteNote()">删除</div>
    </div>
  </div>

  <div class="sheet" id="notesView">
    <div class="sh-hd"><span class="sh-x" onclick="closeNotesView()">‹</span><span class="sh-t">我的笔记</span><span class="sh-c" id="nvCount"></span></div>
    <div class="sh-bd">
      <div class="nvtools">
        <span class="nvt" id="cloudBtn" style="display:none" onclick="openLogin()">登录同步</span>
        <span class="nvt" onclick="exportNotes()">导出备份</span>
        <span class="nvt" onclick="document.getElementById('nvFile').click()">导入备份</span>
        <input type="file" id="nvFile" accept="application/json,.json" style="display:none" onchange="importNotes(this)">
        <span class="nvt-tip" id="cloudTip">笔记只存在本机浏览器，建议定期导出</span>
      </div>
      <div class="sbar"><input id="nvSearch" placeholder="搜索笔记内容" oninput="renderNotesView()"></div>
      <div class="chips" id="nvTags"></div>
      <div id="nvList"></div>
    </div>
    <div class="fab" onclick="addNoteToday()">+</div>
  </div>

  <div class="sheet" id="loginSheet">
    <div class="sh-hd"><span class="sh-x" onclick="closeLogin()">‹</span><span class="sh-t">笔记同步</span></div>
    <div class="sh-bd">
      <div class="lg" id="lgSigned" style="display:none">
        <div class="lg-note">已登录 <b id="lgEmailOut"></b></div>
        <div class="lg-note" id="lgSyncInfo">笔记已存到云端，Mac 与手机登录同一账号即可看到同一份。</div>
        <div class="lg-btn ghost" id="lgSyncBtn" onclick="cloudSyncNow()">立即同步</div>
        <div class="lg-btn ghost" onclick="doSignOut()">退出登录</div>
      </div>

      <div class="lg" id="lgForm">
        <div class="lg-tabs">
          <div class="lg-tab on" id="tabPwd" onclick="setLgTab('pwd')">密码登录</div>
          <div class="lg-tab" id="tabOtp" onclick="setLgTab('otp')">验证码登录</div>
          <div class="lg-tab" id="tabReg" onclick="setLgTab('reg')">注册</div>
        </div>
        <div class="lg-f"><label>邮箱</label>
          <input id="lgEmailIn" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com">
        </div>
        <div class="lg-f" id="lgPwdWrap"><label id="lgPwdLab">密码</label>
          <input id="lgPwdIn" type="password" autocomplete="current-password" placeholder="请输入密码">
        </div>
        <div class="lg-row" id="lgCodeRow" style="display:none">
          <div class="lg-f"><label>邮箱验证码</label>
            <input id="lgCodeIn" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="邮件里的验证码">
          </div>
          <div class="lg-code" id="lgSendBtn" onclick="sendCode()">获取验证码</div>
        </div>
        <div class="lg-msg" id="lgMsg"></div>
        <div class="lg-btn" id="lgSubmit" onclick="submitLogin()">登录</div>
        <div class="lg-btn ghost" id="lgForgot" onclick="startForgot()">忘记密码</div>
        <div class="lg-sep"></div>
        <div class="lg-note">网页端仅支持<b>邮箱登录</b>（微信/手机号登录仅小程序可用）。<br>
          登录后笔记存到云端，Mac 和手机用同一邮箱登录就能看到同一份；<br>
          未登录时笔记只存在本机浏览器。</div>
      </div>
    </div>
  </div>
</div>

<script>
const HISTORY = __HISTORY__;
const UPCOMING = __UPCOMING__;
const META = __META__;
// 云版页面会注入 {endpoint, publishableKey}；本地与 GitHub Pages 版为 null（不启用云笔记）
const CLOUD_CFG = __CLOUD_CONFIG__;

const CAT={macro_us:{l:'美国数据',c:'us'},macro_cn:{l:'中国数据',c:'cn'},macro_eu:{l:'欧洲数据',c:'eu'},
  macro_jp:{l:'日本数据',c:'jp'},macro_kr:{l:'韩国数据',c:'kr'},shock:{l:'突发事件',c:'shock'},
  tech:{l:'技术突破',c:'tech'},policy:{l:'政策制度',c:'policy'},market:{l:'市场里程碑',c:'market'}};
// 地区角标：一眼看出这条事件属于哪个资本市场
const REG={US:'美国',CN:'中国',EU:'欧洲',JP:'日本',KR:'韩国',GLOBAL:'全球'};
const CONF={confirmed:{l:'已官宣',c:'confirmed'},estimated:{l:'规律推算',c:'estimated'},rumored:{l:'待官宣',c:'rumored'}};
const UP={}; UPCOMING.forEach(d=>UP[d.date]=d.items);
const IND=META.indicators||{};
// 数值存的是紧凑数组 [指标键,实际,预期,前值,同比,环比]，这里展开成对象
const CALC=META.calCountries||[], CALN=META.calNames||[];
let calFilter='key', calAllCache=[], calKeyCache=[];
function expandCal(arr,vbk){return (arr||[]).map((x,i)=>{const mk=x[6]||'';const v=mk?vbk[mk]:null;
  let pd='';if(x[5]){const mm=+x[5].slice(2);
    pd=(x[5].slice(0,2)===sel.slice(2,4))?mm+' 月':x[5].slice(0,2)+'年'+mm+'月'}
  return {tm:x[0],co:CALC[x[1]]||'',n:CALN[x[2]]||'',i:x[3]||1,k:x[4]||0,pd,
    anr:i<18,a:v?v.a:null,f:v?v.f:null,p:v?v.p:null,u:v?v.u:''}})}
function setCalFilter(f){if(f===calFilter)return;calFilter=f;renderPanel()}
function expand(arr){return (arr||[]).map(x=>{const m=IND[x[0]]||{n:x[0],u:'',i:2};
  return {k:x[0],n:m.n,u:m.u,i:m.i||2,a:x[1],f:x[2],p:x[3],y:x[4],m:x[5]}})}

const NOW=new Date();
const pad=n=>n<10?'0'+n:''+n;
const ymd=d=>d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
const TODAY=ymd(NOW);
let year=NOW.getFullYear(), month=NOW.getMonth()+1, sel=TODAY, mode='history';

const dim=(y,m)=>new Date(y,m,0).getDate();
const addM=(y,m,d)=>{const t=y*12+(m-1)+d;return{y:Math.floor(t/12),m:(t%12)+1}};
const WK=['日','一','二','三','四','五','六'];
function weekCn(s){return WK[new Date(s+'T00:00:00').getDay()]}
function diffDays(a,b){return Math.round((new Date(b+'T00:00:00')-new Date(a+'T00:00:00'))/86400000)}

function histSet(y,m){const p=y+'-'+pad(m)+'-';const s={};for(const k in HISTORY){if(k.indexOf(p)===0)s[k]=true}return s}
function monthEmpty(y,m){const p=y+'-'+pad(m)+'-';for(const k in HISTORY){if(k.indexOf(p)===0)return false}return true}
function upSet(y,m){const p=y+'-'+pad(m)+'-';const s={};for(const k in UP)if(k.indexOf(p)===0)s[k]=true;return s}

function fp(p){const n=+p;return (n>0?'+':(n<0?'-':''))+Math.abs(n).toFixed(2)+'%'}
function fv(v,u){if(v===null||v===undefined||v==='')return '—';const n=+v;if(isNaN(n))return '—';
  const ab=Math.abs(n);let s;if(ab%1===0){s=String(ab)}else{s=ab.toFixed(2).replace(/0+$/,'').replace(/\.$/,'')};
  return (n<0?'-':'')+s+(u||'')}
function biasOf(a,f){if(a==null||f==null)return null;const d=+a-+f;if(isNaN(d))return null;
  if(Math.abs(d)<1e-6)return{t:'符合预期',c:'flat'};return d>0?{t:'高于预期',c:'up'}:{t:'低于预期',c:'down'}}

function renderGrid(){
  document.getElementById('mtitle').textContent=year+'年'+month+'月';
  document.getElementById('msub').textContent='内置离线数据 · 点此查看更新方式';
  const hs=histSet(year,month), us=upSet(year,month), ndays=noteDays(year,month);
  const total=dim(year,month), lead=new Date(year,month-1,1).getDay();
  const prev=addM(year,month,-1), pt=dim(prev.y,prev.m), next=addM(year,month,1);
  let cells=[];
  for(let i=lead-1;i>=0;i--)cells.push({y:prev.y,m:prev.m,d:pt-i,cur:false});
  for(let d=1;d<=total;d++)cells.push({y:year,m:month,d,cur:true});
  let nd=1;while(cells.length<42)cells.push({y:next.y,m:next.m,d:nd++,cur:false});
  document.getElementById('grid').innerHTML=cells.map(c=>{
    const s=c.y+'-'+pad(c.m)+'-'+pad(c.d), md=pad(c.m)+'-'+pad(c.d);
    const cls=['cell',c.cur?'':'dim',s===sel?'sel':'',s===TODAY?'today':''].join(' ');
    const dot=(hs[s]&&mode==='history')?'<div class="dot dot-h"></div>':'';
    const ndot=(ndays[s])?'<div class="dot dot-n"></div>':'';
    const dot2=(us[s]&&mode==='upcoming')?'<div class="dot dot-u"></div>':'';
    return `<div class="${cls}" onclick="pick(${c.y},${c.m},${c.d})"><div class="num">${c.d}</div><div class="dots">${dot}${dot2}${ndot}</div></div>`;
  }).join('');
}

function pick(y,m,d){sel=y+'-'+pad(m)+'-'+pad(d);year=y;month=m;renderGrid();renderPanel()}
function go(d){const b=addM(year,month,d);year=b.y;month=b.m;renderGrid()}
function goToday(){const t=new Date();year=t.getFullYear();month=t.getMonth()+1;sel=TODAY;renderGrid();renderPanel()}
function setMode(m){mode=m;document.getElementById('segH').className='seg-i'+(m==='history'?' on':'');
  document.getElementById('segU').className='seg-i'+(m==='upcoming'?' on':'');renderGrid();renderPanel()}

function decorate(items,date){
  return (items||[]).map(x=>{
    const c=CAT[x.c]||{l:'事件',c:'market'}, cf=CONF[x.cf]||CONF.estimated;
    const n=diffDays(TODAY,date);
    const cd=n===0?'今天':(n===1?'明天':(n>1?n+' 天后':'已过去'));
    // v 是「上一期实际值」锚点，不是本期预期；本期预期需云端同步
    let v=null;
    if(x.v&&x.v.a!=null){
      v={txt:fv(x.v.a,x.v.u),n:x.v.n,date:x.v.d,
         prev:(x.v.p==null?'':fv(x.v.p,x.v.u)),
         y:(x.v.y==null?'':'同比 '+fv(x.v.y,x.v.u)),
         m:(x.v.m==null?'':'环比 '+fv(x.v.m,x.v.u))};
    }
    return {t:x.t,d:x.d,tm:x.tm,label:c.l,cls:'tag-'+c.c,cl:cf.l,ccls:'conf-'+cf.c,cd,v};
  });
}

function tagHtml(it){return `<span class="tag ${it.cls}">${it.label}</span>`}

function renderPanel(){
  const md=sel.slice(5);
  const p=document.getElementById('panel');
  const dnum=+sel.slice(8,10);
  const yr=(META.stats&&META.stats.yearRange)?META.stats.yearRange.join('–'):'—';
  const nd=monthEmpty(year,month)?`<div class="nodata">${year}年${month}月 暂无收录 · 数据覆盖 ${yr}</div>`:'';
  const head=`<div class="ph"><span class="ph-d">${sel.slice(0,4)}年${+sel.slice(5,7)}月${dnum}日</span><span class="ph-w">星期${weekCn(sel)}</span></div>`+nd;
  let html=head;

  if(mode==='history'){
    const day=HISTORY[sel]||{e:[],v:[],s:null};
    let dvals=expand(day.v);
    const vbk={}; dvals.forEach(x=>vbk[x.k]=x);
    const cal=expandCal(day.c,vbk);
    const linked={}; cal.forEach(x=>{if(x.a!==null&&x.a!==undefined)linked[x.k]=1});
    // 日历行已带出实际值的指标，从「关键数值」里剔除，避免同一读数出现两遍
    dvals=dvals.filter(x=>!linked[x.k]);

    if(cal.length){
      calAllCache=cal; calKeyCache=cal.filter(x=>x.i>=2);
      // 全是 ★ 级信息时自动回落到全部，否则卡片会是空白
      const shown=(!calKeyCache.length||calFilter==='all')?calAllCache:calKeyCache;
      const nv=cal.filter(x=>x.a!==null&&x.a!==undefined).length;
      html+=`<div class="card"><div class="card-title"><span>财经日历</span><span class="src">${cal.length} 项${nv?' · 已公布 '+nv:''}</span></div>`+
        (calKeyCache.length?`<div class="calf">`+
          `<div class="calf-i ${calFilter==='key'?'on':''}" onclick="setCalFilter('key')">重点 ${calKeyCache.length}</div>`+
          `<div class="calf-i ${calFilter==='all'?'on':''}" onclick="setCalFilter('all')">全部 ${calAllCache.length}</div>`+
        `</div>`:'')+
        shown.map((x,i)=>{const b=biasOf(x.a,x.f);
          return `<div class="ci c${x.i}${x.anr?' anr':''}" style="animation-delay:${x.anr?i*22:0}ms">`+
            `<div class="ci-t">${x.tm||''}</div><div class="ci-bar"></div><div class="ci-b">`+
            `<div class="ci-h"><span class="ci-n">${esc(x.n)}</span>${x.pd?`<span class="ci-pd">${x.pd}</span>`:''}</div>`+
            `<div class="ci-m">${x.co?`<span class="ci-co">${esc(x.co)}</span>`:''}`+
              `${x.k===1?'<span class="ci-co">事件</span>':(x.k===2?'<span class="ci-co">动态</span>':'')}`+
              `${b&&x.a!==null&&x.a!==undefined?`<span class="bias bias-${b.c}">${b.t}</span>`:''}</div>`+
            `${x.a!==null&&x.a!==undefined?`<div class="ci-v"><span class="civ civ-a">${fv(x.a,x.u)}</span>`+
              `${x.f!=null?`<span class="civ">预期 ${fv(x.f,x.u)}</span>`:''}`+
              `${x.p!=null?`<span class="civ">前值 ${fv(x.p,x.u)}</span>`:''}</div>`:''}`+
            `</div></div>`}).join('')+`</div>`;
    }
    if(dvals.length){
      html+=`<div class="card"><div class="card-title"><span>关键数值</span><span class="src">${dvals.length} 项</span></div>`+
        dvals.map(x=>{const b=biasOf(x.a,x.f);
          const ex=(x.y!=null||x.m!=null)?`<div class="vextra">${x.y!=null?`<span>同比 ${fv(x.y,x.u)}</span>`:''}${x.m!=null?`<span>环比 ${fv(x.m,x.u)}</span>`:''}</div>`:'';
          const st=x.i>=3?'★★★':(x.i===2?'★★':'★');
          return `<div class="vrow"><div class="vhead"><span class="stars ${x.i>=3?'hot':''}">${st}</span><span class="vname">${x.n}</span>${b?`<span class="bias bias-${b.c}">${b.t}</span>`:''}</div>`+
            `<div class="vgrid"><div class="vcell"><span class="vlab">实际</span><span class="vval ${x.a!=null?'vreal':''}">${fv(x.a,x.u)}</span></div>`+
            ((x.f==null&&x.p==null)?`<div class="vcell vnote"><span class="vlab">口径</span><span class="vval vsub vsmall">官方数据 · 无公开预期</span></div>`
              :`<div class="vcell"><span class="vlab">市场预期</span><span class="vval vsub">${fv(x.f,x.u)}</span></div>`+
               `<div class="vcell"><span class="vlab">前值</span><span class="vval vsub">${fv(x.p,x.u)}</span></div>`)+`</div>${ex}</div>`}).join('')+`</div>`;
    }
    if(day.s&&day.s.up&&day.s.up.length){
      html+=`<div class="card"><div class="card-title"><span>A 股领涨 / 领跌板块</span><span class="src">实盘 ${day.s.date}</span></div><div class="two">
        <div class="col"><div class="col-t up">领涨</div>${day.s.up.map(x=>`<div class="bk"><span class="bk-n">${x.n}</span><span class="bk-p up">${fp(x.p)}</span></div>`).join('')}</div>
        <div class="col"><div class="col-t down">领跌</div>${day.s.down.map(x=>`<div class="bk"><span class="bk-n">${x.n}</span><span class="bk-p down">${fp(x.p)}</span></div>`).join('')}</div></div>
        <div class="breadth">当日 ${day.s.bt} 个板块 · <span class="up">${day.s.br} 涨</span> / <span class="down">${day.s.bt-day.s.br} 跌</span></div></div>`;
    }
    if(day.e&&day.e.length){
      html+=`<div class="card"><div class="card-title"><span>这一天发生的大事件</span><span class="src">${day.e.length} 条</span></div>`+
        day.e.map(x=>{const c=CAT[x.c]||{l:'事件',c:'market'};
          const g=x.r?(REG[x.r]||x.r):'';
          return `<div class="row"><div><div class="ev-h"><span class="tag tag-${c.c}">${c.l}</span>`+
            (g?`<span class="tag g-${x.r.toLowerCase()}">${g}</span>`:'')+
            `<span class="ev-t">${x.t}</span></div><div class="ev-d">${x.d}</div></div></div>`}).join('')+`</div>`;
    }
    (day.u||[]).forEach(u=>{
      html+=`<div class="card"><div class="card-title"><span>UP 主观点 · ${u.n||'UP 主'}</span><span class="src">转写提炼</span></div>`+
        `<div class="up-t">${esc(u.t||'')}</div>`+
        (u.p||[]).map(pt=>`<div class="up-pt"><span class="up-dot">·</span><span class="up-tx">${esc(pt)}</span></div>`).join('')+
        `<div class="up-link" onclick="window.open('https://www.bilibili.com/video/${u.k}','_blank')">在 B 站看原视频 ›</div></div>`;
    });
    if(!(day.s&&day.s.up&&day.s.up.length)&&!(day.e&&day.e.length)&&!dvals.length&&!cal.length&&!(day.u&&day.u.length))
      html+=`<div class="empty">${sel} 暂无收录<div class="empty-sub">这一天没有发布重要数据，也没有收录到重大事件</div></div>`;
  } else {
    const items=decorate(UP[sel],sel);
    if(items.length){
      html+=`<div class="card"><div class="card-title"><span>当日事件</span><span class="src">${items.length} 条</span></div>`+
        items.map(i=>{const va=i.v?`<div class="vanchor"><span class="va-lab">上次</span><span class="va-val">${i.v.txt}</span>`+
          `<span class="va-src">${i.v.n} · ${i.v.date}</span>${i.v.prev?`<span class="va-prev">前值 ${i.v.prev}</span>`:''}`+
          `${i.v.y?`<span class="va-exp">${i.v.y}</span>`:''}${i.v.m?`<span class="va-exp">${i.v.m}</span>`:''}`+
          `<span class="va-wait">本期市场预期待云端同步</span></div>`:'';
          return `<div class="row"><div><div class="ev-h">${tagHtml(i)}<span class="conf ${i.ccls}">${i.cl}</span><span class="ev-t">${i.t}</span></div><div class="ev-d">${i.d}</div>${va}<div class="ev-m"><span class="tm">${i.tm}</span> · <span class="cd">${i.cd}</span></div></div></div>`}).join('')+`</div>`;
    } else {
      html+=`<div class="empty">这一天暂无预告事件</div>`;
    }
    const list=Object.keys(UP).filter(k=>k>=TODAY).sort();
    html+=`<div class="card"><div class="card-title"><span>未来 ${META.horizonDays} 天重点日程</span><span class="src">${list.length} 天有事件</span></div>`;
    list.forEach(k=>{
      const n=diffDays(TODAY,k);
      html+=`<div class="dsep"><span class="dsep-d">${k}</span><span class="dsep-w">周${weekCn(k)}</span><span class="dsep-c">${n===0?'今天':(n===1?'明天':n+' 天后')}</span></div>`;
      decorate(UP[k],k).forEach(i=>{
        html+=`<div class="row"><div><div class="ev-h">${tagHtml(i)}<span class="conf ${i.ccls}">${i.cl}</span><span class="ev-t">${i.t}</span></div><div class="ev-d">${i.d}</div><div class="ev-m"><span class="tm">${i.tm}</span></div></div></div>`;
      });
    });
    html+=`</div>`;
  }
  html+=renderNoteCard();
  html+=`<div class="foot"><span class="foot-t" onclick="toggleHint()">数据来源与更新说明 ›</span></div>`;
  p.innerHTML=html; p.scrollTop=0;
}

// ============ 我的笔记（localStorage 持久化，模拟小程序 storage）============
const NKEY='mc_notes_v1';
const NTAGS=['复盘','计划','观察','灵感'];
function loadNotes(){try{return JSON.parse(localStorage.getItem(NKEY)||'{}')}catch(e){return {}}}
function saveNotes(o){try{localStorage.setItem(NKEY,JSON.stringify(o))}catch(e){}}
let NOTES=loadNotes();
let edId=null, edDate='', edTags=[], nvTag='';

function notesByDate(d){return Object.keys(NOTES).map(k=>NOTES[k]).filter(n=>n.date===d&&!n.deleted).sort((a,b)=>a.createdAt-b.createdAt)}
function notesAll(){return Object.keys(NOTES).map(k=>NOTES[k]).filter(n=>!n.deleted)
  .sort((a,b)=> a.date===b.date ? b.createdAt-a.createdAt : (a.date<b.date?1:-1))}
function noteDays(y,m){const p=y+'-'+pad(m)+'-';const s={};
  Object.keys(NOTES).forEach(k=>{const n=NOTES[k];if(!n.deleted&&n.date&&n.date.indexOf(p)===0)s[n.date]=true});return s}
function fmtTime(ts){if(!ts)return '';const d=new Date(ts);return pad(d.getHours())+':'+pad(d.getMinutes())}
function fmtDateTime(ts){if(!ts)return '';const d=new Date(ts);return pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes())}

function renderNoteCard(){
  const list=notesByDate(sel);
  let h=`<div class="card note-card"><div class="card-title"><span>我的笔记</span><span class="nbtn" onclick="openEditor('${sel}',null)">＋ 写点想法</span></div>`;
  if(!list.length){ h+=`<div class="nem">这一天还没有笔记，点右上角记录你的想法</div>`; }
  else {
    list.forEach(n=>{
      const tg=(n.tags||[]).map(t=>`<span class="ntag">${t}</span>`).join('');
      h+=`<div class="nrow" onclick="openEditor('${n.date}','${n.id}')"><div class="nh"><span class="ntm">${fmtTime(n.updatedAt)}</span>${tg}</div><div class="ntx">${esc(n.text)}</div></div>`;
    });
  }
  return h+`</div>`;
}
function esc(t){return String(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

function openEditor(date,id){
  edDate=date; edId=id;
  const n=id?NOTES[id]:null;
  document.getElementById('edDate').textContent=date.slice(0,4)+'.'+date.slice(5,7)+'.'+date.slice(8,10);
  document.getElementById('edText').value=n?n.text:'';
  edTags=n?(n.tags||[]).slice():[];
  document.getElementById('edDel').style.display=id?'block':'none';
  renderEdTags();
  document.getElementById('noteEditor').className='sheet on';
}
function renderEdTags(){
  document.getElementById('edTags').innerHTML=NTAGS.map(t=>
    `<div class="chip ${edTags.indexOf(t)>=0?'on':''}" onclick="toggleEdTag('${t}')">${t}</div>`).join('');
}
function toggleEdTag(t){const i=edTags.indexOf(t);if(i>=0)edTags.splice(i,1);else edTags.push(t);renderEdTags()}
function closeEditor(){document.getElementById('noteEditor').className='sheet';renderGrid();renderPanel()}
function saveNote(){
  const txt=document.getElementById('edText').value.trim();
  if(!txt){alert('写点什么吧');return}
  const old=edId?NOTES[edId]:null;
  // 必须带随机数：仅用时间戳时，同一毫秒内新建的两条会互相覆盖
  const id=edId||('n'+Date.now().toString(36)+Math.random().toString(36).slice(2,6));
  NOTES[id]={id,date:edDate,text:txt,tags:edTags.slice(),
    createdAt:old?old.createdAt:Date.now(),updatedAt:Date.now()};
  saveNotes(NOTES);
  cloudSave(NOTES[id]);            // 云版才生效；未登录/本地版是空操作
  closeEditor();
}
function deleteNote(){
  if(!edId)return;
  if(!confirm('删除这条笔记？删除后无法恢复'))return;
  NOTES[edId]={...(NOTES[edId]||{}),deleted:true,updatedAt:Date.now()};
  saveNotes(NOTES);
  cloudSave(NOTES[edId]);          // 写墓碑，另一台设备才会把这条也删掉
  closeEditor();
}

function openNotesView(){renderNotesView();document.getElementById('notesView').className='sheet on'}
function closeNotesView(){document.getElementById('notesView').className='sheet';renderGrid();renderPanel()}
function renderNotesView(){
  const kw=(document.getElementById('nvSearch').value||'').trim().toLowerCase();
  document.getElementById('nvTags').innerHTML=
    `<div class="chip ${nvTag===''?'on':''}" onclick="setNvTag('')">全部</div>`+
    NTAGS.map(t=>`<div class="chip ${nvTag===t?'on':''}" onclick="setNvTag('${t}')">${t}</div>`).join('');
  let list=notesAll();
  if(nvTag)list=list.filter(n=>(n.tags||[]).indexOf(nvTag)>=0);
  if(kw)list=list.filter(n=>(n.text||'').toLowerCase().indexOf(kw)>=0);
  document.getElementById('nvCount').textContent='共 '+notesAll().length+' 条';
  document.getElementById('nvList').innerHTML=list.length? list.map(n=>{
    const tg=(n.tags||[]).map(t=>`<span class="nit-t">${t}</span>`).join('');
    return `<div class="nit" onclick="openEditor('${n.date}','${n.id}')">
      <div class="nit-h"><span class="nit-d">${n.date.slice(0,4)}.${n.date.slice(5,7)}.${n.date.slice(8,10)}</span>
      <span class="nit-w">周${weekCn(n.date)}</span>${tg}<span class="nit-tm">${fmtDateTime(n.updatedAt)}</span></div>
      <div class="nit-x">${esc(n.text.slice(0,90))}${n.text.length>90?'…':''}</div></div>`;
  }).join('') : `<div class="empty">${kw||nvTag?'没有匹配的笔记':'还没有笔记'}</div>`;
}
function setNvTag(t){nvTag=t;renderNotesView()}
function addNoteToday(){openEditor(TODAY,null)}

// ---- 笔记导出 / 导入 ----------------------------------------------------
// 笔记存在 localStorage（本机浏览器），换设备、换浏览器、清缓存都会丢，
// 所以必须给一条「搬走」的通路：导出成 JSON 文件，在另一台设备导入。
// 导入按 updatedAt 后写胜出，跟小程序端云同步的冲突策略保持一致。
function exportNotes(){
  const live=Object.keys(NOTES).filter(k=>!NOTES[k].deleted).length;
  if(!live){alert('还没有笔记可以导出');return}
  const payload={format:'market-calendar-notes',version:1,
    exportedAt:new Date().toISOString(),count:live,notes:NOTES};
  const blob=new Blob([JSON.stringify(payload,null,1)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url; a.download='市场日历笔记_'+TODAY+'.json';
  document.body.appendChild(a); a.click();
  setTimeout(function(){URL.revokeObjectURL(url);a.remove()},800);
}
function importNotes(input){
  const f=input.files&&input.files[0];
  if(!f)return;
  const rd=new FileReader();
  rd.onload=function(){
    try{
      const j=JSON.parse(rd.result)||{};
      let incoming=(j.notes&&typeof j.notes==='object')?j.notes:null;
      if(!incoming&&typeof j==='object'&&!j.format){
        // 裸的 {id:note} 旧格式也接受
        incoming=j;
      }
      if(Array.isArray(incoming)){
        const o={};incoming.forEach(function(n){if(n&&n.id)o[n.id]=n});incoming=o;
      }
      if(!incoming){alert('文件里没有笔记数据');input.value='';return}
      let added=0,updated=0,skipped=0;
      Object.keys(incoming).forEach(function(id){
        const n=incoming[id];
        if(!n||typeof n!=='object'||!n.date)return;
        const old=NOTES[id];
        if(!old){NOTES[id]=n;added++}
        else if((n.updatedAt||0)>(old.updatedAt||0)){NOTES[id]=n;updated++}
        else skipped++;
      });
      saveNotes(NOTES);
      renderNotesView(); renderGrid(); renderPanel();
      alert('导入完成\n新增 '+added+' 条，更新 '+updated+' 条'
        +(skipped?'，跳过 '+skipped+' 条（本地版本更新）':''));
    }catch(e){
      alert('导入失败：这不是有效的笔记备份文件\n'+e.message);
    }
    input.value='';
  };
  rd.readAsText(f,'utf-8');
}

// ============ 云端同步（仅云版页面启用；本地与 Pages 版 CLOUD_CFG 为 null）============
// 为什么需要它：localStorage 按「设备 + 浏览器」隔离，Mac 和手机各自一份。
// 登录后笔记改存云数据库（按账号隔离，owner_id 由服务端 auth.uid() 填充），
// 两台设备用同一邮箱登录即共用一份。
// 冲突策略与小程序端保持一致：按 updatedAt「后写胜出」；删除写墓碑，避免被旧数据复活。
let cloud=null, cloudUser=null, lgTab='pwd', pendingOtp=null, otpTimer=null, resetCtx=null;
const CT='mc_notes';

function val(id){return (document.getElementById(id).value||'').trim()}
function setLgMsg(t,ok){const e=document.getElementById('lgMsg');e.textContent=t||'';e.className='lg-msg'+(ok?' ok':'')}
function safeTags(v){try{const a=JSON.parse(v||'[]');return Array.isArray(a)?a:[]}catch(e){return []}}

async function initCloud(){
  if(!CLOUD_CFG||!window.WorkBuddyCloud)return;
  try{
    cloud=WorkBuddyCloud.createWorkBuddyCloud({
      endpoint:CLOUD_CFG.endpoint, publishableKey:CLOUD_CFG.publishableKey});
  }catch(e){return}
  document.getElementById('cloudBtn').style.display='';
  await bootCloud();
}
async function bootCloud(){
  if(!cloud)return;
  let r;
  try{ r=await cloud.auth.getSession(); }catch(e){ r={error:e}; }
  if(r.error||!r.data){ cloudUser=null; renderCloudBar(); return }
  cloudUser=r.data.user||r.data;
  renderCloudBar();
  await cloudPull();
}
function renderCloudBar(){
  const btn=document.getElementById('cloudBtn'), tip=document.getElementById('cloudTip');
  if(!cloud){ if(btn)btn.style.display='none'; return }
  btn.style.display='';
  if(cloudUser){
    btn.textContent='同步设置';
    tip.textContent='已登录 '+(cloudUser.email||'')+' · 笔记已同步到云端';
  }else{
    btn.textContent='登录同步';
    tip.textContent='登录后 Mac 与手机共用同一份笔记';
  }
}
function openLogin(){ renderLogin(); document.getElementById('loginSheet').className='sheet on' }
function closeLogin(){ document.getElementById('loginSheet').className='sheet' }
function renderLogin(){
  const signed=!!cloudUser;
  document.getElementById('lgSigned').style.display=signed?'flex':'none';
  document.getElementById('lgForm').style.display=signed?'none':'flex';
  if(signed)document.getElementById('lgEmailOut').textContent=cloudUser.email||'';
}
function setLgTab(t){
  lgTab=t; pendingOtp=null; resetCtx=null;
  const map={pwd:'tabPwd',otp:'tabOtp',reg:'tabReg'};
  Object.keys(map).forEach(function(k){
    document.getElementById(map[k]).className='lg-tab'+(k===t?' on':'')});
  const isReg=t==='reg', isOtp=t==='otp';
  document.getElementById('lgPwdWrap').style.display=isOtp?'none':'flex';
  document.getElementById('lgCodeRow').style.display=(isOtp||isReg)?'flex':'none';
  document.getElementById('lgForgot').style.display=(t==='pwd')?'flex':'none';
  document.getElementById('lgPwdLab').textContent=isReg?'设置密码（至少 6 位）':'密码';
  document.getElementById('lgPwdIn').setAttribute('autocomplete',isReg?'new-password':'current-password');
  document.getElementById('lgSubmit').textContent=isReg?'注册并登录':(isOtp?'验证码登录':'登录');
  setLgMsg('');
}
async function sendCode(){
  const email=val('lgEmailIn');
  if(!email||email.indexOf('@')<0){setLgMsg('请先填写邮箱');return}
  const btn=document.getElementById('lgSendBtn');
  if(btn.className.indexOf('dis')>=0)return;
  btn.className='lg-code dis'; btn.textContent='发送中…';
  const sent=await cloud.auth.sendOtp({email:email});
  if(sent.error){
    setLgMsg(sent.error.message||'验证码发送失败');
    btn.className='lg-code'; btn.textContent='获取验证码'; return;
  }
  // challenge 必须留在事件外：提交时复用它，绝不重新发码
  pendingOtp={email:email, verificationId:sent.data.verificationId,
    isExistingUser:sent.data.isExistingUser};
  setLgMsg('验证码已发送，请查收邮件',true);
  let n=60; btn.textContent=n+'s 后可重发';
  otpTimer=setInterval(function(){
    n--; if(n<=0){clearInterval(otpTimer); btn.className='lg-code'; btn.textContent='获取验证码'}
    else btn.textContent=n+'s 后可重发';
  },1000);
}
async function submitLogin(){
  const email=val('lgEmailIn'), pwd=val('lgPwdIn'), code=val('lgCodeIn');
  if(!email||email.indexOf('@')<0){setLgMsg('请填写邮箱');return}
  const btn=document.getElementById('lgSubmit');
  btn.className='lg-btn dis';
  try{
    if(lgTab==='pwd'){
      const r=await cloud.auth.signInWithPassword({email:email,password:pwd});
      if(r.error){setLgMsg('邮箱或密码不正确');return}
      await afterLogin();
    }else if(lgTab==='otp'){
      const p=pendingOtp;
      if(!p||p.email!==email){setLgMsg('请先获取当前邮箱的验证码');return}
      const r=await cloud.auth.verifyOtp({email:p.email,verificationId:p.verificationId,
        isExistingUser:p.isExistingUser,token:code});
      if(r.error){setLgMsg(r.error.message||'验证码不正确');return}
      pendingOtp=null; await afterLogin();
    }else if(lgTab==='reg'){
      const p=pendingOtp;
      if(!p||p.email!==email){setLgMsg('请先获取当前邮箱的验证码');return}
      if((pwd||'').length<6){setLgMsg('密码至少 6 位');return}
      // 邮箱注册必须带密码：不带的话这个账号以后无法用密码登录
      const r=await cloud.auth.verifyOtp({email:p.email,verificationId:p.verificationId,
        isExistingUser:p.isExistingUser,token:code,
        password:p.isExistingUser?undefined:pwd});
      if(r.error){setLgMsg(r.error.message||'注册失败');return}
      pendingOtp=null; await afterLogin();
    }else if(lgTab==='reset'){
      if(!resetCtx){setLgMsg('请先获取验证码');return}
      if((pwd||'').length<6){setLgMsg('新密码至少 6 位');return}
      const r=await resetCtx.updateUser({nonce:code,password:pwd});
      if(r.error){setLgMsg(r.error.message||'重置失败');return}
      resetCtx=null; await afterLogin();
    }
  }catch(e){
    setLgMsg('网络异常，请稍后重试');
  }finally{
    btn.className='lg-btn';
  }
}
async function startForgot(){
  const email=val('lgEmailIn');
  if(!email||email.indexOf('@')<0){setLgMsg('请先填写邮箱');return}
  const r=await cloud.auth.resetPasswordForEmail(email);
  if(r.error){setLgMsg(r.error.message||'发送失败');return}
  resetCtx=r.data;
  lgTab='reset';
  document.getElementById('lgPwdWrap').style.display='flex';
  document.getElementById('lgCodeRow').style.display='flex';
  document.getElementById('lgForgot').style.display='none';
  document.getElementById('lgPwdLab').textContent='新密码（至少 6 位）';
  document.getElementById('lgPwdIn').value='';
  document.getElementById('lgSubmit').textContent='重置密码';
  setLgMsg('验证码已发送到邮箱，请输入验证码和新密码',true);
}
async function afterLogin(){
  closeLogin();
  await bootCloud();
  renderNotesView(); renderGrid(); renderPanel();
}
async function doSignOut(){
  try{ await cloud.auth.signOut(); }catch(e){}
  cloudUser=null;
  renderLogin(); renderCloudBar();
  renderNotesView(); renderGrid(); renderPanel();
}
async function cloudSyncNow(){
  const b=document.getElementById('lgSyncBtn');
  b.textContent='同步中…';
  await cloudPull(true);
  await cloudPushAll();
  b.textContent='立即同步';
  renderNotesView(); renderGrid(); renderPanel();
}
async function cloudPushAll(){
  if(!cloud||!cloudUser)return 0;
  const rows=Object.keys(NOTES).map(function(k){return noteToRow(NOTES[k])});
  if(!rows.length)return 0;
  const r=await cloud.database.from(CT).upsert(rows).select();
  if(r.error){renderCloudBar();return 0}
  return rows.length;
}
function noteToRow(n){
  return {id:n.id, note_date:n.date, body:n.text||'',
    tags:JSON.stringify(n.tags||[]), created_at:n.createdAt||Date.now(),
    updated_at:n.updatedAt||Date.now(), deleted:!!n.deleted};
}
async function cloudPull(loud){
  if(!cloud||!cloudUser)return 0;
  const r=await cloud.database.from(CT).select('*');
  if(r.error){
    if(loud)alert('云端读取失败：'+(r.error.message||'未知错误'));
    return 0;
  }
  let changed=0;
  (r.data||[]).forEach(function(row){
    const local=NOTES[row.id];
    if(local&&(row.updated_at||0)<=(local.updatedAt||0))return;
    if(row.deleted){ delete NOTES[row.id]; }
    else{
      NOTES[row.id]={id:row.id,date:row.note_date,text:row.body||'',
        tags:safeTags(row.tags),createdAt:row.created_at||Date.now(),
        updatedAt:row.updated_at||Date.now()};
    }
    changed++;
  });
  if(changed)saveNotes(NOTES);
  return changed;
}
async function cloudSave(note){
  if(!cloud||!cloudUser||!note)return;
  let r;
  try{ r=await cloud.database.from(CT).upsert(noteToRow(note)).select(); }
  catch(e){ r={error:e}; }
  // RLS 会挡掉不属于自己的行：空数组 / 报错都说明没写进去，必须让用户看见
  if(r.error||!(r.data&&r.data.length)){
    alert('笔记未同步到云端（'+((r.error&&r.error.message)||'权限被拒绝')+'），已保存在本机');
  }
}

function showUpdateInfo(){
  alert('数据更新说明\n\n'
    +'【当前】内置离线数据包，数据随版本发布，不会自动变化。\n\n'
    +'【开启每日自动更新】需要三步：\n'
    +'1. 开通云开发并填写环境 ID（app.js 的 cloudEnv / useCloud）\n'
    +'2. 部署 syncCalendar 云函数（含 08:00 与 18:00 定时触发）\n'
    +'3. 建立 market_daily 等数据库集合\n\n'
    +'部署后：云函数每日抓取并落库，客户端打开时自动合并，\n'
    +'顶部会显示「云端 18:05 更新」，点一下可手动刷新。\n\n'
    +'可更新的数据：A 股当日板块、宏观数值、本期市场预期。\n'
    +'需发版更新的数据：历史事件库。\n\n'
    +'详细步骤见项目根目录 DEPLOY.md');
}
function toggleHint(){
  const h=document.getElementById('hint');
  h.className = h.className.includes('on') ? 'hint' : 'hint on';
  h.innerHTML=`<b>数据覆盖</b>：${META.stats.days} 天历史 · ${META.stats.events} 条真实事件 · ${META.stats.sector_days} 天 A 股板块行情（${META.sectorRange[0]} ~ ${META.sectorRange[1]}）<br>
  <b>三档置信度</b>：<span class="conf conf-confirmed">已官宣</span> 官方公布日期 ｜ <span class="conf conf-estimated">规律推算</span> 按发布规律推算 ｜ <span class="conf conf-rumored">待官宣</span> 市场预期未官宣<br>
  <b>更新</b>：主包内置离线数据，断网可用；配置云开发后由云函数每日 08:00 / 18:00 抓取并落库，客户端自动合并。<br>
  <b>免责</b>：仅用于信息整理与复盘参考，不构成投资建议，日程与行情以官方发布为准。`;
}

// ============ 本地工作台状态条 ============
// 只在本地服务器（tools/workbench.py）可用时显示。
// 部署到静态托管（GitHub Pages）时 /api/status 不存在，静默隐藏 —— 同一份页面两种场景都能用。
let wbVer=null, wbTimer=null;
function wbSet(cls,text){
  const d=document.getElementById('wbDot'); if(d) d.className='wb-dot'+(cls?' '+cls:'');
  const t=document.getElementById('wbText'); if(t) t.textContent=text;
}
function wbInit(){
  fetch('/api/status',{cache:'no-store'})
    .then(r=>r.ok?r.json():Promise.reject(new Error('no api')))
    .then(d=>{
      const el=document.getElementById('wb'); if(!el) return;
      el.style.display='flex';
      wbVer=d.dataVersion;
      wbTick(d);
      wbTimer=setInterval(wbPoll,15000);
    })
    .catch(()=>{});
}
function wbPoll(){
  fetch('/api/status',{cache:'no-store'}).then(r=>r.json()).then(wbTick).catch(()=>{});
}
function wbTick(d){
  if(d.updating){
    const st=d.steps||[];
    const done=st.filter(s=>s.state==='done').length;
    wbSet('busy','正在更新 · '+(d.current||'准备中')+'（'+done+'/'+st.length+'）');
    return;
  }
  const t=d.lastSuccess?d.lastSuccess.slice(11,16):'—';
  const p=d.pendingUP||0;
  if(d.error){
    wbSet('err','上次更新出错：'+d.error+'（已沿用现有数据）');
  }else if(p>0){
    // 这一条很重要：转写是机器做的，但「要点」必须 AI 阅读后写入，
    // 所以点完「完整更新」B 站区块仍可能没有变化 —— 必须让用户看得见，不能静默。
    wbSet('warn','上次更新 '+t+' ｜ 有 '+p+' 个 B 站视频已转写但缺要点（这步需要 AI 提炼）');
  }else{
    wbSet('','本地工作台 · 上次更新 '+t+' · 数据变更后自动刷新');
  }
  if(wbVer && d.dataVersion && d.dataVersion!==wbVer){
    wbVer=d.dataVersion;
    setTimeout(()=>location.reload(),700);
  }
}
function wbRefresh(mode){
  const msg=mode==='full'
    ?'完整更新：抓日历/板块/宏观 + 下载并转写 B 站新视频。\n\n'
     +'耗时约 5-10 分钟（要跑本地语音识别）。\n\n'
     +'注意：转写只是「原材料」，要变成日历里的「要点」还需要 AI 读一遍——\n'
     +'所以点完之后 B 站区块可能仍无变化，状态栏会提示还差几个待提炼。\n\n继续？'
    :'快速刷新会重新抓取财经日历 / 板块行情 / 宏观数值，约 1-2 分钟，继续？';
  if(!confirm(msg)) return;
  fetch('/api/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:mode})})
    .then(r=>r.json())
    .then(d=>{
      if(d.error){ alert(d.error); return; }
      wbSet('busy','已开始更新…');
      setTimeout(wbPoll,1500);
    })
    .catch(()=>alert('无法连接本地服务，请确认 workbench.py 正在运行'));
}
wbInit();

renderGrid(); renderPanel();
initCloud();   // 云版：恢复登录态并拉取云端笔记；本地 / Pages 版直接返回
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')go(-1);if(e.key==='ArrowRight')go(1);if(e.key==='t')goToday()});
</script>
</body>
</html>
"""


def build_html(cloud_mode):
    """cloud_mode=False：数据内嵌（离线可用，本地预览与 GitHub Pages 用）
       cloud_mode=True ：数据运行时加载 + 云笔记（部署在 WorkBuddy 域名用）

    云版为什么不能内嵌数据：云服务要求请求来自本应用域名，所以页面部署在
    WorkBuddy 域名；而数据每天由 GitHub Actions 更新到 GitHub Pages。
    两边不同域，只能运行时用 <script> 加载（script 不受跨域限制）。
    """
    history = load_js_module("history.js")
    upcoming = load_js_module("upcoming.js")
    meta = load_js_module("meta.js")

    if cloud_mode:
        cfg = {}
        if os.path.exists(CCFG):
            with open(CCFG, encoding="utf-8") as f:
                cfg = json.load(f)
        if not cfg.get("endpoint") or not cfg.get("publishableKey"):
            raise SystemExit(f"[✗] 缺少云配置 {CCFG}（需先开通云服务，写回 endpoint 与 publishableKey）")
        head = "\n".join([
            f'<script src="{SDK_URL}"></script>',
            f'<script src="{DATA_BASE}/history.js"></script>',
            f'<script src="{DATA_BASE}/upcoming.js"></script>',
            f'<script src="{DATA_BASE}/meta.js"></script>',
        ])
        h, u, m = "(window.MC_HISTORY||{})", "(window.MC_UPCOMING||[])", "(window.MC_META||{})"
        c = json.dumps({"endpoint": cfg["endpoint"], "publishableKey": cfg["publishableKey"]})
    else:
        head = ""
        h = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
        u = json.dumps(upcoming, ensure_ascii=False, separators=(",", ":"))
        m = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
        c = "null"

    return (TPL
            .replace("__HEAD_SCRIPTS__", head)
            .replace("__HISTORY__", h)
            .replace("__UPCOMING__", u)
            .replace("__META__", m)
            .replace("__CLOUD_CONFIG__", c))


def main():
    cloud_mode = "--cloud" in sys.argv
    out = CLOUD_OUT if cloud_mode else OUT
    html = build_html(cloud_mode)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    tag = "云版（外部数据 + 云笔记）" if cloud_mode else "预览版"
    print(f"[✓] {tag}生成：{out}  ({os.path.getsize(out)/1024:.0f}KB)")


if __name__ == "__main__":
    main()
