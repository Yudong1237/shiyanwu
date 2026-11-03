# 蓝牙耳机营销组：实验五 v0.5

竞争情报分析引擎，复用实验3商品表和实验4主题编码评论，输出可复算的竞品配对排名、证据表、敏感性检查、结论报告与离线 Dashboard。

## 目录

- `src/competitive_intelligence.py`：标准库实现，无第三方运行依赖。
- `data/input/`：实验3/4输入文件副本；原实验目录未修改。
- `docs/metric_dictionary.csv`：指标定义、公式、权重、来源。
- `docs/method_and_limitations.md`：方法说明、数据边界与复核要求。
- `reports/`：脚本生成的统计、证据、敏感性、报告和运行清单。
- `dashboard/competitive_dashboard.html`：可离线打开的单文件 Dashboard。
- `tests/`：指标基础测试。

## 运行

需要 Python 3.10 或更高版本。项目仅使用 Python 标准库。

```powershell
python src/competitive_intelligence.py
python -m unittest discover -s tests -v
```

自定义数据目录和输出目录：

```powershell
python src/competitive_intelligence.py --input-dir data/input --output-dir reports --dashboard dashboard/competitive_dashboard.html
```

## 主要结果

- `reports/conclusion_report.md`：提交版结论报告。
- `reports/competitor_pairs.csv`：12组有向竞品配对及四项评分分量。
- `reports/evidence_table.csv`：评论-主题粒度证据明细，保留 review_id 回链。
- `reports/sensitivity_analysis.csv`：基准与四种调整权重下的名次变化。
- `dashboard/competitive_dashboard.html`：浏览器可直接打开。

本项目输入的商品记录和评论均为模拟数据。不得将结果描述为真实平台市场份额、真实消费者总体偏好或因果结论。
