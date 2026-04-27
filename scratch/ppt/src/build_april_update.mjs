import { createRequire } from "node:module";
import fs from "node:fs/promises";
import path from "node:path";

const workspace = "/Users/xy718/workspace/nodeskclaw";
const runtimeRoot = "/Users/xy718/.cache/codex-runtimes/codex-primary-runtime/dependencies/node";
const runtimeRequire = createRequire(`${runtimeRoot}/package.json`);
const artifact = await import(runtimeRequire.resolve("@oai/artifact-tool"));
const artifactRequire = createRequire(`${runtimeRoot}/node_modules/@oai/artifact-tool/package.json`);
const { Canvas } = await import(artifactRequire.resolve("skia-canvas"));

const {
  Presentation,
  PresentationFile,
  row,
  column,
  grid,
  layers,
  panel,
  text,
  shape,
  rule,
  fill,
  hug,
  fixed,
  wrap,
  grow,
  fr,
  auto,
  drawSlideToCtx,
} = artifact;

const W = 1920;
const H = 1080;
const outputDir = path.join(workspace, "output");
const previewDir = path.join(workspace, "scratch/ppt/previews");
const pptxPath = path.join(outputDir, "nodeskclaw-april-update.pptx");
const montagePath = path.join(previewDir, "montage.png");

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

function logStep(label) {
  console.log(`[ppt] ${label}`);
}

function formatError(error) {
  return {
    name: error?.name,
    message: error?.message,
    stack: error?.stack?.split("\n").slice(0, 12).join("\n"),
    cause: error?.cause,
  };
}

const C = {
  ink: "#0E1720",
  ink2: "#172432",
  paper: "#F7F9F6",
  paper2: "#EEF4EF",
  text: "#16212D",
  muted: "#5B6875",
  mint: "#8AE6B0",
  cyan: "#52D1DC",
  coral: "#FF6B6B",
  amber: "#F6C85F",
  blue: "#3366FF",
  line: "#D7E0DA",
  white: "#FFFFFF",
};

const font = "Aptos";
const zhFont = "PingFang SC";

const titleStyle = (color = C.text, size = 56) => ({
  fontSize: size,
  bold: true,
  color,
  typeface: zhFont,
  lineSpacing: 1.08,
});

const bodyStyle = (color = C.muted, size = 25) => ({
  fontSize: size,
  color,
  typeface: zhFont,
  lineSpacing: 1.18,
});

const labelStyle = (color = C.muted, size = 18) => ({
  fontSize: size,
  color,
  typeface: zhFont,
  letterSpacing: 0,
});

const monoStyle = (color = C.text, size = 20) => ({
  fontSize: size,
  color,
  typeface: font,
  bold: true,
});

function bg(fillColor) {
  return shape({
    name: "background",
    width: fill,
    height: fill,
    fill: fillColor,
  });
}

function pill(label, color, fillColor = "transparent") {
  return panel(
    {
      name: `pill-${label}`,
      width: fixed(340),
      height: hug,
      fill: fillColor,
      borderRadius: "rounded-full",
      padding: { x: 18, y: 8 },
    },
    text(label, {
      width: fill,
      height: hug,
      style: { ...labelStyle(color, 18), bold: true, alignment: "center" },
    }),
  );
}

function footer(label = "依据：2026-04-01 至 2026-04-27 本地 git log（主仓库 + ee 仓库）") {
  return row(
    { name: "footer", width: fill, height: hug, gap: 16, align: "center" },
    [
      rule({ name: "footer-rule", width: grow(1), stroke: C.line, weight: 1 }),
      text(label, {
        name: "footer-label",
        width: hug,
        height: hug,
        style: labelStyle(C.muted, 14),
      }),
    ],
  );
}

function slideShell(presentation, options, content) {
  const slide = presentation.slides.add();
  const background = bg(options.background ?? C.paper);
  slide.compose(
    layers(
      { name: "slide-layers", width: fill, height: fill },
      [
        background,
        column(
          {
            name: "slide-root",
            width: fill,
            height: fill,
            padding: { x: 88, y: 64 },
            gap: options.gap ?? 34,
          },
          content,
        ),
      ],
    ),
    { frame: { left: 0, top: 0, width: W, height: H }, baseUnit: 8 },
  );
  return slide;
}

function header(kicker, title, subtitle, dark = false) {
  return column(
    { name: "header", width: fill, height: hug, gap: 16 },
    [
      row(
        { name: "header-kicker-row", width: fill, height: hug, gap: 12, align: "center" },
        [
          rule({ name: "kicker-rule", width: fixed(72), stroke: dark ? C.mint : C.blue, weight: 5 }),
          text(kicker, {
            name: "kicker",
            width: fill,
            height: hug,
            style: { ...labelStyle(dark ? "#A7BAC8" : C.muted, 18), bold: true },
          }),
        ],
      ),
      text(title, {
        name: "slide-title",
        width: fill,
        height: hug,
        style: titleStyle(dark ? C.white : C.text, 52),
      }),
      subtitle
        ? text(subtitle, {
          name: "slide-subtitle",
          width: wrap(1380),
          height: hug,
          style: bodyStyle(dark ? "#C7D8E4" : C.muted, 24),
        })
        : text("", { width: fixed(1), height: fixed(1), style: { fontSize: 1, color: "transparent" } }),
    ],
  );
}

function openMetric(value, label, color) {
  return column(
    { name: `metric-${label}`, width: fill, height: hug, gap: 6 },
    [
      text(value, {
        width: fill,
        height: hug,
        style: { ...titleStyle(color, 56), typeface: font },
      }),
      text(label, {
        width: fill,
        height: hug,
        style: labelStyle("#C8D4DD", 18),
      }),
    ],
  );
}

function lane(index, title, body, color) {
  return row(
    { name: `lane-${index}`, width: fill, height: hug, gap: 22, align: "center" },
    [
      panel(
        {
          name: `lane-index-${index}`,
          width: fixed(58),
          height: fixed(58),
          fill: color,
          borderRadius: 12,
          align: "center",
          justify: "center",
        },
        text(String(index).padStart(2, "0"), {
          width: fill,
          height: hug,
          style: { ...monoStyle(C.ink, 20), alignment: "center" },
        }),
      ),
      column(
        { name: `lane-copy-${index}`, width: fill, height: hug, gap: 6 },
        [
          text(title, {
            width: fill,
            height: hug,
            style: { ...bodyStyle(C.text, 28), bold: true },
          }),
          text(body, {
            width: fill,
            height: hug,
            style: bodyStyle(C.muted, 21),
          }),
        ],
      ),
    ],
  );
}

function chipStack(items) {
  return column(
    { name: "chip-stack", width: fill, height: hug, gap: 16 },
    items.map(([label, color]) => pill(label, color, `${color}18`)),
  );
}

function miniStep(label, detail, color) {
  return column(
    { name: `step-${label}`, width: fill, height: hug, gap: 10 },
    [
      rule({ name: `step-rule-${label}`, width: fixed(110), stroke: color, weight: 5 }),
      text(label, {
        width: fill,
        height: hug,
        style: { ...bodyStyle(C.text, 31), bold: true },
      }),
      text(detail, {
        width: fill,
        height: hug,
        style: bodyStyle(C.muted, 21),
      }),
    ],
  );
}

function miniStepDark(label, detail, color) {
  return column(
    { name: `dark-step-${label}`, width: fill, height: hug, gap: 10 },
    [
      rule({ name: `dark-step-rule-${label}`, width: fixed(110), stroke: color, weight: 5 }),
      text(label, {
        width: fill,
        height: hug,
        style: { ...bodyStyle(C.white, 31), bold: true },
      }),
      text(detail, {
        width: fill,
        height: hug,
        style: bodyStyle("#C7D8E4", 21),
      }),
    ],
  );
}

const presentation = Presentation.create({
  slideSize: { width: W, height: H },
});

slideShell(
  presentation,
  { background: C.ink, gap: 46 },
  [
    row(
      { name: "cover-top", width: fill, height: hug, align: "center" },
      [
        text("NoDeskClaw", {
          width: fill,
          height: hug,
          style: { ...monoStyle(C.mint, 22), letterSpacing: 1.8 },
        }),
        text("2026.04 产品更新分享", {
          width: hug,
          height: hug,
          style: labelStyle("#9FB4C2", 18),
        }),
      ],
    ),
    grid(
      {
        name: "cover-grid",
        width: fill,
        height: fill,
        columns: [fr(1.35), fr(0.65)],
        columnGap: 86,
        rows: [fr(1)],
      },
      [
        column(
          { name: "cover-copy", width: fill, height: fill, gap: 34, justify: "center" },
          [
            text("四月更新：从实例控制台，走向 AI 员工运营平台", {
              name: "cover-title",
              width: wrap(1120),
              height: hug,
              style: titleStyle(C.white, 74),
            }),
            text("多集群、拓扑路由、模板部署、模型供应商、灾备、绩效与运行底座，在这个月连成了一条完整产品主线。", {
              name: "cover-subtitle",
              width: wrap(980),
              height: hug,
              style: bodyStyle("#C7D8E4", 29),
            }),
            row(
              { name: "cover-pills", width: fill, height: hug, gap: 14 },
              [
                pill("CE + EE", C.mint, "#8AE6B01A"),
                pill("Agent（AI 员工）", C.cyan, "#52D1DC1A"),
                pill("K8s（Kubernetes 集群）", C.amber, "#F6C85F1A"),
              ],
            ),
          ],
        ),
        column(
          { name: "cover-metrics", width: fill, height: fill, gap: 36, justify: "center" },
          [
            openMetric("260", "主仓库四月非 merge 提交", C.mint),
            openMetric("48", "ee 仓库同步提交", C.cyan),
            openMetric("7", "可对外分享的产品主线", C.amber),
          ],
        ),
      ],
    ),
    footer("截至 2026-04-27，本地仓库四月提交统计"),
  ],
);

slideShell(
  presentation,
  { background: C.paper },
  [
    header("总览", "四月主线：底座补齐，协作显性化，运营可量化", "这些更新不是单点功能堆叠，而是在把 DeskClaw 实例管理升级为 AI 员工平台。"),
    grid(
      {
        name: "overview-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1)],
        rows: [auto, auto, auto, auto],
        columnGap: 60,
        rowGap: 28,
      },
      [
        lane(1, "多集群承载", "Workspace（工作区）与实例开始显式绑定目标 Cluster（集群）。", C.mint),
        lane(2, "可控协作路由", "Agent（AI 员工）消息按拓扑可达性流转，黑板访问也有边界。", C.cyan),
        lane(3, "模板资产化", "模板可以更新、覆盖、删除，并支撑拓扑交互式一键部署。", C.amber),
        lane(4, "模型入口统一", "LLM Provider（大模型供应商）从 Key 管理扩展成团队模型方案。", C.coral),
        lane(5, "实例生命周期闭环", "备份、恢复、克隆、重建补上生产运维必需动作。", C.blue),
        lane(6, "绩效与失败可见", "任务失败、Token（令牌）消耗、ROI（投入产出比）进入指标面板。", C.mint),
        lane(7, "底座可治理", "NetworkPolicy（网络策略）、StorageClass（存储类）、版本目录逐步可配置。", C.cyan),
      ],
    ),
    footer(),
  ],
);

slideShell(
  presentation,
  { background: C.paper2 },
  [
    header("01 多集群", "多集群能力成型：办公室和实例开始知道自己部署在哪里", "四月的变化让 CE/EE 都不再被单集群假设锁住，后续才能承载更复杂的组织和环境边界。"),
    grid(
      {
        name: "cluster-grid",
        width: fill,
        height: fill,
        columns: [fr(0.72), fr(1.28)],
        columnGap: 78,
      },
      [
        column(
          { name: "cluster-left", width: fill, height: fill, gap: 24, justify: "center" },
          [
            text("cluster_id", {
              width: fill,
              height: hug,
              style: { ...monoStyle(C.blue, 54), letterSpacing: 0 },
            }),
            text("（集群 ID）成为 Workspace（工作区）和部署流程的显式坐标。", {
              width: fill,
              height: hug,
              style: bodyStyle(C.text, 28),
            }),
            rule({ width: fixed(220), stroke: C.blue, weight: 5 }),
          ],
        ),
        column(
          { name: "cluster-right", width: fill, height: fill, gap: 30, justify: "center" },
          [
            miniStep("创建办公室可选目标集群", "Portal（用户门户）新增集群选择器，后端 Schema（数据结构）与 Service（服务层）同步透传。", C.blue),
            miniStep("创建 AI 员工按集群过滤", "AddAgentDialog（添加员工弹窗）按 Workspace（工作区）绑定集群过滤候选实例。", C.mint),
            miniStep("CE/EE 共同解除单集群限制", "实例、事件、StorageClass（存储类）、K8s Client（集群客户端）都按 cluster_id（集群 ID）取数。", C.cyan),
          ],
        ),
      ],
    ),
    footer("代表提交：feat(cluster): 移除单集群限制，CE/EE 均支持多集群"),
  ],
);

slideShell(
  presentation,
  { background: C.ink },
  [
    header("02 拓扑协作", "拓扑协作：黑盒群聊变成可控路由", "Agent（AI 员工）消息是否能到达，不再只看谁被 @，还要看办公室拓扑是否连通。", true),
    grid(
      {
        name: "topology-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1)],
        columnGap: 78,
      },
      [
        column(
          { name: "before", width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("之前", { width: fill, height: hug, style: { ...labelStyle("#9FB4C2", 20), bold: true } }),
            text("广播退化容易让协作变成“全员可见”。", {
              width: fill,
              height: hug,
              style: titleStyle(C.white, 48),
            }),
            text("Agent（AI 员工）没有明确空间边界，群聊像黑盒，调试也难。", {
              width: fill,
              height: hug,
              style: bodyStyle("#C7D8E4", 24),
            }),
          ],
        ),
        column(
          { name: "after", width: fill, height: fill, gap: 26, justify: "center" },
          [
            text("现在", { width: fill, height: hug, style: { ...labelStyle(C.mint, 20), bold: true } }),
            miniStepDark("check_topology_access（拓扑可达性校验）", "AI→AI 单播先判断走廊连通关系，不可达就阻断并给出 reason（原因）。", C.mint),
            miniStepDark("check_blackboard_access（黑板访问校验）", "黑板 API（接口）也按拓扑拦截，错误码接入 i18n（国际化）文案。", C.cyan),
            miniStepDark("reachable member list（可达成员列表）", "系统提示词注入当前可达成员，减少 Agent（AI 员工）误找不可达对象。", C.amber),
          ],
        ),
      ],
    ),
    footer("代表提交：feat: topology-based multi-room group chat to eliminate agent communication black box"),
  ],
);

slideShell(
  presentation,
  { background: C.paper },
  [
    header("03 模板部署", "模板一键部署进入可运营阶段", "从“保存一个办公室快照”，进化到“可以更新、治理、复用的部署资产”。"),
    grid(
      {
        name: "template-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1), fr(1), fr(1)],
        columnGap: 34,
      },
      [
        miniStep("保存", "采集办公室拓扑、黑板快照和 Gene（技能基因）分配。", C.blue),
        miniStep("治理", "模板名称唯一，支持 update/overwrite（更新/覆盖）与 delete（删除）。", C.coral),
        miniStep("选择", "一键部署时可交互选择拓扑节点和目标配置。", C.mint),
        miniStep("通知", "部署过程通过 SSE（服务端推送）反馈状态，模板卡片更适合浏览。", C.cyan),
      ],
    ),
    row(
      { name: "template-bottom", width: fill, height: hug, gap: 18, align: "center" },
      [
        pill("node_cards（节点卡片表）兼容", C.blue, "#3366FF14"),
        pill("legacy 表双写过渡", C.muted, "#5B687514"),
        pill("组织边界收紧", C.coral, "#FF6B6B14"),
      ],
    ),
    footer("代表提交：feat(template): template update/overwrite, delete, and name uniqueness"),
  ],
);

slideShell(
  presentation,
  { background: C.paper2 },
  [
    header("04 LLM Provider", "LLM Provider（大模型供应商）体系重构", "团队模型配置从“存几个 Key”变成可管理、可验证、可分发的 Working Plan（团队模型方案）。"),
    grid(
      {
        name: "llm-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1.15)],
        columnGap: 72,
      },
      [
        column(
          { name: "llm-left", width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("OrgModelProvider", {
              width: fill,
              height: hug,
              style: { ...monoStyle(C.blue, 46), letterSpacing: 0 },
            }),
            text("（组织模型供应商）成为组织级模型能力的核心对象。", {
              width: fill,
              height: hug,
              style: bodyStyle(C.text, 28),
            }),
            chipStack([
              ["api_type（接口协议类型）", C.blue],
              ["base_url（接口地址）", C.cyan],
              ["allowed_models（允许模型）", C.mint],
              ["skip_ssl_verify（跳过 SSL 校验）", C.coral],
            ]),
          ],
        ),
        column(
          { name: "llm-right", width: fill, height: fill, gap: 28, justify: "center" },
          [
            miniStep("自定义 Provider（供应商）", "OpenAI/Anthropic/Gemini/OpenRouter 之外，可以接入组织自己的模型网关。", C.blue),
            miniStep("测试连接更真实", "测试按钮改用 chat completion（对话补全）验证，并返回更具体错误信息。", C.mint),
            miniStep("LLM Proxy（大模型代理）成为硬依赖", "团队 Key（密钥）走统一代理，减少直写实例配置造成的绕路和不一致。", C.coral),
          ],
        ),
      ],
    ),
    footer("代表提交：refactor(backend): API + Service 层重构为 model-providers / provider-configs"),
  ],
);

slideShell(
  presentation,
  { background: C.ink },
  [
    header("05 灾备", "实例灾备上线：备份、恢复、克隆、重建闭环", "生产环境真正需要的是“坏了能回来、要复制能复制、资源丢了能重建”。", true),
    grid(
      {
        name: "backup-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1), fr(1), fr(1)],
        columnGap: 34,
      },
      [
        miniStepDark("Backup（备份）", "Pod 内打包 RuntimeSpec.backup_dirs（运行时备份目录）并上传 S3（对象存储）。", C.mint),
        miniStepDark("Restore（恢复）", "从备份覆盖原实例数据，并复用部署进度 SSE（服务端推送）。", C.cyan),
        miniStepDark("Clone（克隆）", "备份 → 新实例部署 → 数据恢复，形成可复制办公室资产。", C.amber),
        miniStepDark("Rebuild（重建）", "DB（数据库）记录仍在时，重建 Namespace/PVC/Deployment/Service/Ingress/NetworkPolicy。", C.coral),
      ],
    ),
    row(
      { name: "backup-pills", width: fill, height: hug, gap: 14 },
      [
        pill("Portal（用户门户）", C.mint, "#8AE6B01A"),
        pill("Admin（管理后台）", C.cyan, "#52D1DC1A"),
        pill("操作审计 Hook（钩子）", C.amber, "#F6C85F1A"),
      ],
    ),
    footer("代表提交：feat(backend): 新建 backup_service — 备份/恢复/克隆核心逻辑"),
  ],
);

slideShell(
  presentation,
  { background: C.paper },
  [
    header("06 任务与绩效", "任务与绩效体系更像“AI 员工管理”了", "四月开始把任务结果、失败原因、Token（令牌）成本和 ROI（投入产出比）放到同一张运营视图里。"),
    grid(
      {
        name: "perf-grid",
        width: fill,
        height: fill,
        columns: [fr(0.85), fr(1.15)],
        columnGap: 82,
      },
      [
        column(
          { name: "perf-metrics", width: fill, height: fill, gap: 30, justify: "center" },
          [
            openMetric("failed", "任务新增失败状态", C.coral),
            openMetric("3+", "连续失败触发提醒", C.amber),
            openMetric("ROI", "按每 1k Token 计算产出", C.blue),
          ],
        ),
        column(
          { name: "perf-copy", width: fill, height: fill, gap: 28, justify: "center" },
          [
            miniStep("Schedule（定时任务）失败追踪", "timeout_minutes（超时分钟数）、consecutive_failures（连续失败次数）、last_succeeded_at（上次成功时间）进入模型。", C.amber),
            miniStep("TaskKanban（任务看板）更接近真实工作流", "失败任务展示 failure_reason（失败原因），历史任务按列滚动分页。", C.coral),
            miniStep("AI 员工绩效与全局工资单", "按 Agent（AI 员工）汇总完成率、失败数、Token（令牌）消耗、价值产出和 ROI（投入产出比）。", C.blue),
          ],
        ),
      ],
    ),
    footer("代表提交：feat(portal): AI 员工绩效面板 + 全局工资单页面"),
  ],
);

slideShell(
  presentation,
  { background: C.paper2 },
  [
    header("07 运行底座", "网络、存储、运行时管理更完整", "底层配置不再藏在部署脚本里，而是逐步进入组织设置、集群详情和版本目录。"),
    grid(
      {
        name: "runtime-grid",
        width: fill,
        height: fill,
        columns: [fr(1), fr(1), fr(1)],
        columnGap: 48,
      },
      [
        column(
          { name: "runtime-network", width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("NetworkPolicy", { width: fill, height: hug, style: { ...monoStyle(C.blue, 36), letterSpacing: 0 } }),
            text("（网络策略）", { width: fill, height: hug, style: bodyStyle(C.text, 28) }),
            rule({ width: fixed(160), stroke: C.blue, weight: 5 }),
            text("Ingress/Egress（入站/出站）独立开关，CE/EE 通用。", { width: fill, height: hug, style: bodyStyle(C.muted, 23) }),
          ],
        ),
        column(
          { name: "runtime-storage", width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("StorageClass", { width: fill, height: hug, style: { ...monoStyle(C.cyan, 36), letterSpacing: 0 } }),
            text("（存储类）", { width: fill, height: hug, style: bodyStyle(C.text, 28) }),
            rule({ width: fixed(160), stroke: C.cyan, weight: 5 }),
            text("管理员启用列表进入集群详情，创建实例时只展示可用项。", { width: fill, height: hug, style: bodyStyle(C.muted, 23) }),
          ],
        ),
        column(
          { name: "runtime-version", width: fill, height: fill, gap: 22, justify: "center" },
          [
            text("EngineVersion", { width: fill, height: hug, style: { ...monoStyle(C.coral, 36), letterSpacing: 0 } }),
            text("（引擎版本目录）", { width: fill, height: hug, style: bodyStyle(C.text, 28) }),
            rule({ width: fixed(160), stroke: C.coral, weight: 5 }),
            text("OpenClaw/Nanobot 版本、release_notes（发布说明）、默认版本可管理。", { width: fill, height: hug, style: bodyStyle(C.muted, 23) }),
          ],
        ),
      ],
    ),
    footer("代表提交：feat(backend): 引擎版本目录 + StorageClass 启用管理 + NetworkPolicy 独立开关"),
  ],
);

slideShell(
  presentation,
  { background: C.ink },
  [
    header("收束", "四月：NoDeskClaw 走向 AI 员工运营平台", "如果要对外分享，可以把这个月的更新讲成一条从基础设施到组织运营的产品升级路径。", true),
    grid(
      {
        name: "closing-grid",
        width: fill,
        height: fill,
        columns: [fr(1.15), fr(0.85)],
        columnGap: 78,
      },
      [
        column(
          { name: "closing-left", width: fill, height: fill, gap: 28, justify: "center" },
          [
            text("可部署、可路由、可恢复、可度量、可治理。", {
              width: wrap(1050),
              height: hug,
              style: titleStyle(C.white, 60),
            }),
            text("这不是“增加了几个管理页面”，而是平台边界在变清楚：实例在哪里、消息去哪儿、失败怎么发现、成本怎么算、版本怎么控。", {
              width: wrap(980),
              height: hug,
              style: bodyStyle("#C7D8E4", 27),
            }),
          ],
        ),
        column(
          { name: "closing-right", width: fill, height: fill, gap: 24, justify: "center" },
          [
            pill("多集群承载", C.mint, "#8AE6B01A"),
            pill("拓扑可控协作", C.cyan, "#52D1DC1A"),
            pill("模板资产复用", C.amber, "#F6C85F1A"),
            pill("模型统一入口", C.coral, "#FF6B6B1A"),
            pill("灾备与绩效闭环", C.mint, "#8AE6B01A"),
            pill("网络存储版本治理", C.cyan, "#52D1DC1A"),
          ],
        ),
      ],
    ),
    footer("建议标题：NoDeskClaw 2026 年 4 月产品更新"),
  ],
);

const previewPaths = [];
const slideCount = presentation.slides.count;
logStep(`slides prepared: ${slideCount}`);
for (let i = 0; i < slideCount; i += 1) {
  const slide = presentation.slides.getItem(i);
  const canvas = new Canvas(W, H);
  const ctx = canvas.getContext("2d");
  logStep(`render slide ${i + 1}`);
  try {
    await drawSlideToCtx(slide, presentation, ctx);
  } catch (error) {
    console.error(`[ppt] render slide ${i + 1} failed`);
    console.error(JSON.stringify(formatError(error), null, 2));
    throw error;
  }
  const out = path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`);
  await canvas.toFile(out);
  previewPaths.push(out);
}

let pptxBlob;
try {
  logStep("export pptx");
  pptxBlob = await PresentationFile.exportPptx(presentation);
  await pptxBlob.save(pptxPath);
} catch (error) {
  console.error("[ppt] export failed");
  console.error(JSON.stringify(formatError(error), null, 2));
  throw error;
}

const thumbW = 480;
const thumbH = 270;
const cols = 2;
const rowsCount = Math.ceil(previewPaths.length / cols);
const montage = new Canvas(thumbW * cols, thumbH * rowsCount);
const mctx = montage.getContext("2d");
mctx.fillStyle = "#F7F9F6";
mctx.fillRect(0, 0, montage.width, montage.height);
const { loadImage } = await import(artifactRequire.resolve("skia-canvas"));
for (let i = 0; i < previewPaths.length; i += 1) {
  const img = await loadImage(previewPaths[i]);
  const x = (i % cols) * thumbW;
  const y = Math.floor(i / cols) * thumbH;
  mctx.drawImage(img, x, y, thumbW, thumbH);
}
await montage.toFile(montagePath);

const manifest = {
  pptxPath,
  previewPaths,
  montagePath,
  slideCount,
};
await fs.writeFile(path.join(previewDir, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(JSON.stringify(manifest, null, 2));
