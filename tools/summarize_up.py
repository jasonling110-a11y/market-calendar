# -*- coding: utf-8 -*-
"""
B 站 UP 主视频「要点兜底摘录」。

为什么需要它：up_summary.json 一直靠 AI 读转写后手写，机器不会做。结果是
新视频常常「已经转写好了、躺在 up_raw.json 里，但日历上没有卡片」——
也就是用户说的"总结更新不及时"。

本脚本用零依赖的抽取式摘录补上这个缺口：
  * 有 AI 手写总结（人工/模型校对过的）→ 原样保留，绝不被覆盖；
  * 只有转写、没有总结的新视频 → 摘出信息量最高的句子，标 auto=true 入包。
这样日历永远不空窗，之后再让 AI 润色成正式要点即可（AI 版会覆盖 auto 版）。

用法：
    python3 summarize_up.py            # 为所有待总结视频生成兜底摘录
    python3 summarize_up.py --force BV1SMa96EEZH   # 覆盖指定视频（含 AI 版）
    python3 summarize_up.py --dry        # 只看会摘出什么，不落盘
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "up_raw.json")
SUM = os.path.join(HERE, "data", "up_summary.json")

MAX_BULLETS = 10
CHUNK_MIN, CHUNK_MAX = 22, 150      # 句子长度窗口
TARGET = 130                        # 单条要点最终长度上限

# 语音转写的高频错字（只收「改了不会有歧义」的，宁缺勿错）
ASR_FIX = {
    "货罗姆斯": "霍尔木兹",
    "毛根大通": "摩根大通",
    "阿联球": "阿联酋",
    "卡特尔": "卡塔尔",
    "海蛮": "海湾",
    "通脏": "通胀",
    "胡散": "胡塞",
    "赞钱": "战前",
    "股主一致": "孤注一掷",
    "远有价格": "原油价格",
    "传队传转运": "船对船转运",
    "处游": "储油",
    "运输料": "运输量",
    "为灵": "为零",
    "中共的战势": "中东的战势",
    "脱压力": "拖压力",
    "新片半导体": "芯片半导体",
    "一论的影响力": "舆论的影响力",
    "意外长": "伊朗外长",
    "三百五十万同": "350万桶",
}
# 通用数字量词纠正：转写常把「桶」听成「同」
ASR_NUM = re.compile(r"(\d[\d,.]*\s*万?)同")

# 强信息词：命中一次算 3 分
KW_STRONG = re.compile(
    r"万桶|亿美元|万亿元?|百分点|基点|CPI|PPI|PCE|非农|失业率|GDP|PMI|议息|加息|降息|"
    r"降准|关税|油价|原油|天然气|黄金|白银|铜|国债|收益率|汇率|利率|通胀|通缩|社融|"
    r"出口|进口|贸易|财政|赤字|发债|美联储|欧央行|日本央行|中期选举|封锁|制裁|"
    r"霍尔木兹|红海|停火|谈判|协议|数据|同比|环比|增长|下滑|上升|下降"
)
# 结论/判断词：命中一次算 1.5 分
KW_MED = re.compile(
    r"核心|关键|结论|意味着|说明|原因|影响|预计|推演|判断|风险|策略|目标|变量|"
    r"一方面|另一方面|不排除|可能|大概|实际上|重点是|我个人的看法|观点"
)
# 口播填充词，出现在句首要剪掉
FILLER = re.compile(
    r"^(好[，,、]?|另外[，,]|其实[，,]|所以[，,]|那么[，,]|并且[，,]|同时[，,]|"
    r"也就是说[，,]|我想说的是[，,]|我想[，,]|大家[，,]|然后[，,]|因此[，,]|"
    r"但是[，,]|不过[，,]|而且[，,]|首先[，,]|其次[，,]|第三[，,]|"
    r"第二[，,]|第一[，,]|再一个[，,]|整体来看[，,]|综合来看[，,])+"
)


def load(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fix_asr(s):
    s = ASR_NUM.sub(r"\1桶", s)
    for a, b in ASR_FIX.items():
        s = s.replace(a, b)
    return s


def split_clauses(text):
    """转写稿几乎只有逗号：先用句末标点切，过长的句子再按逗号打包成块。"""
    text = re.sub(r"\s+", "", text or "")
    out = []
    for seg in re.split(r"[。！？；;!?]+", text):
        seg = seg.strip("，,、 ")
        if not seg:
            continue
        if len(seg) <= CHUNK_MAX:
            out.append(seg)
            continue
        buf = ""
        for cl in re.split(r"[，,]+", seg):
            if not cl:
                continue
            if len(buf) + len(cl) + 1 <= CHUNK_MAX:
                buf = f"{buf},{cl}" if buf else cl
            else:
                if buf:
                    out.append(buf)
                buf = cl
        if buf:
            out.append(buf)
    return out


def score(chunk, idx, total):
    s = 0.0
    s += 3.0 * len(KW_STRONG.findall(chunk))
    s += 1.5 * len(KW_MED.findall(chunk))
    digits = len(re.findall(r"\d", chunk))
    s += min(digits * 0.35, 3.5)                     # 带具体数字的句子更值得留
    if CHUNK_MIN <= len(chunk) <= 120:
        s += 1.0                                     # 太短没信息、太长是碎句
    if total and idx < total * 0.15:
        s += 1.5                                     # 开头常是当期新闻
    if total and idx > total * 0.82:
        s += 0.8                                     # 结尾常是结论
    return s


def bigrams(s):
    s = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)
    return {s[i:i + 2] for i in range(max(len(s) - 1, 1))}


def jaccard(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def tidy(chunk):
    c = FILLER.sub("", chunk).strip("，,、 ")
    c = fix_asr(c)
    if len(c) > TARGET:                              # 尽量在逗号处收口
        cut = c[:TARGET]
        pos = max(cut.rfind("，"), cut.rfind(","))
        c = (cut[:pos] if pos > TARGET * 0.6 else cut).rstrip("，,、 ") + "…"
    return c


def extract(text):
    chunks = split_clauses(text)
    if not chunks:
        return []
    total = len(chunks)
    ranked = sorted(range(total), key=lambda i: -score(chunks[i], i, total))
    picked = []
    for i in ranked:
        if len(picked) >= MAX_BULLETS:
            break
        cand = tidy(chunks[i])
        if len(cand) < 12:
            continue
        # picked 存的是 (原句序号, 文本)，比对要去文本那一位
        if any(jaccard(cand, p[1]) >= 0.5 for p in picked):   # 去掉近重复句
            continue
        picked.append((i, cand))
    picked.sort(key=lambda t: t[0])                        # 还原时间顺序，读起来才顺
    return [c for _, c in picked]


def main():
    raw, summ = load(RAW), load(SUM)
    if not raw:
        print("[i] 还没有转写结果，先跑 fetch_bilibili.py")
        return

    force = set()
    if "--force" in sys.argv:
        rest = sys.argv[sys.argv.index("--force") + 1:]
        force = {x for x in rest if x.startswith("BV")}
    dry = "--dry" in sys.argv

    todo = [b for b in raw
            if (b not in summ or b in force
                or not (summ.get(b) or {}).get("p"))]
    if not todo:
        print(f"[✓] {len(raw)} 个视频都已有要点，无需兜底")
        return

    added = 0
    for bvid in sorted(todo, key=lambda x: raw[x].get("d", "")):
        v = raw[bvid]
        pts = extract(v.get("txt", ""))
        if not pts:
            print(f"  [!] {bvid} 转写太短，跳过")
            continue
        print(f"  {'·' if dry else '✓'} {v.get('d','')}  {str(v.get('t',''))[:30]}"
              f"  → 摘出 {len(pts)} 条")
        if dry:
            for p in pts:
                print(f"        - {p}")
            continue
        summ[bvid] = {
            "d": v.get("d", ""),
            "t": v.get("t", ""),
            "p": pts,
            "auto": True,          # 标记为机器摘录，UI 会显示「自动摘录」
        }
        added += 1

    if dry or not added:
        return
    with open(SUM, "w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, indent=1)
    print(f"[✓] 兜底摘录 {added} 个视频 → {SUM}")
    print("    提示：AI 润色后的正式要点会直接覆盖 auto 版（重新写入同一 bvid 即可）")


if __name__ == "__main__":
    main()
