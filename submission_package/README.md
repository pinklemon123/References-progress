# 三问程序、正式结果与复核材料

论文正式结果仅以本目录根部的三个文件为准：

- `result1.xlsx`
- `result2.xlsx`
- `result3.xlsx`

三个文件由 `reproduce_all.py` 根据已验证 JSON 和赛题原始五列模板生成，只包含
`UAV ID` 与逐次巡检点编号。`question1-3/results` 中的 JSON/CSV 以及
`audit_materials` 中的扩展工作簿用于复核，不作为赛题模板结果文件。

```text
submission_package/
├─ reproduce_all.py          一键校验并生成三个正式结果文件
├─ formal_excel.py           官方模板填表与逐格回读核对
├─ 运行说明.md               Windows 环境和复现命令
├─ requirements.txt          快速复核所需依赖
├─ requirements-search.txt   重新搜索所需附加依赖
├─ templates/                赛题给定的三个原始空模板
├─ audit_materials/          旧版扩展工作簿和历史中间结果
├─ question1/
│  ├─ program/               问题一算法、输入、测试与校验器
│  └─ results/               正式 solution.json 和搜索报告
├─ question2/
│  ├─ program/               固定问题一 N、Tmax 上界的均衡程序
│  └─ results/               正式 JSON、CSV 和路线明细
└─ question3/
   ├─ program/               算法 A、算法 B 和独立验证器
   └─ results/               算法 B 正式 JSON、算法 A 对照 JSON/CSV
```

最快复现：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe reproduce_all.py
```

无需激活虚拟环境，也不要求 Python 3.12；支持 Python 3.10 以上版本。完整说明见
`运行说明.md`。

## 结果口径

- 问题一 Case4 正式值为 `Tmax=8.6263 h`、`Tmin=8.6058 h`。
- 问题二固定问题一的无人机数量和完成时间上界，主结果 `epsilon=0`。
- 问题三正式结果只取算法 B 的 `formal_fixed_N0`；算法 A 仅作对照，
  `N0+1`、`N0+2` 仅作敏感性分析。
- 校验通过只证明保存路线满足程序实现的约束，不等于证明全局最优。
