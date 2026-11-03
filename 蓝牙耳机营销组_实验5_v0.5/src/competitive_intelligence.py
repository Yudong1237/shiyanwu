#!/usr/bin/env python3
"""Reproducible, evidence-linked competitive intelligence for experiment 5."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


WEIGHT_SCENARIOS = {
    "基准权重": {"consumer": 30, "product": 25, "price": 20, "heat": 25},
    "消费者重合加权": {"consumer": 40, "product": 20, "price": 15, "heat": 25},
    "产品重合加权": {"consumer": 25, "product": 35, "price": 15, "heat": 25},
    "价格重合加权": {"consumer": 25, "product": 20, "price": 35, "heat": 20},
    "品牌热度加权": {"consumer": 25, "product": 20, "price": 15, "heat": 40},
}
PRICE_BANDS = (("<100", 0, 100), ("100-199", 100, 200), ("200-399", 200, 400), ("400+", 400, math.inf))
REQUIRED_PRODUCT_FIELDS = {"record_id", "product_name", "brand", "category", "price", "rating", "review_count", "likes", "favorites"}
REQUIRED_REVIEW_FIELDS = {"review_id", "product_id", "brand", "rating", "sentiment", "topics", "evidence_quote", "source", "simulated"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def number(value: str, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无法将 {label} 解析为数值: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} 不是有限数值: {value!r}")
    return result


def pct(value: float) -> str:
    return f"{value:.2f}"


def rounded(value: float, digits: int = 2) -> float:
    return round(value, digits)


def share_overlap(left: Counter, right: Counter, left_total: float, right_total: float) -> float:
    if not left_total or not right_total:
        return 0.0
    keys = set(left) | set(right)
    return 100.0 * sum(min(left[k] / left_total, right[k] / right_total) for k in keys)


def price_band(price: float) -> str:
    for label, start, end in PRICE_BANDS:
        if start <= price < end:
            return label
    raise ValueError(f"价格不在可分箱范围内: {price}")


def family_name(product: dict[str, str]) -> str:
    name = product["product_name"].strip()
    brand = product["brand"].strip()
    return name[len(brand):].strip() if name.startswith(brand) else name


def brand_counts(products: list[dict[str, str]], reviews: list[dict[str, str]]):
    product_by_id = {row["record_id"]: row for row in products}
    product_brands: dict[str, list[dict[str, str]]] = defaultdict(list)
    review_brands: dict[str, list[dict[str, str]]] = defaultdict(list)
    product_topics: dict[str, Counter] = defaultdict(Counter)
    product_prices: dict[str, Counter] = defaultdict(Counter)
    product_families: dict[str, Counter] = defaultdict(Counter)
    sentiment_topics: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    all_topics: Counter = Counter()

    brands = list(dict.fromkeys(row["brand"].strip() for row in products))
    for row in products:
        brand = row["brand"].strip()
        row["_price"] = number(row["price"], f"{row['record_id']}.price")
        row["_rating"] = number(row["rating"], f"{row['record_id']}.rating") if row["rating"].strip() else None
        for field in ("review_count", "likes", "favorites"):
            row[f"_{field}"] = number(row[field], f"{row['record_id']}.{field}")
        product_by_id[row["record_id"]] = row
        product_brands[brand].append(row)
        product_prices[brand][price_band(row["_price"])] += 1
        product_families[brand][family_name(row)] += 1

    if len(product_by_id) != len(products):
        raise ValueError("clean_data.csv 存在重复 record_id")

    for row in reviews:
        brand = row["brand"].strip()
        if row["product_id"] not in product_by_id:
            raise ValueError(f"评论 {row['review_id']} 引用了未知 product_id {row['product_id']}")
        if product_by_id[row["product_id"]]["brand"].strip() != brand:
            raise ValueError(f"评论 {row['review_id']} 的品牌与商品记录不一致")
        review_brands[brand].append(row)
        topics = [topic.strip() for topic in row["topics"].split(";") if topic.strip()]
        for topic in topics:
            product_topics[brand][topic] += 1
            all_topics[topic] += 1
            sentiment_topics[brand][topic][row["sentiment"].strip().lower()] += 1

    if set(brands) != set(review_brands):
        raise ValueError("实验3与实验4品牌范围不一致")
    return brands, product_by_id, product_brands, review_brands, product_topics, product_prices, product_families, sentiment_topics, all_topics


def make_brand_summaries(brands, product_brands, review_brands):
    totals = {
        field: sum(row[f"_{field}"] for rows in product_brands.values() for row in rows)
        for field in ("review_count", "likes", "favorites")
    }
    shares = {}
    for brand in brands:
        shares[brand] = {
            field: (sum(row[f"_{field}"] for row in product_brands[brand]) / totals[field] if totals[field] else 0.0)
            for field in totals
        }
    heat_share = {brand: sum(shares[brand].values()) / len(totals) * 100.0 for brand in brands}
    max_heat = max(heat_share.values(), default=0.0)
    heat_index = {brand: 100.0 * value / max_heat if max_heat else 0.0 for brand, value in heat_share.items()}

    rows = []
    for brand in brands:
        products = product_brands[brand]
        reviews = review_brands[brand]
        product_ratings = [row["_rating"] for row in products if row["_rating"] is not None]
        positive = sum(row["sentiment"].strip().lower() == "positive" for row in reviews)
        negative = sum(row["sentiment"].strip().lower() == "negative" for row in reviews)
        top_topic = Counter()
        for row in reviews:
            if row["sentiment"].strip().lower() == "negative":
                top_topic.update(topic.strip() for topic in row["topics"].split(";") if topic.strip())
        rows.append({
            "brand": brand,
            "product_count": len(products),
            "review_count": len(reviews),
            "avg_price": rounded(sum(row["_price"] for row in products) / len(products)),
            "min_price": rounded(min(row["_price"] for row in products)),
            "max_price": rounded(max(row["_price"] for row in products)),
            "avg_product_rating": rounded(sum(product_ratings) / len(product_ratings)) if product_ratings else "",
            "product_rating_n": len(product_ratings),
            "missing_product_rating_n": len(products) - len(product_ratings),
            "review_avg_rating": rounded(sum(number(row["rating"], f"{row['review_id']}.rating") for row in reviews) / len(reviews)),
            "negative_reviews": negative,
            "negative_review_pct": rounded(100.0 * negative / len(reviews) if reviews else 0.0),
            "top_negative_topic": top_topic.most_common(1)[0][0] if top_topic else "",
            "review_count_share_pct": rounded(100.0 * shares[brand]["review_count"]),
            "likes_share_pct": rounded(100.0 * shares[brand]["likes"]),
            "favorites_share_pct": rounded(100.0 * shares[brand]["favorites"]),
            "brand_heat_share_pct": rounded(heat_share[brand]),
            "brand_heat_index": rounded(heat_index[brand]),
        })
    return rows, heat_share, heat_index


def pair_score(target: str, rival: str, consumer, product, price, heat_index, weights):
    parts = {
        "consumer": consumer,
        "product": product,
        "price": price,
        "heat": heat_index[rival],
    }
    return sum(parts[key] * weights[key] / 100.0 for key in parts), parts


def build_pairs(brands, product_topics, product_families, product_prices, heat_index, weights):
    pair_rows = []
    pair_factors = {}
    for target in brands:
        for rival in brands:
            if target == rival:
                continue
            consumer = share_overlap(product_topics[target], product_topics[rival], sum(product_topics[target].values()), sum(product_topics[rival].values()))
            product = share_overlap(product_families[target], product_families[rival], sum(product_families[target].values()), sum(product_families[rival].values()))
            price = share_overlap(product_prices[target], product_prices[rival], sum(product_prices[target].values()), sum(product_prices[rival].values()))
            score, parts = pair_score(target, rival, consumer, product, price, heat_index, weights)
            pair_factors[(target, rival)] = parts
            pair_rows.append({
                "target_brand": target,
                "competitor_brand": rival,
                "threat_index": rounded(score),
                "consumer_overlap_pct": rounded(consumer),
                "product_overlap_pct": rounded(product),
                "price_overlap_pct": rounded(price),
                "competitor_heat_index": rounded(heat_index[rival]),
                "consumer_weight_pct": weights["consumer"],
                "product_weight_pct": weights["product"],
                "price_weight_pct": weights["price"],
                "heat_weight_pct": weights["heat"],
            })
    pair_rows.sort(key=lambda row: (-row["threat_index"], row["target_brand"], row["competitor_brand"]))
    for rank, row in enumerate(pair_rows, 1):
        row["rank"] = rank
    return pair_rows, pair_factors


def build_topic_rows(brands, review_brands, sentiment_topics, all_topics):
    rows = []
    scopes = [("全样本", None)] + [(brand, brand) for brand in brands]
    for scope_name, brand in scopes:
        for topic in all_topics:
            if brand is None:
                counts = Counter()
                for one_brand in brands:
                    counts.update(sentiment_topics[one_brand][topic])
            else:
                counts = sentiment_topics[brand][topic]
            mentions = sum(counts.values())
            negative = counts["negative"]
            evidence_ids = []
            for one_brand in (brands if brand is None else [brand]):
                for review in review_brands[one_brand]:
                    if topic in [value.strip() for value in review["topics"].split(";") if value.strip()] and review["sentiment"].strip().lower() == "negative":
                        evidence_ids.append(review["review_id"])
                        if len(evidence_ids) == 5:
                            break
                if len(evidence_ids) == 5:
                    break
            rows.append({
                "scope": scope_name,
                "brand": brand or "",
                "topic": topic,
                "mentions": mentions,
                "positive_mentions": counts["positive"],
                "neutral_mentions": counts["neutral"],
                "negative_mentions": negative,
                "negative_share_pct": rounded(100.0 * negative / mentions if mentions else 0.0),
                "evidence_review_ids": ";".join(evidence_ids),
            })
    rows.sort(key=lambda row: (0 if row["scope"] == "全样本" else 1, -row["negative_mentions"], row["scope"], row["topic"]))
    return rows


def build_evidence_rows(brands, review_brands, product_by_id, trace_rows):
    trace = {row["review_id"]: row for row in trace_rows if row.get("review_id")}
    rows = []
    for brand in brands:
        for review in review_brands[brand]:
            product = product_by_id[review["product_id"]]
            trace_row = trace.get(review["review_id"], {})
            for topic in [value.strip() for value in review["topics"].split(";") if value.strip()]:
                rows.append({
                    "review_id": review["review_id"],
                    "product_id": review["product_id"],
                    "product_name": product["product_name"],
                    "brand": brand,
                    "topic": topic,
                    "sentiment": review["sentiment"],
                    "rating": review["rating"],
                    "evidence_quote": review["evidence_quote"],
                    "source": review["source"],
                    "simulated": review["simulated"],
                    "verification_status": trace_row.get("verification_status", "待人工复核"),
                    "traceability_claim": trace_row.get("claim", ""),
                })
    return rows


def build_sensitivity(brands, product_topics, product_families, product_prices, heat_index, baseline_pairs):
    baseline_rank = {(row["target_brand"], row["competitor_brand"]): row["rank"] for row in baseline_pairs}
    rows = []
    summary = []
    for scenario, weights in WEIGHT_SCENARIOS.items():
        scenario_pairs, _ = build_pairs(brands, product_topics, product_families, product_prices, heat_index, weights)
        best = scenario_pairs[0]
        summary.append({"scenario": scenario, "weights": weights, "top_pair": best, "top_pair_stable": (best["target_brand"], best["competitor_brand"]) == (baseline_pairs[0]["target_brand"], baseline_pairs[0]["competitor_brand"])})
        for row in scenario_pairs:
            key = (row["target_brand"], row["competitor_brand"])
            rows.append({
                "scenario": scenario,
                "weights": f"消费者{weights['consumer']}%/产品{weights['product']}%/价格{weights['price']}%/品牌热度{weights['heat']}%",
                "target_brand": row["target_brand"],
                "competitor_brand": row["competitor_brand"],
                "threat_index": row["threat_index"],
                "rank": row["rank"],
                "baseline_rank": baseline_rank[key],
                "rank_delta_vs_baseline": row["rank"] - baseline_rank[key],
            })
    return rows, summary


def metric_dictionary_rows():
    return [
        {"指标": "消费者重合度", "权重": "30%", "定义与计算": "实验4按品牌统计各评论主题标签的提及占比；跨品牌取各主题占比的较小值之和 × 100。", "范围": "0-100，越高表示表达出的需求主题结构越接近。", "来源": "reviews_encoded.csv: brand, topics"},
        {"指标": "产品重合度", "权重": "25%", "定义与计算": "从 product_name 中移除品牌前缀得到产品系列；按系列统计商品占比，取两品牌各系列占比较小值之和 × 100。", "范围": "0-100，越高表示产品系列组合越相似。", "来源": "clean_data.csv: product_name, brand"},
        {"指标": "价格重合度", "权重": "20%", "定义与计算": "按 <100、100-199、200-399、400+ 元四档统计商品价格结构；取两品牌各档商品占比较小值之和 × 100。", "范围": "0-100，越高表示价格带布局越相似。", "来源": "clean_data.csv: price, brand"},
        {"指标": "品牌热度指数", "权重": "25%", "定义与计算": "review_count、likes、favorites 分别计算品牌在四品牌样本中的份额，三项份额等权平均为热度份额；最高品牌归一为100，其余按比例缩放。", "范围": "0-100，相对本样本热度最高品牌；非市场份额。", "来源": "clean_data.csv: review_count, likes, favorites"},
        {"指标": "竞争威胁指数", "权重": "-", "定义与计算": "针对目标品牌与单一竞品：消费者重合×30% + 产品重合×25% + 价格重合×20% + 竞品品牌热度指数×25%。", "范围": "0-100，越高表示样本内潜在竞争接近度越高；不等于因果概率或真实市场份额。", "来源": "以上四项；按有向品牌对计算"},
    ]


def html_table(rows: list[dict], columns: list[tuple[str, str]], row_limit: int | None = None) -> str:
    shown = rows if row_limit is None else rows[:row_limit]
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key, _ in columns) + "</tr>" for row in shown)
    return f"<div class=table-wrap><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def build_dashboard(brand_rows, pair_rows, topic_rows, sensitivity_summary, prices_by_brand, family_counts, product_count, min_price, max_price, review_count):
    worst_topics = [row for row in topic_rows if row["scope"] == "全样本"]
    worst_topics.sort(key=lambda row: (-row["negative_share_pct"], -row["negative_mentions"]))
    target_pair = pair_rows[0]
    brand_table = html_table(brand_rows, [
        ("brand", "品牌"), ("product_count", "商品数"), ("review_count", "评论数"),
        ("avg_price", "均价（元）"), ("brand_heat_index", "热度指数"),
        ("negative_review_pct", "负向评论占比%"), ("top_negative_topic", "主要负向主题"),
    ])
    pair_table = html_table(pair_rows, [
        ("rank", "排名"), ("target_brand", "目标品牌"), ("competitor_brand", "竞品"),
        ("threat_index", "威胁指数"), ("consumer_overlap_pct", "消费者重合%"),
        ("product_overlap_pct", "产品重合%"), ("price_overlap_pct", "价格重合%"),
        ("competitor_heat_index", "竞品热度"),
    ])
    topic_bars = "".join(
        f"<div class=bar-row><div class=bar-label><span>{html.escape(row['topic'])}</span><span>{row['negative_share_pct']:.2f}% · {row['negative_mentions']}/{row['mentions']}</span></div>"
        f"<div class=track><div class=fill style=width:{row['negative_share_pct']:.2f}%></div></div></div>"
        for row in worst_topics
    )
    price_lines = []
    bands = [label for label, _, _ in PRICE_BANDS]
    for brand, counts in prices_by_brand.items():
        total = sum(counts.values()) or 1
        segments = "".join(f"<span title='{html.escape(band)}: {counts[band]} 件' style='width:{100*counts[band]/total:.2f}%;background:{color}'></span>" for band, color in zip(bands, ("#dd6b20", "#148a78", "#3976ad", "#a34c67")))
        legend = " · ".join(f"{band}: {counts[band]}" for band in bands)
        price_lines.append(f"<div class=price-row><strong>{html.escape(brand)}</strong><div class=stack>{segments}</div><small>{html.escape(legend)}</small></div>")
    sensitivity_rows = []
    for item in sensitivity_summary:
        best = item["top_pair"]
        sensitivity_rows.append({
            "scenario": item["scenario"],
            "top_pair": f"{best['competitor_brand']} → {best['target_brand']}",
            "threat_index": best["threat_index"],
            "stable": "是" if item["top_pair_stable"] else "否",
        })
    sensitivity_table = html_table(sensitivity_rows, [("scenario", "权重情景"), ("top_pair", "排名第一竞品 → 目标"), ("threat_index", "威胁指数"), ("stable", "与基准首位一致")])
    family_summary = "；".join(f"{html.escape(name)} {sum(count.values())}件" for name, count in family_counts.items())
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>竞品情报 Dashboard v0.5</title>
<style>
:root{{--ink:#182b3a;--muted:#526575;--line:#d8e1e7;--paper:#fff;--canvas:#f2f6f5;--teal:#147d72;--blue:#3976ad;--orange:#d97732;--rose:#a34c67}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.55 "Segoe UI","Microsoft YaHei",sans-serif}}main{{max-width:1320px;margin:auto;padding:28px 22px 44px}}header{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:20px}}h1{{font-size:26px;margin:0 0 5px}}h2{{font-size:17px;margin:0 0 14px}}p{{margin:5px 0;color:var(--muted)}}.version{{font-weight:700;color:var(--teal)}}.notice{{background:#fff4e7;border-left:4px solid var(--orange);padding:11px 14px;margin:16px 0 20px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0 22px}}.metric{{background:var(--paper);border:1px solid var(--line);padding:14px 16px;min-height:94px}}.metric span{{display:block;color:var(--muted);font-size:12px}}.metric strong{{font-size:24px;display:block;margin-top:5px}}.metric small{{color:var(--muted)}}section{{padding:20px 0;border-top:1px solid var(--line)}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:var(--paper);font-size:13px}}th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}th{{background:#203c50;color:#fff;font-weight:600}}tbody tr:nth-child(even){{background:#f8faf9}}.bar-row{{margin:12px 0}}.bar-label{{display:flex;justify-content:space-between;gap:16px;font-size:13px;margin-bottom:5px}}.track{{height:8px;background:#e5ecea}}.fill{{height:100%;background:var(--rose)}}.price-row{{display:grid;grid-template-columns:90px 1fr;align-items:center;gap:8px;margin:11px 0}}.price-row small{{grid-column:2;color:var(--muted)}}.stack{{display:flex;height:14px;overflow:hidden;background:#edf1f0}}.stack span{{display:block;height:100%}}.callout{{padding:14px;border:1px solid var(--line);background:#fff}}.callout strong{{color:var(--teal)}}.legend{{font-size:12px;color:var(--muted);margin-top:12px}}footer{{border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:12px;margin-top:24px}}@media(max-width:760px){{main{{padding:20px 14px}}header{{display:block}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.columns{{grid-template-columns:1fr;gap:8px}}h1{{font-size:22px}}}}
</style></head><body><main>
<header><div><h1>竞争情报分析引擎</h1><p>蓝牙耳机品类 · 有向竞品威胁评估</p></div><div class=version>实验五 · v0.5</div></header>
<div class=notice><strong>数据边界：</strong>基于实验3的 {len(sum((list(v) for v in prices_by_brand.values()), [])) if False else '320'} 条模拟商品记录与实验4的 {review_count} 条合成评论 / 规则标签，不代表真实平台市场、消费者总体或市场份额。威胁指数是可复算的相对比较分，不是因果概率。</div>
<div class=grid><div class=metric><span>商品样本</span><strong>320</strong><small>四个模拟品牌</small></div><div class=metric><span>评论样本</span><strong>{review_count}</strong><small>实验4编码结果</small></div><div class=metric><span>最高威胁配对</span><strong>{html.escape(target_pair['competitor_brand'])} → {html.escape(target_pair['target_brand'])}</strong><small>指数 {target_pair['threat_index']}/100</small></div><div class=metric><span>样本价格区间</span><strong>¥{min_price:.0f}–{max_price:.0f}</strong><small>商品标价</small></div></div>
<section><h2>竞品画像</h2>{brand_table}</section>
<section><h2>威胁指数排名</h2><p>每一行表示竞品对目标品牌的有向威胁；权重为消费者30%、产品25%、价格20%、竞品热度25%。</p>{pair_table}</section>
<section class=columns><div><h2>负向主题信号</h2><p>显示主题标签中负向提及占比；分母为该主题全部提及数。</p>{topic_bars}</div><div><h2>各品牌价格带结构</h2>{''.join(price_lines)}<div class=legend>颜色顺序：&lt;100、100-199、200-399、400+ 元。商品系列样本：{family_summary}</div></div></section>
<section><h2>敏感性检查</h2>{sensitivity_table}<p>首位配对随权重情景变化时，应将结论视为依赖权重设定，优先核验底层证据。</p></section>
<section><div class=callout><strong>样本解释：</strong>商品品类字段仅有“蓝牙耳机”，因此产品重合度按型号系列组合计算；消费者重合度比较评论主题构成，不代表个体消费者交叉购买。负向率和热度指标仅描述模拟样本。</div></section>
<footer>生成文件：reports/competitor_pairs.csv、reports/brand_summary.csv、reports/topic_metrics.csv、reports/sensitivity_analysis.csv、reports/evidence_table.csv。详细定义与限制见 docs/metric_dictionary.csv、docs/method_and_limitations.md。</footer>
</main></body></html>"""


def generate_report(brand_rows, pair_rows, topic_rows, sensitivity_summary, evidence_rows, products, reviews, source_trace_count):
    top = pair_rows[0]
    top_topics = [row for row in topic_rows if row["scope"] == "全样本"]
    top_topics.sort(key=lambda row: (-row["negative_share_pct"], -row["negative_mentions"]))
    top_topic = max(top_topics, key=lambda row: (row["negative_mentions"], row["negative_share_pct"]))
    highest_neg = max(top_topics, key=lambda row: (row["negative_share_pct"], row["negative_mentions"]))
    stable_count = sum(item["top_pair_stable"] for item in sensitivity_summary)
    avg_rating = sum(number(row["rating"], "review.rating") for row in reviews) / len(reviews)
    min_price = min(number(row["price"], "product.price") for row in products)
    max_price = max(number(row["price"], "product.price") for row in products)
    brand_table = "\n".join(
        f"| {row['brand']} | {row['product_count']} | {row['review_count']} | {row['avg_price']:.2f} | {row['brand_heat_index']:.2f} | {row['negative_review_pct']:.2f}% | {row['top_negative_topic']} |"
        for row in brand_rows
    )
    scenario_table = "\n".join(
        f"| {item['scenario']} | {item['weights']['consumer']}/{item['weights']['product']}/{item['weights']['price']}/{item['weights']['heat']} | {item['top_pair']['competitor_brand']} → {item['top_pair']['target_brand']} | {item['top_pair']['threat_index']:.2f} | {'是' if item['top_pair_stable'] else '否'} |"
        for item in sensitivity_summary
    )
    topic_table = "\n".join(
        f"| {row['topic']} | {row['mentions']} | {row['negative_mentions']} | {row['negative_share_pct']:.2f}% | {row['evidence_review_ids']} |"
        for row in sorted(top_topics, key=lambda row: (-row["negative_mentions"], row["topic"]))
    )
    return f"""# 实验五：竞争情报分析报告 v0.5

## 结论摘要

在当前模拟样本和基准权重下，威胁指数最高的有向配对是 **{top['competitor_brand']} → {top['target_brand']}**，指数 **{top['threat_index']:.2f}/100**。消费者重合度 {top['consumer_overlap_pct']:.2f}、产品系列重合度 {top['product_overlap_pct']:.2f}、价格带重合度 {top['price_overlap_pct']:.2f}，竞品热度指数 {top['competitor_heat_index']:.2f}。这是样本内相对接近程度，不足以证明真实市场中的竞争强度。

主题层面，**{top_topic['topic']}** 负向提及最多（{top_topic['negative_mentions']}/{top_topic['mentions']}）；**{highest_neg['topic']}** 的负向占比最高（{highest_neg['negative_share_pct']:.2f}%，分母 {highest_neg['mentions']} 条主题提及）。建议将连接稳定性与降噪体验作为优先验证方向。证据来自模拟评论，须先人工核验后才能用于产品决策。

## 数据范围与质量

- 实验3商品表：{len(products)} 条，{len(brand_rows)} 个品牌，品类字段为蓝牙耳机。
- 实验4评论表：{len(reviews)} 条，平均评分 {avg_rating:.2f}/5；全部记录均标为模拟数据，主题来自透明关键词规则。
- 商品样本价格范围：¥{min_price:.0f}–¥{max_price:.0f}。样本中没有低于 ¥{min_price:.0f} 的商品，属于样本覆盖空档，不等于市场需求已被证实。
- 实验4已有可追溯证据记录 {source_trace_count} 条；本报告证据表扩展为 {len(evidence_rows)} 条“评论-主题”明细，可由 review_id 回查原始模拟评论。
- 样本不是概率抽样。各品牌评论条数、评论量、点赞和收藏都不能解释为平台份额或真实消费者偏好。

## 品牌画像

| 品牌 | 商品数 | 评论数 | 均价（元） | 热度指数 | 负向评论占比 | 主要负向主题 |
|---|---:|---:|---:|---:|---:|---|
{brand_table}

热度指数由商品评论量、点赞量和收藏量的品牌样本份额等权形成，再按样本最高品牌归一为100。均价与热度不构成销量估计。

## 竞争配对判断

基准威胁指数：消费者重合度×30% + 产品重合度×25% + 价格重合度×20% + 竞品品牌热度指数×25%。所有不同品牌组合均按有向配对计算，未指定任何品牌为“我方”；竞品 → 目标表示威胁方向。

完整 12 组排名见 `competitor_pairs.csv`。因四品牌品类字段相同，产品重合组件依据品牌前缀剥离后的型号系列组合计算，避免单一品类字段导致所有品牌得分相同。

## 主题证据与机会假设

| 主题 | 提及数 | 负向提及 | 负向占比 | 样例证据ID |
|---|---:|---:|---:|---|
{topic_table}

**事实：**以上是规则编码后的模拟评论计数与比例；主题负向率的分母为该主题全部提及数，而非全部评论数。证据原文、商品、标签、情感和复核状态见 `evidence_table.csv`。

**推断：**连接和降噪等高频负向主题提示，可将连接稳定性、噪声抑制体验作为产品验证候选方向。样本未覆盖真实购买情境，且关键词规则可能误判，不能据此认定因果或总体痛点。

**机会假设：**当前商品样本最低价格为 ¥{min_price:.0f}，以下价格段未覆盖；可作为下一轮市场调研的待验证细分，不直接视为已确认的市场空白。品类字段单一，现有数据无法支持跨品类机会判断。

## 敏感性检查

下表改变四项权重但保持总和为100%，观察第一名有向配对是否改变。权重顺序为消费者/产品/价格/品牌热度。{stable_count}/{len(sensitivity_summary)} 个情景与基准首位一致；若不稳定，应在结论中同时报告权重依赖，并优先做人工复核或补充数据。

| 情景 | 权重（%） | 第一名配对 | 指数 | 与基准首位一致 |
|---|---:|---|---:|---|
{scenario_table}

## 建议

1. 先按 `evidence_table.csv` 中的 review_id 抽查连接、降噪主题原文，记录误判和复核者，再考虑调整关键词规则。
2. 将威胁指数用于筛选访谈或商品对比对象，不把它用作销量、份额或竞争因果结论。
3. 若要判断市场空白，补入有来源和采样框的授权真实评论、规格参数、成交价及样本时间，并将真实数据与模拟数据分开保存。

## 可复算文件

- `../src/competitive_intelligence.py`：指标计算和文件生成逻辑。
- `competitor_pairs.csv`：基准权重下 12 组有向竞品排名。
- `brand_summary.csv`、`topic_metrics.csv`、`price_band_distribution.csv`：品牌、主题和价格带统计。
- `sensitivity_analysis.csv`：各配对在五种权重情景下的排名和名次变化。
- `evidence_table.csv`：按评论主题展开的证据明细。
- `../dashboard/competitive_dashboard.html`：离线可打开的竞品 Dashboard。

生成版本：v0.5。数据源、行数及文件摘要见 `run_manifest.json`。
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(input_dir: Path, output_dir: Path, dashboard_path: Path, root: Path) -> None:
    product_path = input_dir / "clean_data.csv"
    review_path = input_dir / "reviews_encoded.csv"
    trace_path = input_dir / "evidence_traceability.csv"
    products, reviews, trace_rows = read_csv(product_path), read_csv(review_path), read_csv(trace_path)
    if not products or not reviews:
        raise ValueError("输入 CSV 不得为空")
    missing_product = REQUIRED_PRODUCT_FIELDS - set(products[0])
    missing_review = REQUIRED_REVIEW_FIELDS - set(reviews[0])
    if missing_product or missing_review:
        raise ValueError(f"输入字段不符合要求，商品缺少 {sorted(missing_product)}，评论缺少 {sorted(missing_review)}")
    review_ids = [row["review_id"] for row in reviews]
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("reviews_encoded.csv 存在重复 review_id")
    if any(row["simulated"].strip().lower() != "true" for row in reviews):
        raise ValueError("发现非模拟评论；此版本只接受实验4模拟数据，避免数据来源混合")

    (brands, product_by_id, product_brands, review_brands, product_topics,
     product_prices, product_families, sentiment_topics, all_topics) = brand_counts(products, reviews)
    brand_rows, heat_share, heat_index = make_brand_summaries(brands, product_brands, review_brands)
    weights = WEIGHT_SCENARIOS["基准权重"]
    pair_rows, _ = build_pairs(brands, product_topics, product_families, product_prices, heat_index, weights)
    topic_rows = build_topic_rows(brands, review_brands, sentiment_topics, all_topics)
    evidence_rows = build_evidence_rows(brands, review_brands, product_by_id, trace_rows)
    sensitivity_rows, sensitivity_summary = build_sensitivity(brands, product_topics, product_families, product_prices, heat_index, pair_rows)

    metric_rows = metric_dictionary_rows()
    write_csv(output_dir / "brand_summary.csv", brand_rows, list(brand_rows[0]))
    write_csv(output_dir / "competitor_pairs.csv", pair_rows, list(pair_rows[0]))
    write_csv(output_dir / "topic_metrics.csv", topic_rows, list(topic_rows[0]))
    write_csv(output_dir / "evidence_table.csv", evidence_rows, list(evidence_rows[0]))
    write_csv(output_dir / "sensitivity_analysis.csv", sensitivity_rows, list(sensitivity_rows[0]))
    write_csv(root / "docs" / "metric_dictionary.csv", metric_rows, list(metric_rows[0]))

    price_rows = []
    for brand in brands:
        total = len(product_brands[brand])
        for label, _, _ in PRICE_BANDS:
            count = product_prices[brand][label]
            price_rows.append({"brand": brand, "price_band": label, "product_count": count, "share_pct": rounded(100 * count / total if total else 0)})
    write_csv(output_dir / "price_band_distribution.csv", price_rows, list(price_rows[0]))

    family_rows = []
    for brand in brands:
        total = len(product_brands[brand])
        for family, count in product_families[brand].most_common():
            family_rows.append({"brand": brand, "product_family": family, "product_count": count, "share_pct": rounded(100 * count / total if total else 0)})
    write_csv(output_dir / "product_family_distribution.csv", family_rows, list(family_rows[0]))

    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    prices_by_brand = {brand: product_prices[brand] for brand in brands}
    min_price = min(row["_price"] for rows in product_brands.values() for row in rows)
    max_price = max(row["_price"] for rows in product_brands.values() for row in rows)
    dashboard = build_dashboard(brand_rows, pair_rows, topic_rows, sensitivity_summary, prices_by_brand, product_families, len(products), min_price, max_price, len(reviews))
    dashboard = dashboard.replace("320 条模拟商品记录", f"{len(products)} 条模拟商品记录")
    dashboard = dashboard.replace("<strong>320</strong>", f"<strong>{len(products)}</strong>")
    dashboard_path.write_text(dashboard, encoding="utf-8")
    (output_dir / "conclusion_report.md").write_text(generate_report(brand_rows, pair_rows, topic_rows, sensitivity_summary, evidence_rows, products, reviews, len(trace_rows)), encoding="utf-8")

    input_manifest = []
    for name, path in (("clean_data.csv", product_path), ("reviews_encoded.csv", review_path), ("evidence_traceability.csv", trace_path)):
        try:
            relative = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            relative = str(path.resolve())
        input_manifest.append({"file": name, "path": relative, "rows": len(read_csv(path)), "sha256": sha256(path)})
    manifest = {
        "version": "0.5",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "deterministic aggregate metrics over experiment 3 synthetic product data and experiment 4 synthetic review labels",
        "brand_order": brands,
        "weights_pct": weights,
        "price_bands": [label for label, _, _ in PRICE_BANDS],
        "input_files": input_manifest,
        "counts": {
            "products": len(products), "reviews": len(reviews), "brands": len(brands),
            "review_topic_evidence_rows": len(evidence_rows), "source_traceability_rows": len(trace_rows),
            "directed_competitor_pairs": len(pair_rows), "weight_scenarios": len(WEIGHT_SCENARIOS),
        },
        "limits": [
            "商品和评论均为模拟数据，不代表真实市场总体或平台份额。",
            "消费者主题由实验4透明关键词规则编码，需人工抽检。",
            "竞争威胁指数为规则加权的相对筛选指标，不是因果估计。",
        ],
        "outputs": [
            "reports/brand_summary.csv", "reports/competitor_pairs.csv", "reports/topic_metrics.csv",
            "reports/evidence_table.csv", "reports/sensitivity_analysis.csv", "reports/price_band_distribution.csv",
            "reports/product_family_distribution.csv", "reports/conclusion_report.md",
            "docs/metric_dictionary.csv", "dashboard/competitive_dashboard.html",
        ],
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {len(products)} 条商品、{len(reviews)} 条评论、{len(pair_rows)} 组配对和 {len(evidence_rows)} 条主题证据。")
    print(f"首位配对: {pair_rows[0]['competitor_brand']} -> {pair_rows[0]['target_brand']} ({pair_rows[0]['threat_index']:.2f}/100)")
    print(f"报告: {output_dir / 'conclusion_report.md'}")
    print(f"Dashboard: {dashboard_path}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="生成实验五竞争情报分析结果（v0.5）")
    parser.add_argument("--input-dir", type=Path, default=root / "data" / "input", help="实验3/4输入 CSV 目录")
    parser.add_argument("--output-dir", type=Path, default=root / "reports", help="报告与统计 CSV 输出目录")
    parser.add_argument("--dashboard", type=Path, default=root / "dashboard" / "competitive_dashboard.html", help="离线 Dashboard 输出文件")
    args = parser.parse_args()
    run(args.input_dir.resolve(), args.output_dir.resolve(), args.dashboard.resolve(), root)


if __name__ == "__main__":
    main()
