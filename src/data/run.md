# 运行指南

> 本文档只讲**怎么跑起来**：环境、依赖、命令、输出位置与执行顺序。
> 分析方法本身见 [README.md](README.md)。

---

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows / Linux / macOS（命令以 PowerShell 为例） |
| Python | 3.12 及以上（3.12 / 3.13 的预编译包最齐全） |
| 虚拟环境 | 项目根目录的 `.venv`（与系统 Python 隔离） |
| 内存 | ≥ 4 GB |
| GPU | 不需要，TensorFlow 以 CPU 模式运行 |

## 2. 一次性准备

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

基础依赖（`requirements.txt`）：

```text
numpy pandas matplotlib seaborn scipy statsmodels tabulate
scikit-learn mlxtend openpyxl missingno ruptures tensorflow
```

工程化主题另需两个库：

```powershell
pip install dask pandera -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 3. 运行命令

以下命令均在**项目根目录**执行，脚本内部使用相对路径定位数据库，不依赖当前目录。

### 3.1 数据探查

```powershell
python src/data/profiling/data_profiling_report.py
```

可选参数：

| 参数 | 说明 |
|---|---|
| `--db PATH` | 指定其他 SQLite 数据库 |
| `--tables a,b` | 只探查指定表，默认全部业务表 |

输出：

| 文件 | 面向 | 内容 |
|---|---|---|
| `src/data/profiling/data_profiling_report.md` | 数据团队 | 表级/字段级画像、一致性检查、建模就绪度 |
| `src/data/profiling/report_manager.html` | 数据管理者 | 资产健康度、风险与治理建议 |
| `src/data/profiling/report_analyst.html` | 数据分析师 | 字段质量、分布、建模资产 |
| `src/data/profiling/images/` | — | 报告引用图表 |

### 3.2 各层分析

```powershell
# L1 描述性：主报告 + 交叉/地理/文本专题
python src/data/L1/generate_report.py
python src/data/L1/l1_cross_analysis.py
python src/data/L1/l1_geo_analysis.py
python src/data/L1/l1_text_analysis.py

# L2 诊断性：主报告 + 因果/Granger/异常/聚类/序列专题
python src/data/L2/generate_diagnostic_report.py
python src/data/L2/l2_causal.py
python src/data/L2/l2_granger.py
python src/data/L2/l2_anomaly.py
python src/data/L2/l2_clustering.py
python src/data/L2/l2_sequence.py

# L3 预测性：主报告 + 集成/多步/分位数/迁移/SHAP 专题
python src/data/L3/generate_predictive_report.py
python src/data/L3/l3_ensemble.py
python src/data/L3/l3_multistep.py
python src/data/L3/l3_quantile.py
python src/data/L3/l3_transfer.py
python src/data/L3/l3_shap.py

# L4 规范性：主报告 + DQN/赌博机/多目标/因果推荐专题
python src/data/L4/generate_prescriptive_report.py
python src/data/L4/l4_dqn.py
python src/data/L4/l4_bandit.py
python src/data/L4/l4_multiobjective.py
python src/data/L4/l4_causal_rec.py

# L5 认知性：持续学习 / 元学习 / 多模态
python src/data/L5/l5_continual.py
python src/data/L5/l5_meta.py
python src/data/L5/l5_multimodal.py
```

每个脚本都会在所在目录生成对应的 `*_report.md` 与图片目录（`images*`）。

### 3.3 工程化

```powershell
python src/data/engineering/eng_distributed.py
python src/data/engineering/eng_ab_test.py
python src/data/engineering/eng_data_quality.py
```

### 3.4 数据生成与校验

```powershell
python src/data/ecommerce/generate_dataset.py --force   # 重新生成 ecommerce.db
python src/data/ecommerce/_verify.py                     # 外键、金额、分布校验
```

数据库由固定种子 42 与锚定日期 2025-06-15 生成，同一份代码在不同机器上产出一致结果。
注意：重新生成会改变随机流，所有下游报告的数字都需要重跑。

## 4. 执行顺序

```text
1. ecommerce/generate_dataset.py   → 生成数据库
2. profiling/data_profiling_report.py → 确认数据可用
3. L1 → L2 → L3 → L4 → L5          → 逐层分析（后层可复用前层产物）
4. engineering/*.py                → 工程化主题
```

单独重跑某一层时，只需保证 `ecommerce/ecommerce.db` 存在。

## 5. 输出约定

- 报告统一为 Markdown，图表统一为 PNG。
- 报告内的图片使用**相对路径**，可直接被文档工具与界面渲染。
- 每份报告开头注明数据来源与口径，结尾注明生成脚本。

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| 图表中文显示为方块 | 确认系统安装 SimHei 或 Microsoft YaHei；脚本会自动回退到可用字体 |
| TensorFlow 首次运行较慢 | 首次加载与 CPU 算子初始化耗时较长，属正常现象 |
| 内存不足 | 先跑探查与 L1；L3/L5 的深度学习脚本可减少 epoch 或减小窗口 |
| 报告数字与旧版本不一致 | 数据库被重新生成过，随机流变化会改变全部下游结果 |
| PowerShell 无法激活 venv | 执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 后重试 |

## 7. 说明性跳过

| 主题 | 原因 |
|---|---|
| Feast / Tecton 特征存储 | 需要常驻服务，Windows 支持有限，不适合脚本化示例 |
| MLflow / BentoML 模型部署 | 需要常驻 tracking server / API server，超出脚本范围 |
| 真实大模型 API 接入 | 环境无可用 API Key，L5 以可复现的本地方法等效演示 |
| 知识追踪（DKT/SAKT/AKT） | 教育领域专用技术，电商数据无“知识点-作答”概念 |
