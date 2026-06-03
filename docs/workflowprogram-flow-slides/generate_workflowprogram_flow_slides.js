const path = require("path");
const PptxGenJS = require("pptxgenjs");
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers/layout");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Codex";
pptx.company = "WorkflowProgram-CN";
pptx.subject = "WorkflowProgram overview deck";
pptx.title = "WorkflowProgram 使用与架构总览";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

const C = {
  bg: "F7FAFD",
  white: "FFFFFF",
  ink: "17324D",
  muted: "5D7083",
  line: "B7C6D6",
  navy: "0F2740",
  blue: "1F5A91",
  teal: "0E6E6E",
  green: "1E6B45",
  amber: "A86218",
  red: "A13B3B",
  skyFill: "DCEBFA",
  skyLine: "9DBDDD",
  greenFill: "DFF3EE",
  greenLine: "9FD2C5",
  amberFill: "FFF3E4",
  amberLine: "E7BF89",
  redFill: "FDEAE9",
  redLine: "D8A5A1",
  violetFill: "F3E9FF",
  violetLine: "C8A8EC",
  slateFill: "EAF0F6",
};

function addTitle(slide, title, subtitle, page) {
  slide.background = { color: C.bg };
  slide.addText(title, {
    x: 0.5,
    y: 0.28,
    w: 8.5,
    h: 0.46,
    fontFace: "Microsoft YaHei",
    fontSize: 24,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.5,
      y: 0.78,
      w: 11.8,
      h: 0.22,
      fontFace: "Microsoft YaHei",
      fontSize: 10,
      color: C.muted,
      margin: 0,
    });
  }
  slide.addShape(pptx.ShapeType.line, {
    x: 0.5,
    y: 1.05,
    w: 12.2,
    h: 0,
    line: { color: C.line, pt: 1.1 },
  });
  slide.addText(`第 ${page} 页`, {
    x: 11.85,
    y: 7.12,
    w: 0.75,
    h: 0.18,
    fontFace: "Microsoft YaHei",
    fontSize: 9,
    color: C.muted,
    align: "right",
    margin: 0,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.5,
    y: 7.02,
    w: 12.2,
    h: 0,
    line: { color: C.line, pt: 0.8 },
  });
}

function addBox(slide, text, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.05,
    fill: { color: opts.fill || C.white },
    line: { color: opts.line || C.line, pt: opts.linePt || 1.2 },
  });
  slide.addText(text, {
    x: x + 0.08,
    y: y + 0.05,
    w: w - 0.16,
    h: h - 0.1,
    fontFace: "Microsoft YaHei",
    fontSize: opts.fontSize || 12,
    bold: opts.bold !== false,
    color: opts.color || C.ink,
    align: opts.align || "center",
    valign: opts.valign || "mid",
    margin: opts.margin === undefined ? 0.03 : opts.margin,
  });
}

function addBulletList(slide, x, y, w, items, opts = {}) {
  const gap = opts.gap || 0.31;
  const fontSize = opts.fontSize || 12;
  items.forEach((item, index) => {
    slide.addText(`• ${item}`, {
      x,
      y: y + gap * index,
      w,
      h: 0.22,
      fontFace: "Microsoft YaHei",
      fontSize,
      color: opts.color || C.ink,
      bold: false,
      margin: 0,
    });
  });
}

function addArrow(slide, x1, y1, x2, y2, color = C.blue) {
  slide.addShape(pptx.ShapeType.line, {
    x: x1,
    y: y1,
    w: x2 - x1,
    h: y2 - y1,
    line: {
      color,
      pt: 1.5,
      endArrowType: "triangle",
    },
  });
}

function finalize(slide) {
  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

function buildCover() {
  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 1.45,
    fill: { color: C.navy },
    line: { color: C.navy, pt: 0 },
  });
  slide.addText("WorkflowProgram 使用与架构总览", {
    x: 0.65,
    y: 0.5,
    w: 8.6,
    h: 0.45,
    fontFace: "Microsoft YaHei",
    fontSize: 28,
    bold: true,
    color: C.white,
    margin: 0,
  });
  slide.addText("安装步骤、设计哲学、快速使用、文件结构、运行过程与维护说明", {
    x: 0.7,
    y: 1.78,
    w: 9.4,
    h: 0.28,
    fontFace: "Microsoft YaHei",
    fontSize: 15,
    color: C.muted,
    margin: 0,
  });
  addBox(slide, "安装步骤", 0.85, 4.45, 1.8, 0.72, {
    fill: C.skyFill,
    line: C.skyLine,
    color: C.navy,
    fontSize: 15,
  });
  addBox(slide, "设计哲学", 2.95, 4.45, 1.8, 0.72, {
    fill: C.greenFill,
    line: C.greenLine,
    color: C.green,
    fontSize: 15,
  });
  addBox(slide, "快速使用", 5.05, 4.45, 1.8, 0.72, {
    fill: C.amberFill,
    line: C.amberLine,
    color: C.amber,
    fontSize: 15,
  });
  addBox(slide, "文件结构", 7.15, 4.45, 1.8, 0.72, {
    fill: C.redFill,
    line: C.redLine,
    color: C.red,
    fontSize: 15,
  });
  addBox(slide, "运行过程", 9.25, 4.45, 1.8, 0.72, {
    fill: C.violetFill,
    line: C.violetLine,
    color: "6D3A92",
    fontSize: 15,
  });
  addBox(slide, "维护说明", 11.35, 4.45, 1.2, 0.72, {
    fill: C.slateFill,
    line: C.line,
    color: C.ink,
    fontSize: 15,
  });
  addBulletList(slide, 0.95, 2.55, 11.5, [
    "WorkflowProgram-CN 是一个为 Claude Code 生态设计和维护工作流的元工作流仓库。",
    "它产出的核心不是业务代码，而是一套可交付到目标项目的 `.claude/` 工作流资产与验证链。",
    "当前能力已经扩展到：workflow-maintenance 维护说明持久化、阶段进展追踪、运行宿主抽象、矩阵化 smoke 与文档真源治理。",
  ], { fontSize: 13, gap: 0.42 });
  slide.addText("WorkflowProgram-CN", {
    x: 10.8,
    y: 6.5,
    w: 1.7,
    h: 0.25,
    fontFace: "Microsoft YaHei",
    fontSize: 12,
    color: C.blue,
    bold: true,
    align: "right",
    margin: 0,
  });
  finalize(slide);
}

function buildInstall() {
  const slide = pptx.addSlide();
  addTitle(slide, "1. 安装步骤", "当前稳定支持的是 build plugin -> claude --plugin-dir 的安装方式", 2);
  addBox(slide, "Step 1\n克隆仓库并校验", 0.8, 1.5, 2.15, 0.88, {
    fill: C.skyFill,
    line: C.skyLine,
    fontSize: 17,
  });
  addBox(slide, "Step 2\n构建 dist/plugin", 3.35, 1.5, 2.15, 0.88, {
    fill: C.greenFill,
    line: C.greenLine,
    color: C.green,
    fontSize: 17,
  });
  addBox(slide, "Step 3\n用 --plugin-dir 启动 Claude Code", 5.9, 1.5, 3.05, 0.88, {
    fill: C.amberFill,
    line: C.amberLine,
    color: C.amber,
    fontSize: 16,
  });
  addBox(slide, "Step 4\n使用 workflowprogram-* 入口", 9.35, 1.5, 2.95, 0.88, {
    fill: C.redFill,
    line: C.redLine,
    color: C.red,
    fontSize: 16,
  });
  addArrow(slide, 2.95, 1.94, 3.35, 1.94, C.blue);
  addArrow(slide, 5.5, 1.94, 5.9, 1.94, C.green);
  addArrow(slide, 8.95, 1.94, 9.35, 1.94, C.amber);

  addBox(slide, "核心命令", 0.9, 3.0, 1.25, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(
    slide,
    "git clone https://github.com/Logic70/WorkflowProgram-CN.git\ncd WorkflowProgram-CN\npython3 .claude/scripts/validate-workflow.py\npython3 tools/build_plugin.py\nclaude --plugin-dir /abs/path/to/dist/plugin",
    0.9,
    3.45,
    6.15,
    2.1,
    { align: "left", valign: "top", fontSize: 11, bold: false, margin: 0.08 }
  );

  addBox(slide, "支持的安装通道", 7.35, 3.0, 1.55, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 7.45, 3.45, 5.0, [
    "Source Build：源码仓内运行 build_plugin.py，再加载 dist/plugin。",
    "Release Package：解压 release 附件里的 plugin/ 目录，再用 --plugin-dir 加载。",
    "不建议把 dist/plugin 直接复制到用户 ~/.claude 当作稳定安装方式。",
  ], { fontSize: 12, gap: 0.38 });

  addBox(slide, "环境要求", 7.35, 5.25, 1.25, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 7.45, 5.7, 4.8, [
    "Python 3.10+",
    "Claude Code CLI",
    "git",
    "Node.js 20+ 仅在需要重新生成 PPT 时使用",
  ], { fontSize: 12, gap: 0.32 });
  finalize(slide);
}

function buildPhilosophy() {
  const slide = pptx.addSlide();
  addTitle(slide, "2. 设计哲学与概念", "三根目录、三类设计产物、S0-S6 阶段模型是这套架构的骨架", 3);
  addBox(slide, "三根目录", 0.8, 1.45, 1.3, 0.45, { fill: C.slateFill, line: C.line, fontSize: 13 });
  addBox(slide, "PLUGIN_ROOT\n插件模板、脚本、skills 来源", 0.8, 2.05, 2.65, 0.88, {
    fill: C.skyFill,
    line: C.skyLine,
    color: C.navy,
    fontSize: 15,
  });
  addBox(slide, "TARGET_ROOT\n目标项目的最终交付位置", 0.8, 3.1, 2.65, 0.88, {
    fill: C.greenFill,
    line: C.greenLine,
    color: C.green,
    fontSize: 15,
  });
  addBox(slide, "RUN_ROOT\n单次运行的设计与证据目录", 0.8, 4.15, 2.65, 0.88, {
    fill: C.amberFill,
    line: C.amberLine,
    color: C.amber,
    fontSize: 15,
  });

  addBox(slide, "三类设计产物", 4.05, 1.45, 1.55, 0.45, { fill: C.slateFill, line: C.line, fontSize: 13 });
  addBox(slide, "workflow-spec.yaml\n机器可执行真源", 4.05, 2.05, 2.5, 0.78, {
    fill: C.redFill,
    line: C.redLine,
    color: C.red,
    fontSize: 16,
  });
  addBox(slide, "workflow-view.md\n只读概览", 4.05, 3.03, 2.5, 0.64, {
    fill: C.white,
    line: C.redLine,
    color: C.ink,
    fontSize: 14,
  });
  addBox(slide, "workflow-maintenance.md\n维护/迭代指导，不覆盖 YAML 语义", 4.05, 3.87, 2.5, 0.84, {
    fill: C.white,
    line: C.redLine,
    color: C.ink,
    fontSize: 12,
  });

  addBox(slide, "阶段模型", 7.05, 1.45, 1.25, 0.45, { fill: C.slateFill, line: C.line, fontSize: 13 });
  const stageNames = [
    ["S0", "路由与准备"],
    ["S1", "需求澄清"],
    ["S2", "上下文研究"],
    ["S3", "YAML 设计"],
    ["S4", "受控写入"],
    ["S5", "验证判定"],
    ["S6", "经验回流"],
  ];
  let sx = 7.05;
  stageNames.forEach(([slot, name], idx) => {
    addBox(slide, `${slot}\n${name}`, sx, 2.05, 0.78, 0.85, {
      fill: idx % 2 === 0 ? C.violetFill : C.skyFill,
      line: idx % 2 === 0 ? C.violetLine : C.skyLine,
      fontSize: 12,
      color: C.ink,
    });
    sx += 0.82;
  });
  addBulletList(slide, 7.1, 3.25, 5.3, [
    "不是所有入口都跑完整 S1-S6，而是由 intent_flows 决定。",
    "develop 跑全链；audit 重点在 S5/S6；iterate 聚焦 S6；validate 聚焦 S5。",
    "AI 负责设计与候选生成，Python 脚本负责路由、控制面、判定与状态落盘。",
  ], { fontSize: 12, gap: 0.38 });

  addBox(slide, "一句话", 0.9, 5.75, 1.0, 0.38, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 6.15, 11.4, [
    "WorkflowProgram 不是一组 prompt，而是一条“AI 设计 + Python 控制面 + S5 judge”的产品化工作流。",
  ], { fontSize: 13, gap: 0.3 });
  finalize(slide);
}

function buildQuickUse() {
  const slide = pptx.addSlide();
  addTitle(slide, "3. 快速使用", "推荐让 orchestrate 承接自然语言，再按需要显式进入叶子入口", 4);
  addBox(slide, "推荐入口", 0.85, 1.45, 1.2, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(slide, "/workflowprogram-cn:workflowprogram-orchestrate\n\"为当前项目设计一个 Claude Code 工作流\"", 0.85, 1.95, 4.55, 0.92, {
    fill: C.skyFill,
    line: C.skyLine,
    color: C.navy,
    fontSize: 15,
  });

  addBox(slide, "显式叶子入口", 6.0, 1.45, 1.4, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(slide, "workflowprogram-develop\n高级显式 leaf / 调试入口", 6.0, 1.95, 2.95, 0.92, {
    fill: C.greenFill,
    line: C.greenLine,
    color: C.green,
    fontSize: 13,
  });
  addBox(slide, "/workflowprogram-audit\n/path/to/existing-project", 9.2, 1.95, 1.55, 0.92, {
    fill: C.amberFill,
    line: C.amberLine,
    color: C.amber,
    fontSize: 11,
  });
  addBox(slide, "/workflowprogram-validate\n/path/to/existing-project", 10.95, 1.95, 1.55, 0.92, {
    fill: C.redFill,
    line: C.redLine,
    color: C.red,
    fontSize: 11,
  });

  addBox(slide, "一次典型 develop 的结果", 0.95, 3.45, 1.75, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.05, 3.92, 5.45, [
    "RUN_ROOT/workflow-spec.yaml",
    "RUN_ROOT/workflow-view.md",
    "RUN_ROOT/workflow-maintenance.md",
    "RUN_ROOT/outputs/candidate/.claude/",
    "TARGET_ROOT/.workflowprogram/design/",
  ], { fontSize: 12, gap: 0.34 });

  addBox(slide, "审批模式", 6.45, 3.45, 1.2, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 6.55, 3.92, 5.5, [
    "交互模式：等待人工确认通过 S3 gate。",
    "自动模式：使用 --auto-approve 或 CI=true。",
    "状态会区分 approved 与 auto-approved，不混淆人工与自动批准。",
  ], { fontSize: 12, gap: 0.34 });

  addBox(slide, "兼容入口", 0.95, 5.55, 1.15, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.05, 6.0, 11.2, [
    "历史 /develop、/evolve-workflow、/iterate-workflow 仍可用，但当前主路径推荐 workflowprogram-*。",
    "显式 develop 不会跳回 orchestrate；orchestrate 只负责自然语言总入口。",
  ], { fontSize: 12, gap: 0.32 });
  finalize(slide);
}

function buildStructure() {
  const slide = pptx.addSlide();
  addTitle(slide, "4. 文件结构", "同时看仓库结构和目标项目落盘结构，最容易理解工作流边界", 5);
  addBox(slide, "仓库结构", 0.8, 1.45, 1.15, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(
    slide,
    "WorkflowProgram-CN/\n├── .claude/\n├── dist/plugin/\n├── docs/\n├── openspec/\n├── tests/\n├── tools/\n├── lessons.md\n└── validation-report.md",
    0.8,
    1.92,
    4.8,
    3.2,
    { align: "left", valign: "top", fontSize: 12, bold: false, margin: 0.09 }
  );

  addBox(slide, "目标项目落盘结构", 6.0, 1.45, 1.65, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(
    slide,
    "TARGET_ROOT/\n├── .claude/\n└── .workflowprogram/\n    ├── managed-files.json\n    ├── design/\n    │   ├── workflow-spec.yaml\n    │   ├── workflow-view.md\n    │   └── workflow-maintenance.md\n    └── runs/<run-id>/",
    6.0,
    1.92,
    5.7,
    3.2,
    { align: "left", valign: "top", fontSize: 12, bold: false, margin: 0.09 }
  );

  addBox(slide, "关键文件", 0.95, 5.2, 1.0, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.05, 5.62, 11.2, [
    "workflow-spec.yaml：机器真源，决定执行语义、边界、intent_flows、runtime/test contract。",
    "workflow-view.md：从 YAML 渲染的只读概览，方便审查，不作为执行真源。",
    "workflow-maintenance.md：从 YAML 渲染的维护指导，不允许覆盖 YAML 语义。",
    "managed-files.json：记录哪些目标资产由 WorkflowProgram 托管更新。",
  ], { fontSize: 12, gap: 0.32 });
  finalize(slide);
}

function buildRuntimeFlow() {
  const slide = pptx.addSlide();
  addTitle(slide, "5. 运行过程", "把从 skill 到脚本链、从 candidate 到 verdict 的主过程压缩成一页", 6);
  addBox(slide, "自然语言\n或显式入口", 0.75, 1.8, 1.35, 0.82, { fill: C.skyFill, line: C.skyLine, fontSize: 14 });
  addBox(slide, "workflowprogram-\norchestrate / develop", 2.45, 1.8, 1.75, 0.82, { fill: C.greenFill, line: C.greenLine, color: C.green, fontSize: 14 });
  addBox(slide, "route-intent.py", 4.55, 1.8, 1.25, 0.82, { fill: C.white, line: C.skyLine, color: C.blue, fontSize: 14 });
  addBox(slide, "workflow-entry.py run", 6.15, 1.8, 1.75, 0.82, { fill: C.violetFill, line: C.violetLine, color: "6D3A92", fontSize: 14 });
  addBox(slide, "managed-assets.py", 8.25, 1.8, 1.5, 0.82, { fill: C.amberFill, line: C.amberLine, color: C.amber, fontSize: 14 });
  addBox(slide, "workflow-runner.py", 10.1, 1.8, 1.55, 0.82, { fill: C.amberFill, line: C.amberLine, color: C.amber, fontSize: 14 });
  addBox(slide, "workflowprogram-validate\n+ workflow-s5-judge.py", 10.0, 3.35, 1.75, 0.92, { fill: C.redFill, line: C.redLine, color: C.red, fontSize: 12 });
  addArrow(slide, 2.1, 2.2, 2.45, 2.2, C.blue);
  addArrow(slide, 4.2, 2.2, 4.55, 2.2, C.green);
  addArrow(slide, 5.8, 2.2, 6.15, 2.2, C.blue);
  addArrow(slide, 7.9, 2.2, 8.25, 2.2, C.amber);
  addArrow(slide, 9.75, 2.2, 10.1, 2.2, C.amber);
  addArrow(slide, 10.9, 2.62, 10.9, 3.35, C.red);

  addBox(slide, "脚本链内部顺序", 0.9, 4.7, 1.55, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 5.15, 11.3, [
    "validate-workflow-spec.py -> generate-workflow-view.py -> generate-workflow-maintenance.py",
    "managed-assets.py plan/apply-staged -> workflow-runner.py run -> validate-run-state.py",
    "若 managed apply 冲突，流程停在 S4，不进入 runner，不覆盖目标资产。",
    "真正的 workflow 级 verdict 在 S5 judge，而不是 runner。",
  ], { fontSize: 12, gap: 0.32 });
  finalize(slide);
}

function buildEvidenceProgress() {
  const slide = pptx.addSlide();
  addTitle(slide, "6. 运行证据与进展资产", "这部分解释为什么它不是黑盒：每次运行都会留下可追踪的状态、事件与用户进展", 7);
  addBox(slide, "控制面证据", 0.85, 1.5, 1.25, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 0.95, 1.95, 2.75, [
    "context.json",
    "state.json",
    "events.jsonl",
    "outputs/stages/runner-summary.json",
    "outputs/stages/s0-route.json",
  ], { fontSize: 12, gap: 0.34 });

  addBox(slide, "进展资产", 4.35, 1.5, 1.05, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 4.65, 1.95, 2.25, [
    "current-progress.json",
    "milestones.jsonl",
    "user-progress.md",
  ], { fontSize: 12, gap: 0.34 });

  addBox(slide, "验证产物", 8.0, 1.5, 1.05, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 8.35, 1.95, 3.35, [
    "transcript.md",
    "validation-runtime-report.md",
    "s5-validation-summary.json",
    "s6-lessons-delta.md",
  ], { fontSize: 12, gap: 0.34 });

  addBox(slide, "阶段进展统一入口", 0.95, 4.15, 1.45, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(slide, "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py update ...", 0.95, 4.62, 6.0, 0.76, {
    align: "left",
    fontSize: 12,
    bold: false,
    margin: 0.08,
  });

  addBox(slide, "运行宿主抽象", 7.35, 4.15, 1.2, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 7.45, 4.62, 4.9, [
    "claude_cli：正式主路径",
    "fixture_host：确定性测试宿主",
    "command_adapter：外部宿主适配层",
    "runtime_smoke_matrix.py：统一矩阵复验入口",
  ], { fontSize: 12, gap: 0.32 });

  addBox(slide, "结论", 0.95, 6.05, 0.85, 0.4, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.05, 6.47, 11.2, [
    "这套运行链是可追踪、可复验、可追责的，不只是“让 AI 跑一遍然后相信它”。",
  ], { fontSize: 12, gap: 0.3 });
  finalize(slide);
}

function buildMaintenance() {
  const slide = pptx.addSlide();
  addTitle(slide, "7. 维护说明", "修改语义要改哪里，修改后要跑什么，是这页最重要的内容", 8);
  addBox(slide, "文档真源", 0.8, 1.45, 1.0, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 0.9, 1.92, 5.4, [
    "docs/workflowprogram-stage-highlevel-design.md",
    "docs/workflowprogram-stage-lowlevel-design.md",
    "docs/workflowprogram-stage-consistency-check.md",
    "docs/workflowprogram-design-status.md",
    "docs/workflowprogram-capability-matrix.json",
  ], { fontSize: 12, gap: 0.32 });

  addBox(slide, "修改规则", 6.45, 1.45, 1.0, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 6.55, 1.92, 5.35, [
    "改执行语义：先改 workflow-spec.yaml。",
    "改人类视图：重生成 workflow-view.md。",
    "改维护说明：重生成 workflow-maintenance.md。",
    "不要只改 view / lowlevel / README 试图改变真实执行语义。",
  ], { fontSize: 12, gap: 0.32 });

  addBox(slide, "常用维护命令", 0.9, 4.0, 1.25, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBox(
    slide,
    "python3 .claude/scripts/validate-workflow.py\npython3 tools/build_plugin.py\npython3 .claude/scripts/validate-workflow-spec.py --spec <spec>\npython3 .claude/scripts/validate-workflow-maintenance.py --spec <spec> --maintenance <maintenance>\npython3 tools/runtime_smoke_matrix.py --json",
    0.9,
    4.45,
    6.15,
    1.95,
    { align: "left", valign: "top", fontSize: 11, bold: false, margin: 0.08 }
  );

  addBox(slide, "经验沉淀机制", 7.45, 4.0, 1.35, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 7.55, 4.45, 4.8, [
    "lessons.md：追加式失败经验日志",
    "constraints.md：沉淀后的长期规则",
    "s6-lessons-delta.md：单次运行的经验增量",
    "user-progress.md：面向用户的关键节点历史与下一步",
  ], { fontSize: 12, gap: 0.31 });
  finalize(slide);
}

function buildClose() {
  const slide = pptx.addSlide();
  addTitle(slide, "8. 一页结论", "给第一次接触 WorkflowProgram 的读者一个足够准确的心智模型", 9);
  addBox(slide, "它是什么", 0.9, 1.5, 1.0, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 1.95, 11.0, [
    "它是一个“为 Claude Code 生态设计工作流”的元工作流仓库。",
  ], { fontSize: 13, gap: 0.3 });

  addBox(slide, "它不是什么", 0.9, 2.75, 1.15, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 3.2, 11.0, [
    "它不是业务应用模板，也不是只靠 prompt 串起来的松散说明文档。",
  ], { fontSize: 13, gap: 0.3 });

  addBox(slide, "最关键的 4 个点", 0.9, 3.9, 1.45, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 4.35, 11.2, [
    "三根目录：PLUGIN_ROOT / TARGET_ROOT / RUN_ROOT 必须分清。",
    "三类设计产物：spec 是真源，view 是概览，lowlevel 是维护指导。",
    "运行主链：workflow-entry -> managed-assets -> workflow-runner -> validate -> S5 judge。",
    "维护闭环：validator + smoke + lessons/constraints，保证它不仅能设计，还能长期演进。",
  ], { fontSize: 12, gap: 0.33 });

  addBox(slide, "配套文档", 0.9, 5.78, 1.0, 0.42, { fill: C.slateFill, line: C.line, fontSize: 12 });
  addBulletList(slide, 1.0, 6.2, 11.0, [
    "README：使用者入口",
    "docs/workflowprogram-101/ 与 docs/workflowprogram-flow-slides/：教程与图形化讲解",
    "docs/workflowprogram-design-status.md 与 capability-matrix：文档真源索引与能力对齐矩阵",
  ], { fontSize: 12, gap: 0.29 });
  finalize(slide);
}

async function main() {
  buildCover();
  buildInstall();
  buildPhilosophy();
  buildQuickUse();
  buildStructure();
  buildRuntimeFlow();
  buildEvidenceProgress();
  buildMaintenance();
  buildClose();

  const outPath = path.join(__dirname, "workflowprogram_overview.pptx");
  await pptx.writeFile({ fileName: outPath });
  console.log(`Wrote ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
