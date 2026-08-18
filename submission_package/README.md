# 两问程序与结果目录

```text
submission_package/
├─ question1/
│  ├─ program/   问题一模型、算法、输入、测试与运行入口
│  └─ results/   本轮重新运行并独立校验的问题一结果
└─ question2/
   ├─ program/   固定问题一 N 和 Tmax 上界的均衡优化程序
   └─ results/   问题二 JSON、CSV、Excel 与路线明细
```

问题二只读取 `question1/results/solution.json`，不读取旧版 `Downloads/result2.xlsx`。两问的结果文件和程序文件相互分离。
