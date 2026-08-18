# 问题二：固定完成时间上界的无人机工作负载均衡

本程序读取问题一最终通过校验的 `solution.json`，固定各算例采用的无人机数量，并以问题一的 `Tmax` 为严格上界：

```text
min (delta, Tmax, sum(Tk))
s.t. N = N(问题一)
     Tmax(问题二) <= Tmax(问题一) + epsilon
     epsilon = 0（主结果）
     继承问题一全部任务分配和路径合法性约束
```

其中 `delta = Tmax - Tmin`。候选解采用重载路线向轻载路线的任务迁移、路线间任务交换、合法 2-opt、模拟退火和确定性精修。2-opt 只接受距离缩短操作；程序不设置等待变量，每架无人机的等待时间恒为 0，工作时间仅由飞行与有效巡检服务组成。

## 运行

```powershell
python q2_solver.py `
  --input ..\..\question1\program\input\附件1.xlsx `
  --q1-solution ..\..\question1\results\solution.json `
  --output-dir ..\results `
  --epsilon 0 `
  --seeds 8 `
  --iterations 30000 `
  --time-limit-per-case 45
```

独立复算已保存结果：

```powershell
python q2_solver.py `
  --input ..\..\question1\program\input\附件1.xlsx `
  --q1-solution ..\..\question1\results\solution.json `
  --output-dir ..\results `
  --validate-only
```

输出包括：

- `q2_solution.json`：完整路线、各架无人机时间和搜索记录；
- `summary.csv`：题目要求的汇总字段；
- `comparison.csv`：问题一、问题二工作时间极差对比；
- `CaseX_routes.csv`：逐架无人机路线；
- 正式 `result2.xlsx`：由提交包根目录的 `reproduce_all.py` 按赛题模板生成。
