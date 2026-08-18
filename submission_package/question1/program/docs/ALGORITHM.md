# 程序求解流程

## 1. 总体顺序

程序严格执行下面的字典序，而不是先挑一个较大的无人机数量压低时间：

```text
读取附件1
  ↓
计算合法理论下界 N_LB
  ↓
从 N=N_LB 开始逐个检验
  ├─ 找到 Tmax≤9 的路线：当前 N 是可行上界
  ├─ 精确模型证明 INFEASIBLE：N←N+1
  └─ 求解超时且无解：标记 UNKNOWN，再继续寻找上界
  ↓
确认或暂定 Nmin
  ↓
固定 N，不再增加无人机
  ↓
最小化 Tmax
  ↓
独立校验并导出 result1.xlsx
```

## 2. 快速启发式引擎

启发式引擎用于尽快给出可行上界和高质量路线：

1. K-means 或极角扫描产生多个空间划分初解；
2. 每个物理点先插入一次，再插入 I、II 级的额外任务副本；
3. 所有插入位置都检查“同物理点不能连续”；
4. 对单条路线使用 2-opt 缩短飞行距离；
5. 对路线之间执行单任务迁移和一对一交换；
6. 以 $T_{\max}$ 为接受标准，并使用少量模拟退火式劣解接受跳出局部最优；
7. 使用多个固定随机种子重复搜索，保留最小 $T_{\max}$。

启发式找到 $T_{\max}\le9$ 可以严格证明“当前 N 可行”，但搜索失败不能证明“当前 N 不可行”。

## 3. 精确 MILP 引擎

完整弧集 MILP 使用 SciPy 的 `optimize.milp`（底层 HiGHS）求解。它主要承担两项工作：

1. 当启发式在较小 N 下失败时，尝试给出 `INFEASIBLE` 证明；
2. 在计算规模允许时，证明固定 N 下 $T_{\max}$ 的最优性。

| 状态 | 含义 | 能否排除当前 N |
|---|---|---|
| `OPTIMAL` | 已得到并证明固定 N 下的最优解 | 否，当前 N 可行 |
| `FEASIBLE` | 时限内得到可行解，但未证明最优 | 否，当前 N 可行 |
| `INFEASIBLE` | 完整模型已证明无可行解 | 是 |
| `UNKNOWN` | 时限内没有结论 | 否 |

## 4. 三种运行模式

`hybrid`（推荐）先运行启发式；若没有找到 9 小时内方案，再调用精确 MILP：

```powershell
python run.py --mode search --engine hybrid --quality thorough
```

`heuristic` 只运行多起点启发式，速度快，但最终数量可能只是可行候选：

```powershell
python run.py --mode search --engine heuristic --quality thorough
```

`exact` 逐个 N 运行完整 MILP，适合较小算例或延长求解时间后进行证明：

```powershell
python run.py --mode search --engine exact
```

精确求解时限在 `config.json` 的 `exact_time_limit_seconds` 中设置。只有状态真正返回 `OPTIMAL` 时才能称为固定 N 下的全局最优。

## 5. 输出状态

`solution.json` 为每个 Case 保存：

- `theoretical_lower_bound_N`：合法理论下界；
- `N`：当前采用的最小可行数量或候选数量；
- `fleet_size_status`：`PROVEN_MINIMUM` 或 `FEASIBLE_CANDIDATE`；
- `makespan_status`：最长时间是否已证明最优；
- `search_history`：每个尝试过的 N、最好时间和精确求解状态；
- 每架无人机的路线、距离、服务次数和工作时间。

## 6. 重复性与验证

固定输入、环境、参数和随机种子后，可以重复得到同一实验过程。建议论文至少报告 20 个种子的最好值，并保留 `search_history`。

独立校验器不依赖优化过程，逐条检查：巡检次数、基地首尾、禁止连续同点、距离与时间复算、9 小时限制，以及 $T_{\max}$、$T_{\min}$ 汇总一致性。
