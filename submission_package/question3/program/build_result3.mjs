import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [jsonPath, outputPath, previewDir] = process.argv.slice(2);
if (!jsonPath || !outputPath) throw new Error("Usage: node build_result3.mjs q3_solution.json result3.xlsx [preview_dir]");

const results = JSON.parse(await fs.readFile(jsonPath, "utf8"));
const cases = Object.keys(results);
const workbook = Workbook.create();
const navy = "#1F4E78";
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
summary.mergeCells("A1:H1");
summary.getRange("A1").values = [["问题三：动态圆形飞行管制下的多无人机协同巡检结果"]];
summary.getRange("A1:H1").format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
summary.mergeCells("A2:H2");
summary.getRange("A2").values = [["8:00 为时间原点；固定问题一采用的无人机数量；17:00 不是任务截止时刻；仅允许管制所必需的安全等待。"]];
summary.getRange("A2:H2").format = { fill: pale, font: { color: gray }, wrapText: true };
summary.getRange("A4:H4").values = [["测试算例", "无人机数量 N", "Tmax (h)", "Tmin (h)", "δ=Tmax-Tmin (h)", "总等待 (min)", "最晚返回", "独立验证"]];
styleHeader(summary.getRange("A4:H4"));
const rows = cases.map((name) => {
  const r = results[name];
  return [name, r.N, r.Tmax, r.Tmin, null, r.total_wait_min, r.latest_return, "PASSED"];
});
summary.getRange(`A5:H${4 + cases.length}`).values = rows;
for (let row = 5; row < 5 + cases.length; row += 1) summary.getRange(`E${row}`).formulas = [[`=C${row}-D${row}`]];
styleBody(summary.getRange(`A5:H${4 + cases.length}`));
summary.getRange(`A5:H${4 + cases.length}`).format.horizontalAlignment = "center";
summary.getRange(`A5:H${4 + cases.length}`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
summary.getRange(`B5:B${4 + cases.length}`).format.numberFormat = "0";
summary.getRange(`C5:E${4 + cases.length}`).format.numberFormat = "0.0000";
summary.getRange(`F5:F${4 + cases.length}`).format.numberFormat = "0.000";
summary.getRange(`H5:H${4 + cases.length}`).format.fill = green;

summary.getRange("A11:E11").values = [["测试算例", "管制区数", "正时长管制区", "零时长记录", "涉及巡检点数"]];
styleHeader(summary.getRange("A11:E11"));
summary.getRange(`A12:E${11 + cases.length}`).values = cases.map((name) => {
  const z = results[name].zone_summary;
  return [name, z.zone_count, z.positive_duration_count, z.zero_duration_count, z.involved_point_count];
});
styleBody(summary.getRange(`A12:E${11 + cases.length}`));
summary.mergeCells("A18:H18");
summary.getRange("A18").values = [["注：Case 4 的 Z8=[17:00,17:00) 为空区间，正式结果中不产生飞行约束。"]];
summary.getRange("A18:H18").format = { fill: pale, font: { color: gray }, wrapText: true };
summary.freezePanes.freezeRows(4);
summary.getRange("A1:H18").format.autofitRows();
summary.getRange("A:A").format.columnWidth = 14;
summary.getRange("B:F").format.columnWidth = 19;
summary.getRange("G:H").format.columnWidth = 18;

const notes = workbook.worksheets.add("Model_Notes");
notes.showGridLines = false;
notes.getRange("A1:B1").values = [["项目", "说明"]];
styleHeader(notes.getRange("A1:B1"));
notes.getRange("A2:B10").values = [
  ["时间基准", "8:00 对应 t=0，内部以分钟计算；17:00 仅为部分管制解除时刻，不是任务截止。"],
  ["机队规模", "各算例固定采用问题一最终方案的无人机数量 N=(4,2,5,4)。"],
  ["动态管制", "管制时间统一解释为半开区间 [start,end)；零时长区间为空集。"],
  ["航段判定", "解析求线段位于圆内的参数区间，再与实际飞行时段比较，而非只检查端点。"],
  ["服务约束", "巡检点位于生效圆内时，完整 5 分钟服务区间不得与管制时段重叠。"],
  ["必要等待", "只为避开动态管制而等待；基地允许地面等待，非基地等待必须处于安全位置。"],
  ["目标顺序", "按 (Tmax, δ, 总工作时间) 词典序比较候选方案。"],
  ["结果性质", "多起点变邻域/模拟退火得到的当前最好可行方案，不宣称全局最优。"],
  ["独立验证", "q3_fast_validator.py 使用包围盒预筛与解析线段—圆相交，逐事件复核全部路线。"],
];
styleBody(notes.getRange("A2:B10"));
notes.getRange("A1:B10").format.wrapText = true;
notes.getRange("A:A").format.columnWidth = 20;
notes.getRange("B:B").format.columnWidth = 92;
notes.getRange("A1:B10").format.autofitRows();
notes.freezePanes.freezeRows(1);

for (const caseName of cases) {
  const result = results[caseName];
  const sheet = workbook.worksheets.add(caseName);
  sheet.showGridLines = false;
  const maxStops = Math.max(...result.routes.map((r) => r.sequence.length));
  const headers = ["UAV ID"];
  for (let i = 1; i <= maxStops; i += 1) headers.push(`${i}th Inspection Point`);
  headers.push("Flight Distance (km)", "Inspection Count", "Flight Time (h)", "Waiting Time (min)", "Working Time (h)", "Return Time");
  sheet.getRangeByIndexes(0, 0, 1, headers.length).values = [[...headers]];
  styleHeader(sheet.getRangeByIndexes(0, 0, 1, headers.length));
  const routeRows = result.routes.map((route) => {
    const padding = Array(maxStops - route.sequence.length).fill(null);
    return [route.uav, ...route.sequence, ...padding, route.distance_km, route.service_count, route.flight_time_h, route.wait_time_h * 60, route.time_h, route.return_clock];
  });
  sheet.getRangeByIndexes(1, 0, routeRows.length, headers.length).values = routeRows;
  styleBody(sheet.getRangeByIndexes(1, 0, routeRows.length, headers.length));
  sheet.getRangeByIndexes(1, 0, routeRows.length, headers.length).format.horizontalAlignment = "center";
  sheet.getRangeByIndexes(1, 0, routeRows.length, headers.length).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  const metrics = 1 + maxStops;
  sheet.getRangeByIndexes(1, metrics, routeRows.length, 1).format.numberFormat = "0.000";
  sheet.getRangeByIndexes(1, metrics + 1, routeRows.length, 1).format.numberFormat = "0";
  sheet.getRangeByIndexes(1, metrics + 2, routeRows.length, 1).format.numberFormat = "0.0000";
  sheet.getRangeByIndexes(1, metrics + 3, routeRows.length, 1).format.numberFormat = "0.000";
  sheet.getRangeByIndexes(1, metrics + 4, routeRows.length, 1).format.numberFormat = "0.0000";
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  sheet.getRangeByIndexes(0, 0, routeRows.length + 1, headers.length).format.autofitRows();
  sheet.getRangeByIndexes(0, 0, routeRows.length + 1, 1).format.columnWidth = 10;
  for (let col = 1; col <= maxStops; col += 1) sheet.getRangeByIndexes(0, col, routeRows.length + 1, 1).format.columnWidth = 8;
  sheet.getRangeByIndexes(0, metrics, routeRows.length + 1, 6).format.columnWidth = 21;

  const events = workbook.worksheets.add(`${caseName}_Events`);
  events.showGridLines = false;
  const eventHeaders = ["UAV", "Event No.", "Type", "Start (min)", "End (min)", "Duration (min)", "From", "To", "Node", "Distance (km)", "Reason Zone"];
  events.getRange("A1:K1").values = [[...eventHeaders]];
  styleHeader(events.getRange("A1:K1"));
  const eventRows = [];
  for (const route of result.routes) {
    route.events.forEach((event, index) => eventRows.push([
      route.uav,
      index + 1,
      event.type,
      event.start_min,
      event.end_min,
      event.duration_min,
      event.from ?? null,
      event.to ?? null,
      event.node ?? null,
      event.distance_km ?? null,
      (event.reason_zone_ids ?? []).join(", "),
    ]));
  }
  events.getRangeByIndexes(1, 0, eventRows.length, eventHeaders.length).values = eventRows;
  styleBody(events.getRangeByIndexes(1, 0, eventRows.length, eventHeaders.length));
  events.getRangeByIndexes(1, 3, eventRows.length, 3).format.numberFormat = "0.000";
  events.getRangeByIndexes(1, 9, eventRows.length, 1).format.numberFormat = "0.000";
  events.freezePanes.freezeRows(1);
  events.getRange("A:K").format.columnWidth = 14;
  events.getRange("K:K").format.columnWidth = 34;
  events.getRangeByIndexes(0, 0, eventRows.length + 1, eventHeaders.length).format.autofitRows();
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const sheetName of ["Summary", "Model_Notes", ...cases, ...cases.map((name) => `${name}_Events`)]) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}

const check = await workbook.inspect({ kind: "region", sheetId: "Summary", range: "A1:H18", maxChars: 7000, tableMaxRows: 20, tableMaxCols: 10 });
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 200 }, maxChars: 3000 });
console.log(check.ndjson);
console.log(errors.ndjson);
