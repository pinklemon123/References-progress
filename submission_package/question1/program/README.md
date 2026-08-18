# 问题一：多无人机协同巡检路径优化程序

> 本整理版的最终结果位于相邻目录 `../results/`。可执行
> `python validate.py --solution ../results/solution.json` 独立复算。

本项目严格按照赛题的目标优先级求解：

1. 先求 9 小时内完成全部任务的最小可行无人机数量 $N_{\min}$；
2. 固定 $N=N_{\min}$，再使最长工作时间 $T_{\max}$ 尽可能短；
3. 不允许为了缩短时间而直接增加无人机数量。

重复巡检采用最终补充解释：到达并执行 5 分钟计一次；原地停留不重复计数；离开后返回可以再次计数；不同无人机同时巡检可分别计数。同一路线允许 `i -> j -> i`，禁止连续 `i -> i`。

## 1. 目录

```text
uav_q1_program/
├─ README.md
├─ requirements.txt
├─ environment.yml
├─ config.json
├─ run.py                         # 主程序
├─ validate.py                    # 独立结果校验
├─ setup_windows.ps1
├─ setup_linux.sh
├─ input/
│  ├─ 附件1.xlsx
│  └─ result1_template.xlsx
├─ data/
│  └─ precomputed_solution.json
├─ docs/
│  ├─ MODEL.md                    # 两阶段模型和完整 MILP
│  └─ ALGORITHM.md                # 搜索、证明状态和复现方法
├─ src/uav_q1/
│  ├─ solver_engine.py            # 多起点启发式
│  ├─ exact_milp.py               # 完整弧集精确 MILP
│  ├─ excel_output.py
│  └─ validation.py
├─ tests/
│  ├─ test_exact_small.py
│  └─ test_precomputed.py
└─ outputs/
   ├─ result1.xlsx
   └─ solution.json
```

## 2. 环境

- Windows 10/11、Linux 或 macOS；
- Python 3.10 以上，推荐 3.11/3.12；
- 普通 CPU，建议 8 GB 以上内存；
- 不需要 GPU；
- 主要依赖：NumPy、pandas、SciPy/HiGHS、scikit-learn、openpyxl。

Windows PowerShell：

```powershell
cd G:\uav_q1_program
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

若 PowerShell 禁止激活脚本，可先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Linux/macOS：

```bash
cd /path/to/uav_q1_program
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. 推荐运行方式

### 10 分钟 CPU 并行优化（推荐）

该模式先校验已有的 `4,2,5,4` 热启动方案，再按 `Case2 → Case4 → Case1 → Case3`
执行多进程随机起点搜索。Case2、Case4 位于严格数量下界，因而可确认最小无人机数；
Case1、Case3 保留为当前最优可行候选。搜索使用候选邻域和增量路线代价计算，暂不使用 GPU。

在项目目录的 PowerShell 中运行：

```powershell
$env:PYTHONUTF8 = "1"
$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
.\.venv\Scripts\python.exe run.py --mode ten-minute --total-time-limit 600 --workers 4 --candidate-k 24
```

终端会显示每个算例的进度条、已完成随机起点数、活动进程数、当前最优 `Tmax`
和累计耗时。结果单独保存到 `outputs_10min/`，不会覆盖原来的 `outputs/`：

- `solution.json`：完整路线与时间；
- `result1.xlsx`：完整调度表；
- `search_report.json`：严格下界、热启动值、每次改进、搜索耗时和最终校验状态。

`--workers` 建议从 4 开始。若电脑同时运行其他重负载程序，可改为 2；候选邻域一般保持
`--candidate-k 24`。程序采用全局时间预算并预留结果保存时间，单个正在执行的随机起点可能
使实际结束时间略微超过或短于 600 秒。

若要从上一次结果继续搜索而不是回到内置方案，可执行：

```powershell
.\.venv\Scripts\python.exe run.py --mode ten-minute --total-time-limit 240 --workers 4 --candidate-k 24 --resume-from .\outputs_10min\solution.json
```

续搜前会先独立校验指定 JSON；校验失败时不会启动搜索，也不会覆盖现有结果。

严格从理论下界开始，启发式找解，必要时用 MILP 判断：

```powershell
python run.py --mode solve --engine hybrid --quality thorough
```

程序对每个 Case 执行：

```text
计算 N 的理论下界
→ 从下界开始尝试 N
→ 启发式寻找 Tmax≤9 的方案
→ 搜索失败时调用完整 MILP
→ 只有 INFEASIBLE 才排除当前 N
→ 找到最小可行 N 后固定 N 优化 Tmax
→ 独立校验
→ 导出 outputs/result1.xlsx 和 outputs/solution.json
```

### 快速调试

```powershell
python run.py --mode solve --engine heuristic --quality fast
```

启发式搜索失败不等于不可行，因此这种模式得到的数量可能只是“当前找到的可行上界”。

### 精确模式

```powershell
python run.py --mode solve --engine exact
```

附件 1 展开后分别有 72、139、140、182 个任务副本，完整 MILP 可能耗时较长。可以在 `config.json` 修改：

```json
{
  "exact_time_limit_seconds": 300,
  "exact_mip_relative_gap": 0.0
}
```

达到时限且没有结论时状态为 `UNKNOWN`，不能写成“不存在可行路线”。

## 4. 复现已有可行解

```powershell
python run.py --mode reproduce
```

该模式读取已有路线、重新计算全部距离与时间、验证巡检次数和重复规则，并生成结果文件。已有的 `4,2,5,4` 结果是可行方案，不因复现通过就自动成为严格的 $N_{\min}$。

## 5. 求解状态

每个算例的 `solution.json` 会记录：

| 字段 | 含义 |
|---|---|
| `theoretical_lower_bound_N` | 数量的合法理论下界 |
| `N` | 当前找到的最小可行数量或候选 |
| `fleet_size_status` | 是否已经严格证明最小 |
| `makespan_status` | 固定 N 下的时间是否已证明最优 |
| `search_history` | 每个 N 的启发式最好值和精确状态 |

`fleet_size_status=PROVEN_MINIMUM` 只在两种情况下出现：

1. 理论下界处直接找到可行方案；
2. 所有更小的 N 均由完整模型证明 `INFEASIBLE`。

否则使用 `FEASIBLE_CANDIDATE`。

## 6. 独立校验

```powershell
python validate.py
```

校验内容包括：

- I、II、III 级点分别累计 3、2、1 次；
- 路线从基地出发并最终返回基地；
- 同一物理点不在同一路线连续出现；
- 距离按 1 单位 = 0.1 km 换算；
- 工作时间 = 飞行距离 / 55 + 巡检次数 × 5 / 60；
- 每条路线不超过 9 小时；
- 汇总的 $T_{\max}$、$T_{\min}$ 与逐条复算一致。

## 7. 测试

```powershell
python -m unittest discover -s tests -v
```

小规模测试会验证精确 MILP 的路线结构；预计算测试会验证已有四个算例的可行性。详细公式见 `docs/MODEL.md`，算法状态解释见 `docs/ALGORITHM.md`。
