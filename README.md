# References-progress

低空经济背景下的多无人机协同巡检路径优化论文、程序与可复核结果。

## 目录结构

- `main.tex`：当前论文主文件。
- `references.bib`：参考文献数据库。
- `figures/`：问题一流程图等论文图件。
- `generated_figures/`：问题二、问题三结果图和方法图。
- `submission_package/question1/`：问题一程序、输入与结果。
- `submission_package/question2/`：问题二程序与结果。
- `submission_package/question3/`：问题三算法 A、算法 B、独立验证器与结果。
- `submission_package/reproduce_all.py`：校验三问正式路线并按赛题模板生成三个结果文件。
- `submission_package/运行说明.md`：Windows 环境与复现说明。

## 问题三结果口径

- 正式结果采用算法 B，固定问题一最终采用的机队规模 `N0=(4,2,5,4)`。
- 算法 A 仅作为基准对照。
- `N0+1`、`N0+2` 结果仅用于机队规模敏感性分析。
- 12 组“算例 × 机队规模”结果均通过独立逐事件验证；这证明方案可行，不代表已经证明全局最优。

## 主要入口

```text
submission_package/question1/program/run.py
submission_package/question2/program/q2_solver.py
submission_package/question3/program/q3_solver.py
submission_package/question3/program/q3_solver_enhanced.py
submission_package/question3/program/q3_enhanced_validator.py
```

默认复现入口是 `submission_package/reproduce_all.py`。它不进行耗时的随机搜索，
而是独立校验保存路线并生成赛题模板格式的 `result1.xlsx`、`result2.xlsx`、
`result3.xlsx`。重新搜索属于可选操作，可能得到不同但同样可行的路线。

论文使用 XeLaTeX、BibTeX，并采用 `gbt7714-numerical` 参考文献样式。目录、文献和交叉引用需要多轮编译。
