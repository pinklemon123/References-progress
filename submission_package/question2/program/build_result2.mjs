import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [jsonPath, outputPath, previewDir] = process.argv.slice(2);
if (!jsonPath || !outputPath) {
  throw new Error("Usage: node build_result2.mjs q2_solution.json result2.xlsx [preview_dir]");
}

const results = JSON.parse(await fs.readFile(jsonPath, "utf8"));
const cases = Object.keys(results);
const workbook = Workbook.create();
const navy = "#1F4E78";
const blue = "#D9EAF7";
const pale = "#EEF5FA";
const green = "#E2F0D9";
const gray = "#666666";

function styleHeader(range) {
  range.format = {
    fill: navy,
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: "#A6A6A6" },
  };
}

function styleBody(range) {
  range.format = {
    verticalAlignment: "center",
    borders: {
      insideHorizontal: { style: "thin", color: "#D9E2F3" },
      bottom: { style: "thin", color: "#B4C6E7" },
    },
  };
}

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.mergeCells("A1:F1");
summary.getRange("A1").values = [["问题二：固定问题一完成时间上界的工作负载均衡结果"]];
summary.getRange("A1:F1").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["主结果取 ε=0；工作时间仅含实际飞行与有效巡检服务，等待时间恒为0。"]];
summary.getRange("A2:F2").format = { fill: pale, font: { color: gray }, wrapText: true };
summary.getRange("A4:F4").values = [["测试算例", "无人机数量 N", "Tmax (h)", "Tmin (h)", "δ=Tmax-Tmin (h)", "总工作时间 (h)"]];
styleHeader(summary.getRange("A4:F4"));

const summaryRows = cases.map((name) => {
  const r = results[name];
  return [name, r.N, r.Tmax, r.Tmin, null, r.total_work_h];
});
summary.getRange(`A5:F${4 + cases.length}`).values = summaryRows;
for (let row = 5; row < 5 + cases.length; row += 1) {
  summary.getRange(`E${row}`).formulas = [[`=C${row}-D${row}`]];
}
styleBody(summary.getRange(`A5:F${4 + cases.length}`));
summary.getRange(`B5:B${4 + cases.length}`).format.numberFormat = "0";
summary.getRange(`C5:F${4 + cases.length}`).format.numberFormat = "0.0000";

const comparisonStart = 11;
summary.getRange(`A${comparisonStart}:F${comparisonStart}`).values = [["测试算例", "问题一 δ (h)", "问题二 δ (h)", "极差下降量 (h)", "下降比例", "完成时间上界检查"]];
styleHeader(summary.getRange(`A${comparisonStart}:F${comparisonStart}`));
for (let index = 0; index < cases.length; index += 1) {
  const row = comparisonStart + 1 + index;
  const sourceRow = 5 + index;
  const r = results[cases[index]];
  summary.getRange(`A${row}:F${row}`).values = [[cases[index], r.q1_delta_h, null, null, null, null]];
  summary.getRange(`C${row}`).formulas = [[`=E${sourceRow}`]];
  summary.getRange(`D${row}`).formulas = [[`=B${row}-C${row}`]];
  summary.getRange(`E${row}`).formulas = [[`=IF(B${row}=0,0,D${row}/B${row})`]];
  summary.getRange(`F${row}`).formulas = [[`=IF(C${sourceRow}<=${r.q1_Tmax_h}+1E-8,"通过","未通过")`]];
}
styleBody(summary.getRange(`A${comparisonStart + 1}:F${comparisonStart + cases.length}`));
summary.getRange(`B${comparisonStart + 1}:D${comparisonStart + cases.length}`).format.numberFormat = "0.0000";
summary.getRange(`E${comparisonStart + 1}:E${comparisonStart + cases.length}`).format.numberFormat = "0.0%";
summary.getRange(`F${comparisonStart + 1}:F${comparisonStart + cases.length}`).format.fill = green;
summary.freezePanes.freezeRows(4);
summary.getRange("A1:F20").format.autofitColumns();
summary.getRange("A:A").format.columnWidth = 14;
summary.getRange("B:F").format.columnWidth = 19;
summary.getRange("A1:F20").format.autofitRows();

const notes = workbook.worksheets.add("Model_Notes");
notes.showGridLines = false;
notes.getRange("A1:B1").values = [["项目", "说明"]];
styleHeader(notes.getRange("A1:B1"));
notes.getRange("A2:B9").values = [
  ["固定数量", "各算例固定采用问题一最终方案的无人机数量，不重新搜索 N。"],
  ["完成时间保护", "Tmax(问题二) ≤ Tmax(问题一)+ε，主结果 ε=0。"],
  ["均衡指标", "δ=Tmax−Tmin，目标按 (δ,Tmax,总工作时间) 词典序比较。"],
  ["继承约束", "完整继承任务副本、基地出发返回、巡检次数、禁止同点连续巡检及9小时限制。"],
  ["搜索算子", "重载到轻载任务迁移、路线间交换、合法2-opt、模拟退火、多随机种子与确定性精修。"],
  ["无等待", "等待时间恒为0；工作时间仅由实际飞行时间和每次5分钟有效巡检服务构成。"],
  ["结果性质", "启发式算法当前找到的最好可行方案，不宣称已证明全局最优。"],
  ["校验", "JSON输出已由独立复算程序检查巡检次数、路线合法性、距离、时间、上界与9小时约束。"],
];
styleBody(notes.getRange("A2:B9"));
notes.getRange("A1:B9").format.wrapText = true;
notes.getRange("A:A").format.columnWidth = 20;
notes.getRange("B:B").format.columnWidth = 88;
notes.getRange("A1:B9").format.autofitRows();
notes.freezePanes.freezeRows(1);

for (const caseName of cases) {
  const result = results[caseName];
  const sheet = workbook.worksheets.add(caseName);
  sheet.showGridLines = false;
  const maxStops = Math.max(...result.routes.map((r) => r.sequence.length));
  const headers = ["UAV ID"];
  for (let i = 1; i <= maxStops; i += 1) headers.push(`${i}th Inspection Point`);
  headers.push("Flight Distance (km)", "Inspection Count", "Working Time (h)", "Waiting Time (h)");
  const lastCol = String.fromCharCode(65 + Math.min(headers.length - 1, 25));
  sheet.getRangeByIndexes(0, 0, 1, headers.length).values = [[...headers]];
  styleHeader(sheet.getRangeByIndexes(0, 0, 1, headers.length));
  const rows = result.routes.map((route) => {
    const padding = Array(maxStops - route.sequence.length).fill(null);
    return [route.uav, ...route.sequence, ...padding, route.distance_km, route.service_count, route.time_h, route.waiting_time_h];
  });
  sheet.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows;
  styleBody(sheet.getRangeByIndexes(1, 0, rows.length, headers.length));
  sheet.getRangeByIndexes(1, 1 + maxStops, rows.length, 1).format.numberFormat = "0.000";
  sheet.getRangeByIndexes(1, 2 + maxStops, rows.length, 1).format.numberFormat = "0";
  sheet.getRangeByIndexes(1, 3 + maxStops, rows.length, 2).format.numberFormat = "0.0000";
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).format.autofitColumns();
  sheet.getRangeByIndexes(0, 0, rows.length + 1, 1).format.columnWidth = 10;
  for (let col = 1; col <= maxStops; col += 1) {
    sheet.getRangeByIndexes(0, col, rows.length + 1, 1).format.columnWidth = 8;
  }
  sheet.getRangeByIndexes(0, 1 + maxStops, rows.length + 1, 4).format.columnWidth = 18;
  sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).format.autofitRows();
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const sheetName of ["Summary", "Model_Notes", ...cases]) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}

const check = await workbook.inspect({
  kind: "region",
  sheetId: "Summary",
  range: "A1:F16",
  maxChars: 6000,
  tableMaxRows: 20,
  tableMaxCols: 8,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 3000,
});
console.log(check.ndjson);
console.log(errors.ndjson);
