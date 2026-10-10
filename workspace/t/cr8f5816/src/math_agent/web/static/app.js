"use strict";

const state = { csrf: "", run: null, runs: [], caps: {}, events: [], recheckFeedback: {}, repairGuidance: {}, selected: localStorage.getItem("math-agent-run"), fingerprint: "", busy: false, polling: false, editing: false, epoch: 0, healthCheckedAt: 0 };
const main = document.querySelector("#main");
const statuses = { CREATED: "等待输入", INPUT_VALIDATING: "检查输入", PLANNING: "生成计划", AWAITING_PLAN_INPUT: "等待您的选择", PLAN_READY: "计划可确认", PLAN_CONFIRMED: "计划已确认", QUEUED: "已加入队列", BUILDING: "正在生成与编译", LOCAL_REVIEW: "逐节检查", REPAIRING: "修复中", GLOBAL_REVIEW: "全文检查", AWAITING_USER_REVIEW: "等待逐页复核", COMPLETED: "已完成", COMPLETED_WITH_WARNINGS: "已完成（有限制）", BLOCKED: "条件阻塞", FAILED: "执行失败", CANCELLED: "已取消" };
const activeStatuses = ["PLANNING", "INPUT_VALIDATING", "QUEUED", "BUILDING", "LOCAL_REVIEW", "REPAIRING", "GLOBAL_REVIEW"];
const planningStatuses = ["AWAITING_PLAN_INPUT", "PLAN_READY"];
const el = (tag, text, attrs = {}) => {
  const node = document.createElement(tag);
  if (text !== null && text !== undefined) node.textContent = String(text);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "checked" || key === "disabled" || key === "hidden") node[key] = Boolean(value);
    else node.setAttribute(key, value);
  }
  return node;
};
const append = (parent, ...children) => { children.filter(Boolean).forEach(child => parent.append(child)); return parent; };
const pretty = value => typeof value === "string" ? value : JSON.stringify(value, null, 2);
function notify(message) {
  const box = document.querySelector("#notice");
  box.replaceChildren(el("span", message));
  const close = el("button", "×", { "aria-label": "关闭错误提示" }); close.onclick = () => { box.hidden = true; };
  box.append(close); box.hidden = false;
}
async function api(path, data, method) {
  const options = { method: method || (data === undefined ? "GET" : "POST"), credentials: "same-origin", headers: {} };
  if (data !== undefined) {
    options.headers["X-CSRF-Token"] = state.csrf;
    if (data instanceof FormData) options.body = data;
    else { options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(data); }
  }
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body.error?.message || body.detail || `请求失败 (${response.status})`;
    const error = new Error(typeof message === "string" ? message : pretty(message)); error.status = response.status; throw error;
  }
  return body;
}
async function action(fn) {
  if (state.busy) return;
  state.busy = true; state.epoch++;
  const buttons = [...main.querySelectorAll("button")]; buttons.forEach(b => { b.dataset.disabledBefore = String(b.disabled); b.disabled = true; });
  try { await fn(); } catch (error) { notify(error.message); if (error.status === 409) await refreshRun(true); }
  finally { state.busy = false; buttons.filter(b => b.isConnected).forEach(b => { b.disabled = b.dataset.disabledBefore === "true"; }); }
}
function button(label, handler, className = "", attrs = {}) {
  const b = el("button", label, { type: "button", class: className, ...attrs }); b.onclick = () => action(handler); return b;
}
function field(label, input, help) { const box = el("label", null, { class: "form-field" }); append(box, el("span", label), input, help ? el("small", help, { class: "hint" }) : null); return box; }
function card(title) { return append(el("section", null, { class: "card" }), el("h2", title)); }
function detail(title, value, open = false) { return append(el("details", null, open ? { open: "" } : {}), el("summary", title), el("pre", pretty(value))); }
function badge(status) { return el("span", statuses[status] || status, { class: `status-pill ${String(status).toLowerCase()}`, "data-testid": "run-status", "data-status": status }); }
const artifactUrl = artifact => `/api/artifacts/${encodeURIComponent(artifact.artifact_id)}`;
function templateInfo() { return state.caps.templates || state.caps.themes || {}; }
function fduInfo() { return templateInfo().fduclassroom || { available: false, reason: "尚未取得模板检查结果" }; }
function inputOf(run) { return run.input || run.input_data || {}; }
function titleOf(run) { return run.plan?.title || inputOf(run).topic || (run.workflow_id === "beamer.from_tex" ? "讲义转 Beamer" : "新讲义"); }
const modelIds = ["gpt6", "deepseek-flash", "deepseek-v4-pro"];
function availableModels() {
  const configured = state.caps.settings?.models || [];
  return modelIds.map(id => configured.find(model => model.id === id) || { id, label: id, configured: id === "gpt6" && Boolean(state.caps.settings?.live_enabled && state.caps.settings?.key_configured) });
}
function modelLabel(id) { return availableModels().find(model => model.id === id)?.label || id || "尚无调用"; }
function preferredModel(run) { return run.model_routing?.preferred_model_id || inputOf(run).model_id || "gpt6"; }
function fallbackOrder(preferred) { return [preferred, ...modelIds.filter(id => id !== preferred)]; }
async function refreshList() {
  const result = await api("/api/runs"); state.runs = Array.isArray(result) ? result : result.runs || [];
  const list = document.querySelector("#run-list"); list.replaceChildren();
  if (!state.runs.length) list.append(el("p", "还没有任务", { class: "hint" }));
  for (const run of state.runs) {
    const b = el("button", null, { class: `run-link ${state.selected === run.id ? "active" : ""}`, type: "button" });
    append(b, el("strong", titleOf(run)), el("small", `${statuses[run.status] || run.status} · ${inputOf(run).provider === "live" ? modelLabel(preferredModel(run)) : "MOCK"}`));
    b.onclick = () => action(() => selectRun(run.id)); list.append(b);
  }
}
async function selectRun(id) {
  state.selected = id; state.fingerprint = ""; state.events = []; state.editing = false; localStorage.setItem("math-agent-run", id);
  await refreshRun(true); await refreshList();
}
async function refreshRun(force = false) {
  if (!state.selected) return;
  const id = state.selected; const epoch = state.epoch;
  const run = await api(`/api/runs/${encodeURIComponent(id)}`);
  if (id !== state.selected || epoch !== state.epoch) return;
  state.run = run;
  const fingerprint = JSON.stringify([run.status, run.stage, run.plan?.hash, run.approval, run.error, run.artifacts, run.reviews, run.jobs, run.quality_report, run.budget, run.partial_checkpoints, run.model_routing, run.feedback_review, run.repair_guidance_context]);
  if (force || fingerprint !== state.fingerprint) { state.fingerprint = fingerprint; renderRun(run); }
  const events = await api(`/api/runs/${id}/events?after=${state.events.at(-1)?.sequence || 0}`);
  if (id !== state.selected || epoch !== state.epoch) return;
  state.events.push(...(Array.isArray(events) ? events : events.events || []));
  renderEvents();
}
function renderCapabilities() {
  const container = document.querySelector("#capabilities"); container.replaceChildren();
  const fdu = fduInfo();
  append(container, el("p", "默认模板：可选"), el("p", `FDU Classroom：${fdu.available ? "可选" : "不可用"}`));
  container.append(el("p", availableModels().some(model => model.configured) ? "真实 API：环境已配置，能力以实际检查记录为准" : "真实 API：未配置或未启用"));
  for (const model of availableModels()) container.append(el("p", `${model.label}：${model.configured ? "已配置（即时可用性未保证）" : "未配置或未启用"}`));
  if (!fdu.available) container.append(el("p", pretty(fdu.reason || fdu.missing || fdu.issues || "资源不完整"), { class: "hint" }));
  container.append(detail("本机检查详情", state.caps));
}
function renderNew() {
  state.selected = null; state.run = null; state.fingerprint = ""; state.events = []; state.editing = false; state.epoch++; localStorage.removeItem("math-agent-run");
  main.replaceChildren(el("div", "MATH TEACHING", { class: "eyebrow" }), el("h1", "从一份清楚的教学计划开始"), el("p", "确定内容范围，再逐节生成、检查与交付。", { class: "lead" }));
  const form = el("form", null, { id: "new-run-form" }); const inputCard = card("1. 选择任务与输入");
  const workflow = el("select", null, { id: "workflow", name: "workflow_id" });
  append(workflow, el("option", "专题 → 数学讲义", { value: "lecture.generate" }), el("option", "上传讲义 TeX → Beamer", { value: "beamer.from_tex" }));
  inputCard.append(field("工作流", workflow));
  const lectureFields = el("div");
  const topic = el("input", null, { id: "topic", type: "text", placeholder: "例如：数列与数列极限", required: "", maxlength: "500" });
  const difficulty = el("input", null, { id: "difficulty", type: "text", value: "经济学本科一年级微积分", required: "", maxlength: "500" });
  append(lectureFields, field("数学专题", topic), field("难度范围", difficulty, "可修改为实际教学对象和先修程度。")); inputCard.append(lectureFields);
  const beamerFields = el("div", null, { hidden: true });
  const file = el("input", null, { id: "source-file", type: "file", accept: ".tex,.zip" });
  const mainFile = el("input", null, { id: "main-file", type: "text", placeholder: "多个 TeX 入口时填写，例如：讲义/main.tex" });
  const theme = el("select", null, { id: "theme" }); const fdu = fduInfo();
  append(theme, el("option", "默认模板", { value: "default" }), el("option", `FDU Classroom（用户样例主题）${fdu.available ? "" : " · 不可用"}`, { value: "fduclassroom", disabled: !fdu.available }));
  append(beamerFields, field("讲义文件", file, "支持 TeX 或包含主文件、图片及依赖的 ZIP。原始资料保留为不可变快照。"), field("ZIP 中的主文件（可选）", mainFile), field("课件主题", theme));
  const bibliography = el("input", null, { id: "reference-bibliography", type: "checkbox", disabled: !state.caps.reference_manuscript?.available });
  beamerFields.append(append(el("label", null, { class: "check-label" }), bibliography, el("span", "从本地完整原稿补齐已引用的真实书目（仅生成副本，确认计划前展示条目和出处）")));
  if (!state.caps.reference_manuscript?.available) beamerFields.append(el("p", "尚未找到本地完整原稿，书目补齐不可用。", { class: "hint" }));
  if (!fdu.available) beamerFields.append(el("p", `FDU 不可用：${pretty(fdu.reason || fdu.missing || fdu.issues || "主题资源尚未检查")}`, { class: "notice-inline" }));
  inputCard.append(beamerFields);
  workflow.onchange = () => { const isBeamer = workflow.value === "beamer.from_tex"; lectureFields.hidden = isBeamer; beamerFields.hidden = !isBeamer; topic.required = !isBeamer; difficulty.required = !isBeamer; file.required = isBeamer; };
  const settingsCard = card("2. 运行方式");
  const provider = el("select", null, { id: "provider" });
  const models = availableModels();
  const liveReady = models.some(model => model.configured);
  append(provider, el("option", "MOCK · 离线流程测试（不调用真实模型）", { value: "mock" }), el("option", liveReady ? "真实 API · 环境已配置，能力以检查记录为准" : "真实 API · 未配置或未启用", { value: "live" }));
  provider.value = liveReady ? "live" : "mock";
  const model = el("select", null, { id: "model-id", name: "model_id" });
  for (const item of models) model.append(el("option", item.label, { value: item.id }));
  model.value = "gpt6";
  const modelHelp = el("p", null, { class: "hint", id: "model-selection-help" });
  const disclosure = el("p", null, { class: "notice-inline", id: "provider-disclosure" });
  function updateProviderChoice() {
    const selected = models.find(item => item.id === model.value);
    model.disabled = provider.value !== "live";
    modelHelp.textContent = provider.value === "live" ? `${selected.configured ? "所选模型环境已配置；即时可用性以实际请求为准。" : "所选模型未配置或未启用；后端将检查其他已配置模型。"} 调用失败时依次尝试：${fallbackOrder(model.value).map(modelLabel).join(" → ")}。切换仅用于当前调用，后续调用仍优先使用所选模型。` : "MOCK 不调用所选真实模型。改用真实 API 时，默认首选 gpt6。";
    disclosure.textContent = provider.value === "live" ? (liveReady ? "" : "当前真实 API 未配置或未启用。请按 README 设置后端环境变量并重启服务；未就绪的任务会明确显示阻塞原因。") + "讲义文字及必要参考片段将发送到所选或自动切换后的模型接口。密钥只由后端环境变量读取。" : "MOCK 使用合成内容，仅验证工作流；不代表真实模型教学能力验收通过。";
  }
  provider.onchange = updateProviderChoice; model.onchange = updateProviderChoice; updateProviderChoice();
  append(settingsCard, field("模型来源", provider), field("首选模型", model), modelHelp, disclosure);
  const trust = el("input", null, { id: "trusted-input", type: "checkbox", required: "" });
  append(settingsCard, append(el("label", null, { class: "check-label" }), trust, el("span", "我确认本次输入及模板来自可信来源。当前使用本机原生 TeX 编译，它不是隔离沙箱。")));
  const submit = el("button", "保存输入并生成计划", { class: "primary", type: "submit", id: "create-run" });
  append(form, inputCard, settingsCard, append(el("div", null, { class: "actions" }), submit)); main.append(form);
  form.onsubmit = event => { event.preventDefault(); action(async () => {
    if (!form.reportValidity()) return;
    const isBeamer = workflow.value === "beamer.from_tex";
    const run = await api("/api/runs", { workflow_id: workflow.value, topic: isBeamer ? file.files[0].name : topic.value.trim(), difficulty: difficulty.value.trim(), provider: provider.value, model_id: model.value, trusted_input: trust.checked, theme: theme.value, use_reference_bibliography: isBeamer && bibliography.checked });
    state.selected = run.id; localStorage.setItem("math-agent-run", run.id);
    if (isBeamer) { const data = new FormData(); data.append("file", file.files[0]); if (mainFile.value.trim()) data.append("main_file", mainFile.value.trim()); await api(`/api/runs/${run.id}/attachments`, data); }
    await api(`/api/runs/${run.id}/plan`, {}); await selectRun(run.id);
  }); };
  refreshList().catch(error => notify(error.message));
}
function renderRun(run) {
  main.replaceChildren(); const input = inputOf(run); const isMock = input.provider !== "live";
  const heading = el("div", null, { class: "run-heading" });
  append(heading, append(el("div"), el("div", run.workflow_id === "beamer.from_tex" ? "LECTURE → BEAMER" : "TOPIC → LECTURE", { class: "eyebrow" }), el("h1", titleOf(run)), el("p", `任务 ${run.id}`, { class: "hash" })), append(el("div"), badge(run.status), el("span", isMock ? "MOCK · 合成内容" : "真实 API", { class: `tag ${isMock ? "mock" : "live"}` }))); main.append(heading);
  const current = ["CREATED", "INPUT_VALIDATING"].includes(run.status) ? 0 : ["PLANNING", ...planningStatuses].includes(run.status) ? 1 : run.status === "PLAN_CONFIRMED" ? 2 : ["AWAITING_USER_REVIEW", "COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(run.status) ? 4 : 3;
  const steps = el("ol", null, { class: "steps", "aria-label": "工作流阶段" }); ["输入", "协作计划", "确认", "生成与检查", "复核与交付"].forEach((label, index) => steps.append(el("li", label, { class: index === current ? "current" : index < current ? "done" : "" }))); main.append(steps);
  if (isMock) main.append(el("p", "当前任务为 MOCK。可检查计划、编译和文件流程；数学内容与模型复核属于合成测试证据。", { class: "notice-inline" }));
  renderModelRouting(run);
  if (run.error) main.append(append(el("section", null, { class: "error-panel", role: "status" }), el("strong", "当前步骤未完成"), el("p", pretty(run.error)), el("small", `恢复节点：${run.stage || "待诊断"}。已确认计划和既有产物保留。`)));
  if (run.status === "CREATED" || (["FAILED", "BLOCKED"].includes(run.status) && !run.plan && !run.approval)) renderPendingInput(run);
  if (run.plan) renderPlan(run);
  if ((planningStatuses.includes(run.status) || (run.status === "PLAN_CONFIRMED" && state.editing)) && run.plan) renderDecisions(run);
  renderBudget(run);
  renderExecution(run);
  renderRepairGuidance(run);
  renderFeedbackReview(run);
  renderPartialCheckpoints(run);
  renderArtifacts(run);
  const eventsCard = card("任务事件"); eventsCard.append(el("ul", null, { id: "event-list", class: "event-list" })); main.append(eventsCard); renderEvents();
}
function renderModelRouting(run) {
  const input = inputOf(run), routing = run.model_routing || {}, preferred = preferredModel(run);
  const c = card("模型调用"); c.id = "model-routing";
  const entries = el("dl", null, { class: "model-routing-details" });
  append(entries, el("dt", "首选模型"), el("dd", modelLabel(preferred), { id: "preferred-model" }),
    el("dt", "最近实际调用"), el("dd", input.provider === "live" ? modelLabel(routing.last_model_id) : "MOCK · 未调用真实模型", { id: "last-model" }));
  if (input.provider === "live") {
    append(entries, el("dt", "最近有效返回"), el("dd", routing.last_successful_model_id ? modelLabel(routing.last_successful_model_id) : "尚无通过结构校验的返回", { id: "last-successful-model" }),
      el("dt", "自动尝试顺序"), el("dd", (routing.fallback_order || fallbackOrder(preferred)).map(modelLabel).join(" → "), { id: "model-fallback-order" }),
      el("dt", "已调用模型"), el("dd", (routing.used_models || []).map(modelLabel).join("、") || "尚无调用", { id: "used-models" }),
      el("dt", "自动切换"), el("dd", `${routing.fallback_count || 0} 次`, { id: "model-fallback-count" }));
  }
  c.append(entries);
  if (input.provider === "live") append(c, el("p", "HTTP 超时等接口故障会触发临时切换。后续调用仍优先使用首选模型；各次尝试继续计入现有请求预算。模型有返回不代表数学检查通过。", { class: "hint" }), el("ul", null, { id: "model-fallback-events", class: "model-fallback-events" }));
  main.append(c);
}
function renderPendingInput(run) {
  const c = card("继续准备输入");
  if (run.workflow_id === "beamer.from_tex") {
    const upload = el("input", null, { type: "file", accept: ".tex,.zip", id: "resume-source" });
    const entry = el("input", null, { type: "text", id: "resume-main-file", placeholder: "ZIP 中的主文件（可选）" });
    append(c, field("上传完整讲义资源", upload), field("主文件", entry), button("保存文件", async () => { if (!upload.files[0]) throw new Error("请先选择 TeX 或 ZIP 文件"); const data = new FormData(); data.append("file", upload.files[0]); if (entry.value.trim()) data.append("main_file", entry.value.trim()); await api(`/api/runs/${run.id}/attachments`, data); await refreshRun(true); }));
  }
  c.append(button("生成计划", async () => { await api(`/api/runs/${run.id}/plan`, {}); await refreshRun(true); }, "primary")); main.append(c);
}
function renderPlan(run) {
  const plan = run.plan; const c = card(`内容计划 · 版本 ${plan.revision}`);
  append(c, el("p", `模板：${plan.theme === "fduclassroom" ? "FDU Classroom（用户样例主题）" : "默认模板"} · 难度：${inputOf(run).difficulty || "以原讲义为准"}`, { class: "hint" }));
  if (Array.isArray(plan.theme_adaptations) && plan.theme_adaptations.length) {
    const adaptations = append(el("section", null, { class: "card compact", "aria-label": "模板适配说明" }), el("h3", "本计划的模板适配"));
    const list = el("ul");
    for (const description of plan.theme_adaptations) list.append(el("li", description));
    append(adaptations, list, el("p", "确认当前计划时，将一并确认以上模板适配。", { class: "hint" }));
    c.append(adaptations);
  }
  if (plan.objectives) c.append(detail("教学目标", plan.objectives));
  const sections = el("ol", null, { class: "section-list" });
  for (const section of plan.sections || []) {
    const li = el("li", section.title || section.id);
    append(li, el("small", `来源单元：${(section.source_unit_ids || []).join("、") || "按讲义计划生成"}`));
    const specs = Object.fromEntries(Object.entries(section).filter(([key]) => !["id", "title", "source_unit_ids"].includes(key)));
    if (Object.keys(specs).length) li.append(detail("本节内容与分页安排", specs)); sections.append(li);
  }
  c.append(sections);
  if (planningStatuses.includes(run.status) || run.status === "PLAN_CONFIRMED") {
    const editor = append(el("details", null, { id: "outline-editor" }), el("summary", "编辑专题与章节标题"), el("p", "保存会生成新的内容计划版本；已确认的计划需要重新确认。未保存的标题不会进入构建。", { class: "hint" }));
    const form = el("form", null, { id: "outline-form" });
    const title = el("input", null, { id: "outline-title", type: "text", value: plan.title || "", required: "", maxlength: "200" });
    form.append(field("文档标题", title));
    const titles = [];
    for (const section of plan.sections || []) {
      const input = el("input", null, { type: "text", value: section.title || "", required: "", maxlength: "200", "data-section-title-id": section.id });
      form.append(field(`${section.id} 章节标题`, input)); titles.push({ id: section.id, input });
    }
    form.append(el("button", "保存大纲修改", { type: "submit", class: "primary", id: "save-outline" }));
    form.onsubmit = event => { event.preventDefault(); action(async () => {
      if (!form.reportValidity()) return;
      const sectionTitles = Object.fromEntries(titles.map(item => [item.id, item.input.value.trim()]));
      if (!title.value.trim() || Object.values(sectionTitles).some(value => !value)) throw new Error("文档和章节标题不能为空。");
      await api(`/api/runs/${run.id}/plan/revise`, { expected_plan_revision: plan.revision, title: title.value.trim(), section_titles: sectionTitles });
      state.editing = false; await refreshRun(true); await refreshList();
    }); };
    editor.append(form); c.append(editor);
  }
  if (plan.lecture) {
    const labels = { proof_policy: "证明深度", example_focus: "例题侧重", exercises: "练习与答案", answers_location: "答案位置" };
    const values = { key: "关键定理完整证明，其余给出说明", all: "所有定理完整证明", balanced: "概念与计算均衡", economics: "更多经济应用", with_answers: "安排练习并附答案", none: "不安排额外练习", section: "各节之后", end: "讲义末尾" };
    const settings = append(el("div", null, { class: "lecture-settings" }), el("h3", "计划中的讲义设置"), el("p", "以下为已保存的计划要求；生成后的具体落实情况仍需结合检查证据核对。", { class: "hint" }));
    const list = el("dl");
    for (const [key, label] of Object.entries(labels)) {
      const value = plan.lecture[key];
      const text = value === null || value === undefined ? "尚未选择" : typeof value === "object" && value.custom ? `自定义：${value.custom}` : values[value] || String(value);
      append(list, el("dt", label), el("dd", text));
    }
    append(settings, list, detail("查看设置数据", plan.lecture)); c.append(settings);
  }
  if (plan.diff) c.append(detail("本次计划变更（diff）", plan.diff, true));
  if (plan.omissions?.length) c.append(detail("删除授权与依赖影响", plan.omissions, true));
  if (plan.additions?.length) c.append(detail("新增内容与插入位置", plan.additions, true));
  if (plan.source_enrichment) c.append(detail("从完整原稿补齐的书目与出处（本次确认范围）", plan.source_enrichment, true));
  if (plan.rules) c.append(detail("固定内容与版式规则", plan.rules));
  if (plan.source_issues?.length) c.append(detail("源讲义解析与依赖问题", plan.source_issues, true));
  if (plan.template_status) c.append(detail("实际模板资源与哈希", plan.template_status));
  if (plan.decisions?.length || run.decisions?.length) c.append(detail("用户选择记录", plan.decisions || run.decisions));
  if (plan.risks?.length || plan.unresolved_blocking_questions?.length) c.append(detail("仍需处理的问题", plan.risks || plan.unresolved_blocking_questions, true));
  c.append(el("p", `计划 SHA-256：${plan.hash}`, { class: "hash" }));
  if (run.approval) {
    c.append(el("p", "此计划已有用户确认记录。普通失败可从原节点恢复，无需重新确认。", { class: "hint" }));
    if (run.status === "PLAN_CONFIRMED") c.append(button(state.editing ? "放弃本次未保存修改" : "修改计划（保存后重新确认）", async () => { state.editing = !state.editing; renderRun(run); }));
  }
  else if (planningStatuses.includes(run.status)) c.append(button("确认当前计划", async () => { await api(`/api/runs/${run.id}/plan/confirm`, { expected_plan_revision: plan.revision, expected_plan_hash: plan.hash, action_id: crypto.randomUUID() }); await refreshRun(true); await refreshList(); }, "primary", { id: "confirm-plan", disabled: run.status === "AWAITING_PLAN_INPUT" || Boolean(plan.unresolved_blocking_questions?.length) }));
  main.append(c);
}
function renderDecisions(run) {
  const plan = run.plan; const c = card("协作选择");
  c.append(el("p", "提交后会生成新的计划版本，并展示变更。推荐项需要由您主动选择。", { class: "hint" }));
  const form = el("form", null, { id: "decisions-form" });
  const questions = plan.questions || []; const entries = [];
  for (const q of questions) {
    const fieldset = el("fieldset", null, { class: "question", "data-question-id": q.id });
    append(fieldset, el("legend", q.prompt), q.reason ? el("p", q.reason, { class: "hint" }) : null);
    const choices = el("div", null, { class: "choices" }); const inputs = [];
    const saved = (run.decisions || plan.decisions || []).findLast?.(d => d.question_id === q.id);
    const custom = el("textarea", saved?.custom_input || "", { "aria-label": `${q.prompt} — 自定义输入`, class: "custom-input", hidden: !saved?.selected_option_ids?.includes("CUSTOM"), placeholder: "描述具体要求；提交后请核对计划中的解析效果。" });
    for (const option of q.options || []) {
      const input = el("input", null, { type: q.selection_mode === "multiple" ? "checkbox" : "radio", name: `q-${q.id}`, value: option.id, checked: saved?.selected_option_ids?.includes(option.id) || false });
      input.onchange = () => { custom.hidden = !inputs.some(i => i.value === "CUSTOM" && i.checked); };
      const label = append(el("label", null, { class: "choice" }), input, el("span", option.label)); if (option.recommended) label.append(el("small", "推荐")); choices.append(label); inputs.push(input);
    }
    append(fieldset, choices, custom); form.append(fieldset); entries.push({ q, inputs, custom });
  }
  const unitInputs = []; const additionFields = [];
  if (run.workflow_id === "beamer.from_tex") {
    const units = inputOf(run).units || run.units || []; const omissionPanel = el("details");
    append(omissionPanel, el("summary", "删除或调整原讲义内容"), el("p", "勾选精确源单元作为删除候选。相关题解与依赖影响将在新计划中列出，确认计划后才构成授权。未勾选的内容仍保留。", { class: "hint" }));
    const unitList = el("div", null, { class: "source-units" });
    const omitted = new Set((plan.omissions || []).flatMap(o => o.unit_ids || [o.unit_id || o.source_unit_id]).filter(Boolean));
    for (const unit of units) {
      const input = el("input", null, { type: "checkbox", value: unit.id, checked: omitted.has(unit.id), "data-unit-id": unit.id }); unitInputs.push(input);
      const location = (unit.source_spans || []).map(s => `${s.source_name || s.file || "源文件"}:${s.start_line || s.line_start || "?"}`).join("，");
      const box = el("div", null, { class: "unit" });
      append(box, append(el("label"), input, el("span", `${unit.id} · ${unit.kind} · ${unit.section_title || ""}`)), el("small", location, { class: "hint" }), el("pre", unit.raw_tex || unit.text || "")); unitList.append(box);
    }
    if (!units.length) unitList.append(el("p", "未取得可选择的源单元，请检查输入解析报告。", { class: "hint" }));
    omissionPanel.append(unitList); form.append(omissionPanel);
    const additions = el("details"); append(additions, el("summary", "添加原讲义之外的内容"), el("p", "默认不添加。每项必须指定内容、插入位置和优先级；空项不会提交。", { class: "hint" }));
    const additionList = el("div");
    const addRow = (saved = {}) => {
      const row = el("div", null, { class: "card compact" });
      const content = el("textarea", saved.new_content || "", { "aria-label": "新增内容" });
      const location = el("select", null, { "aria-label": "插入位置" });
      append(location, el("option", "请选择实际章节", { value: "" }));
      for (const section of plan.sections || []) location.append(el("option", `${section.id} · ${section.title}`, { value: section.id }));
      location.value = saved.insertion_location || "";
      const priority = el("select", null, { "aria-label": "新增优先级" }); append(priority, el("option", "必须", { value: "必须" }), el("option", "有空间再加入", { value: "有空间再加入" })); priority.value = saved.priority || "必须";
      const remove = el("button", "移除此新增项", { type: "button" }); remove.onclick = () => { row.remove(); };
      append(row, field("新增正文（支持数学 TeX，按输入加入）", content, "填写要加入课件的实际正文；模型不会将这段输入扩写为额外内容。"), field("插入位置", location), field("优先级", priority), remove); additionList.append(row); additionFields.push({ row, content, location, priority });
    };
    (plan.additions || []).forEach(addRow); const add = el("button", "＋ 添加一项", { type: "button", id: "add-content" }); add.onclick = () => addRow(); append(additions, additionList, add); form.append(additions);
  }
  const actions = el("div", null, { class: "actions" });
  if (questions.length) {
    const recommended = el("button", "采用本批推荐项", { type: "button", id: "use-recommended" });
    recommended.onclick = () => { entries.forEach(({ q, inputs, custom }) => { inputs.forEach(input => { input.checked = Boolean(q.options.find(o => o.id === input.value)?.recommended); }); custom.hidden = !inputs.some(i => i.value === "CUSTOM" && i.checked); }); }; actions.append(recommended);
  }
  actions.append(el("button", "保存选择并更新计划", { type: "submit", class: "primary", id: "save-decisions" })); form.append(actions);
  form.onsubmit = event => { event.preventDefault(); action(async () => {
    const decisions = entries.map(({ q, inputs, custom }) => ({ question_id: q.id, question_revision: q.revision, selected_option_ids: inputs.filter(i => i.checked).map(i => i.value), custom_input: custom.value.trim() })).filter(d => d.selected_option_ids.length);
    for (const d of decisions) if (d.selected_option_ids.includes("CUSTOM") && !d.custom_input) throw new Error("选择“自定义输入”后请填写具体要求。");
    const payload = { expected_plan_revision: plan.revision, decisions };
    if (run.workflow_id === "beamer.from_tex") {
      payload.omitted_unit_ids = unitInputs.filter(i => i.checked).map(i => i.value);
      payload.additions = additionFields.filter(f => f.row.isConnected && f.content.value.trim()).map(f => ({ new_content: f.content.value.trim(), insertion_location: f.location.value.trim(), priority: f.priority.value }));
      if (payload.additions.some(a => !a.insertion_location)) throw new Error("每个新增项都需要具体插入位置。");
    }
    await api(`/api/runs/${run.id}/decisions`, payload); state.editing = false; await refreshRun(true);
  }); };
  c.append(form); main.append(c);
}
function renderBudget(run) {
  const budget = run.budget; if (!budget) return;
  const c = card("请求与修复预算"); c.id = "budget-panel";
  c.append(el("p", `模型请求：已用 ${budget.request_count} / 上限 ${budget.requests ?? "历史上限未知"}；每个单元最多修复 ${budget.local_repairs_per_unit} 次；全文最多修复 ${budget.global_repair_rounds} 轮。`, { id: "budget-summary" }));
  c.append(el("p", "增加预算会允许后续更多模型调用；供应商价格未知，不显示估算费用。累计次数、原审批和失败记录都会保留。", { class: "hint" }));
  for (const note of budget.limitations || []) c.append(el("p", note, { class: "notice-inline" }));
  if (budget.can_increase) {
    const details = el("details", null, { id: "budget-editor", ...(run.error?.code === "BUDGET_EXHAUSTED" || budget.baseline_unknown ? { open: "" } : {}) });
    details.append(el("summary", budget.baseline_unknown ? "由我明确确认本任务的新请求上限" : "由我明确增加本任务预算"));
    details.append(el("p", "只填写要提高的新上限，其余留空。保存不会自动执行；之后可从失败节点重试。增加预算不能跳过数学、范围或编译检查。", { class: "hint" }));
    const form = el("form", null, { id: "budget-form" }); const inputs = {};
    for (const [key, label] of [["requests", "模型请求新上限"], ["local_repairs_per_unit", "每个单元修复新上限"], ["global_repair_rounds", "全文修复轮次新上限"]]) {
      const minimum = key === "requests" ? Math.max(budget[key] + 1, budget.request_count + 1) : budget[key] + 1;
      const input = el("input", null, { type: "number", id: `budget-${key}`, min: minimum, max: budget.maximums[key], step: 1, placeholder: budget[key] == null ? "历史上限未知，须明确输入" : `当前 ${budget[key]}，留空不变`, ...(key === "requests" && budget.baseline_unknown ? { required: "" } : {}) });
      inputs[key] = input; form.append(field(label, input, `仅影响当前任务，最高 ${budget.maximums[key]}。`));
    }
    let confirmUnknown;
    if (budget.baseline_unknown) {
      confirmUnknown = el("input", null, { type: "checkbox", id: "budget-confirm-unknown", required: "" });
      form.append(append(el("label", null, { class: "check-label" }), confirmUnknown, el("span", "我确认填写的是新的请求上限；旧上限尚未核验，系统不会宣称它是已知历史预算的增加。原请求计数不会清零。")));
    }
    const note = el("textarea", null, { id: "budget-note", required: "", maxlength: 1000 }); form.append(field("增加预算的说明", note));
    form.append(el("button", budget.baseline_unknown ? "保存我确认的新上限" : "保存增加的预算", { type: "submit", id: "save-budget", class: "primary" }));
    form.onsubmit = event => { event.preventDefault(); action(async () => {
      const updates = {};
      for (const [key, input] of Object.entries(inputs)) if (input.value.trim()) {
        const value = Number(input.value); if (!Number.isInteger(value) || value <= budget[key]) throw new Error("新预算须为严格增加的整数。"); updates[key] = value;
      }
      if (!Object.keys(updates).length || !note.value.trim()) throw new Error("请填写至少一项新上限和增加说明。");
      await api(`/api/runs/${run.id}/budget`, { expected_version: budget.version, expected_plan_revision: run.active_plan_revision ?? null,
        expected_plan_hash: run.plan?.hash ?? null, action_id: crypto.randomUUID(), note: note.value.trim(), confirm_unknown_request_limit: Boolean(confirmUnknown?.checked), ...updates });
      await refreshRun(true); notify("预算已记录；累计次数和原审批保留。需要继续时，请点击从失败节点重试。");
    }); };
    details.append(form); c.append(details);
  }
  main.append(c);
}
function renderPartialCheckpoints(run) {
  const parts = run.partial_checkpoints || []; if (!parts.length) return;
  const c = card("已保存章节 · 部分结果待复核"); c.id = "partial-checkpoints";
  c.append(el("p", "这些文件只覆盖已保存的章节，可能是累计至该节的讲义。全文仍未完成，局部编译成功不代表教师审核通过。", { class: "notice-inline" }));
  for (const part of parts) {
    const details = el("details", null, { "data-partial-section": part.section_id });
    details.append(el("summary", `${part.section_id} · ${part.status} · 局部编译 ${part.compile_status || "待核验"}`));
    details.append(el("p", `${part.plan_binding || "UNKNOWN"} · ${part.plan_binding_notice || "当前计划关联未核验，可能为历史部分结果。"}`, { class: "notice-inline" }));
    details.append(el("p", `保存时间：${part.created_at || "未知"}；检查点 SHA-256 ${part.checkpoint_hash || "未知"}`, { class: "hash" }));
    if (part.reason) details.append(el("p", part.reason, { class: "error-panel" }));
    for (const file of part.downloads || []) details.append(append(el("a", null, { href: file.url, class: "partial-link artifact-link-partial", "data-partial-id": file.id, target: "_blank", rel: "noopener" }),
      el("strong", file.name), el("small", `PARTIAL · SHA-256 ${file.sha256}`, { class: "hash" })));
    c.append(details);
  }
  main.append(c);
}
function renderExecution(run) {
  if (planningStatuses.includes(run.status) || run.status === "CREATED") return;
  const c = card("执行与恢复");
  c.append(el("p", `当前步骤：${run.stage || run.status}`, { id: "run-stage" }));
  for (const job of run.jobs || []) c.append(append(el("div", null, { class: "progress-row" }), el("span", `${job.kind || job.step_key || "任务"} · ${job.id || job.job_id || ""}`), el("span", job.status || "等待")));
  const actions = el("div", null, { class: "actions" });
  if (run.status === "PLAN_CONFIRMED" && !state.editing) actions.append(button("执行已确认计划", async () => { await api(`/api/runs/${run.id}/execute`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash, idempotency_key: `${run.id}:${run.plan.hash}` }); await refreshRun(true); await refreshList(); }, "primary", { id: "execute-plan" }));
  if (run.status === "AWAITING_USER_REVIEW") {
    const previousBuild = (run.jobs || []).filter(job => job.kind === "build").at(-1);
    const feedback = run.workflow_id === "lecture.generate" ? el("textarea", null, { id: "recheck-feedback", rows: "3", maxlength: "10000", placeholder: "例如：增加夹逼法练习，核对两个重要极限的条件" }) : null;
    if (feedback) {
      feedback.value = state.recheckFeedback[run.id] || "";
      feedback.oninput = () => { state.recheckFeedback[run.id] = feedback.value; };
      c.append(field("本轮希望改进的内容（可选）", feedback, "按已批准的教学计划提出建议；系统会核查并修订适用内容。留空则执行常规自动检查。"));
    }
    actions.append(button("重新运行自动检查", async () => {
      await api(`/api/runs/${run.id}/recheck`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash, idempotency_key: `${run.id}:recheck:${previousBuild?.id || run.plan.hash}`, feedback: feedback?.value || "", feedback_source: "user" });
      delete state.recheckFeedback[run.id];
      await refreshRun(true); await refreshList();
    }, "", { id: "recheck-run", disabled: run.budget?.baseline_unknown || (run.jobs || []).some(job => ["queued", "running"].includes(job.status)) }));
    c.append(el("p", "自动复检会重新检查已保存内容并生成本次交付；沿用原计划和累计预算，历史文件保留。此操作不提交人工审核。", { class: "hint" }));
  }
  if (["FAILED", "BLOCKED"].includes(run.status)) actions.append(button("从失败节点重试", async () => { await api(`/api/runs/${run.id}/retry`, {}); await refreshRun(true); }, "primary", { id: "retry-run", disabled: run.budget?.baseline_unknown || run.error?.code === "BUDGET_EXHAUSTED" && (run.budget?.version || 0) <= (run.error.budget_version || 0) }));
  if (activeStatuses.includes(run.status)) actions.append(button("取消任务", async () => { await api(`/api/runs/${run.id}/cancel`, {}); await refreshRun(true); }, "danger", { id: "cancel-run" }));
  if (activeStatuses.includes(run.status)) c.append(el("p", "由独立 worker 处理。可以刷新或关闭页面，稍后从任务列表恢复。", { class: "hint" }));
  c.append(actions); main.append(c);
}
function renderRepairGuidance(run) {
  const context = run.repair_guidance_context;
  if (run.workflow_id !== "lecture.generate" || !["BLOCKED", "FAILED"].includes(run.status) || !run.plan || !context) return;
  if (!/^S\d+$/.test(context.section_id || "") || !/^[0-9a-f]{64}$/.test(context.candidate_hash || "") || !Array.isArray(context.units) || !context.units.length) return;
  const units = context.units.filter(unit => typeof unit.id === "string" && unit.id.startsWith(`${context.section_id}.`) && typeof unit.tex_excerpt === "string");
  if (units.length !== context.units.length || new Set(units.map(unit => unit.id)).size !== units.length) return;
  const key = JSON.stringify([run.id, run.plan.revision, run.plan.hash, context.section_id, context.candidate_hash]);
  const draft = state.repairGuidance[key] || (state.repairGuidance[key] = { unit_id: "", instructions: "", action_id: null, submitted_signature: null });
  const c = card("补充单元修复指导"); c.id = "repair-guidance-panel";
  c.append(el("p", "仅指导您选择的一个单元。提交后继续原任务，仍须经过数学审阅、编译和交付检查；这不是教师批准。", { class: "hint" }));
  const form = el("form", null, { id: "repair-guidance-form" });
  const target = el("select", null, { id: "repair-guidance-unit", required: "" });
  target.append(el("option", "请选择需要指导的单元", { value: "" }));
  for (const unit of units) target.append(el("option", `${unit.id} · ${unit.kind || "正文"}`, { value: unit.id }));
  target.value = units.some(unit => unit.id === draft.unit_id) ? draft.unit_id : "";
  const excerpt = el("pre", null, { id: "repair-guidance-excerpt", class: "hint" });
  const instructions = el("textarea", null, { id: "repair-guidance-instructions", required: "", minlength: 20, maxlength: 20000, rows: 8 });
  instructions.value = draft.instructions;
  const saveDraft = () => {
    if (draft.unit_id !== target.value || draft.instructions !== instructions.value) {
      draft.action_id = null; draft.submitted_signature = null;
    }
    draft.unit_id = target.value; draft.instructions = instructions.value;
    excerpt.textContent = units.find(unit => unit.id === target.value)?.tex_excerpt || "选择单元后显示当前正文摘要。";
  };
  target.onchange = saveDraft; instructions.oninput = saveDraft;
  excerpt.textContent = units.find(unit => unit.id === target.value)?.tex_excerpt || "选择单元后显示当前正文摘要。";
  append(form, field("修复单元", target), excerpt, field("修复指导", instructions, "请说明具体依据、证明思路或需要保留的条件，20–20000 字。草稿在本页面轮询和提交失败后保留。"));
  form.append(el("button", "提交指导并继续原任务", { type: "submit", id: "submit-repair-guidance", class: "primary", disabled: (run.jobs || []).some(job => ["queued", "running"].includes(job.status)) }));
  form.onsubmit = event => { event.preventDefault(); action(async () => {
    saveDraft();
    const unit = units.find(item => item.id === target.value);
    const text = instructions.value.trim();
    if (!unit || text.length < 20 || text.length > 20000) throw new Error("请选择当前单元，并填写 20–20000 字的具体修复指导。");
    const signature = JSON.stringify([unit.id, text]);
    if (!draft.action_id || draft.submitted_signature !== signature) { draft.action_id = crypto.randomUUID(); draft.submitted_signature = signature; }
    await api(`/api/runs/${run.id}/repair-guidance`, { expected_plan_revision: run.plan.revision, expected_plan_hash: run.plan.hash,
      action_id: draft.action_id, section_id: context.section_id, expected_candidate_hash: context.candidate_hash,
      unit_ids: [unit.id], instructions: text, source: "user" });
    if (JSON.stringify([draft.unit_id, draft.instructions.trim()]) === signature) delete state.repairGuidance[key];
    await refreshRun(true); await refreshList();
    notify("修复指导已记录，原任务已继续；数学与编译检查仍会执行。");
  }); };
  c.append(form); main.append(c);
}

function renderFeedbackReview(run) {
  const receipt = run.workflow_id === "lecture.generate" ? run.feedback_review : null;
  if (!receipt) return;
  const c = card("本轮最近一次反馈核查"); c.id = "feedback-review";
  c.append(el("p", receipt.message || "以下为本轮最近一次自动核查结果。", { id: "feedback-review-message" }));
  if (receipt.timestamp) c.append(el("small", `核查时间：${receipt.timestamp}`));
  const stages = { pending: "等待逐项核查", reviewed: "已形成逐项说明", unresolved: "仍有无法确认的项目", invalid: "回执核对未通过", transport_pending: "模型调用尚未完成" };
  c.append(el("p", `回执阶段：${stages[receipt.status] || "无法确认"}`, { id: "feedback-review-stage", class: "hint" }));
  if (receipt.mock) c.append(el("p", "MOCK 演示回执：不代表真实模型已核实建议。", { class: "notice-inline" }));
  const labels = { satisfied: "已满足", supported_improvement: "待改进", rejected_not_supported: "不适用", out_of_scope: "不适用", unresolved: "无法确认" };
  if (["reviewed", "unresolved", "invalid", "transport_pending"].includes(receipt.status)) {
    const list = el("ol", null, { id: "feedback-review-items" });
    for (const item of receipt.items || []) {
      const row = el("li", null, { "data-feedback-id": item.id, "data-feedback-status": item.status });
      append(row, el("strong", `${item.id} · ${labels[item.status] || "无法确认"}`), el("p", item.reason));
      if (item.unit_ids?.length) row.append(el("p", `相关单元：${item.unit_ids.join("、")}`, { class: "hint" }));
      if (item.repair_unit_ids?.length) row.append(el("p", `建议修改单元：${item.repair_unit_ids.join("、")}`, { class: "hint" }));
      list.append(row);
    }
    c.append(list);
  }
  if (receipt.limitations?.length) {
    c.append(el("p", "自动核查限制：", { class: "hint" }));
    const limitations = el("ul");
    for (const value of receipt.limitations) limitations.append(el("li", value));
    c.append(limitations);
  }
  c.append(el("p", "这是自动核查记录，不代替教师的数学审核与逐页视觉复核。", { class: "hint" }));
  main.append(c);
}

function renderArtifacts(run) {
  const allArtifacts = run.artifacts || []; if (!allArtifacts.length) return;
  const artifacts = allArtifacts.filter(artifact => artifact.status !== "superseded");
  const historicalArtifacts = allArtifacts.filter(artifact => artifact.status === "superseded");
  const pages = artifacts.filter(a => a.media_type === "image/png" && a.metadata?.physical_page);
  const reports = artifacts.filter(a => /quality_report|decision_coverage|source_map|build_manifest/.test(a.name || ""));
  const c = card("文件与检查证据");
  c.append(el("p", "单个 TeX 可能依赖章节、图片与主题；重编译请下载完整源码 ZIP。标为草稿的产物尚未通过发布门槛。", { class: "hint" }));
  const links = el("div", null, { class: "artifact-list" });
  for (const artifact of artifacts.filter(a => a.media_type !== "image/png")) {
    const a = el("a", null, { href: artifactUrl(artifact), class: "artifact-link", target: "_blank", rel: "noopener", "data-artifact-id": artifact.artifact_id });
    append(a, el("strong", artifact.name || artifact.artifact_id), el("small", `版本 ${artifact.revision ?? "待记录"} · ${artifact.status || "草稿"} · ${artifact.media_type || "文件"}`), el("small", `SHA-256 ${artifact.sha256 || "待记录"}`, { class: "hash" })); links.append(a);
  }
  c.append(links);
  if (historicalArtifacts.length) {
    const history = append(el("details", null, { id: "artifact-history" }), el("summary", `历史交付 · ${historicalArtifacts.length} 个文件`), el("p", "以下文件已由后续自动检查替代，保留供比较和下载。本次预览及人工复核使用当前文件。", { class: "hint" }));
    const historyLinks = el("div", null, { class: "artifact-list" });
    for (const artifact of historicalArtifacts) {
      const link = el("a", null, { href: artifactUrl(artifact), class: "artifact-link", target: "_blank", rel: "noopener", "data-historical-artifact-id": artifact.artifact_id });
      append(link, el("strong", artifact.name || artifact.artifact_id), el("small", `历史交付 · 计划版本 ${artifact.revision ?? "待记录"} · ${artifact.created_at || "时间未记录"}`), el("small", `SHA-256 ${artifact.sha256 || "待记录"}`, { class: "hash" }));
      historyLinks.append(link);
    }
    history.append(historyLinks); c.append(history);
  }
  if (run.workflow_id === "beamer.from_tex" && inputOf(run).units?.length) {
    const original = append(el("details"), el("summary", "原讲义内容对照（不可变输入）"), el("p", "结合 source_map.json 与物理页定位核对源内容。这里展示本次输入快照，不是风格参考讲义。", { class: "hint" }));
    for (const unit of inputOf(run).units) original.append(detail(`${unit.id} · ${unit.kind} · ${unit.section_title || ""}`, unit.raw_tex || ""));
    c.append(original);
  }
  for (const report of reports) {
    const details = el("details"); const body = el("pre", "展开后加载记录…"); append(details, el("summary", report.name), body);
    details.ontoggle = async () => { if (!details.open || details.dataset.loaded) return; try { const response = await fetch(artifactUrl(report)); if (!response.ok) throw new Error("报告读取失败"); const text = await response.text(); try { body.textContent = pretty(JSON.parse(text)); } catch { body.textContent = text; } details.dataset.loaded = "true"; } catch (error) { body.textContent = error.message; } };
    if (report.name === "quality_report.json") {
      const record = (run.reviews || []).findLast?.(r => r.artifact_id === report.artifact_id && r.sha256 === report.sha256);
      details.append(el("p", record ? `内容与决策审核已有记录：${record.verdict === "pass" ? "通过" : "存在问题"}` : "请核对七维检查报告、已披露的数学限制和决策落实证据。此审核与逐页视觉审核分别记录。", { class: "hint" }));
      const note = el("textarea", record?.note || "", { "aria-label": "内容与决策审核说明", placeholder: "记录数学疑点、决策落实或审核意见" }); details.append(note);
      const submit = verdict => async () => { if (verdict === "issue" && !note.value.trim()) throw new Error("请说明内容或决策问题。"); await api(`/api/runs/${run.id}/reviews`, { artifact_id: report.artifact_id, sha256: report.sha256, verdict, note: note.value.trim() }); await refreshRun(true); };
      details.append(append(el("div", null, { class: "actions" }), button("内容与决策人工审核通过", submit("pass"), "", { disabled: run.status !== "AWAITING_USER_REVIEW", id: "approve-quality-report" }), button("记录内容与决策问题", submit("issue"), "danger", { disabled: run.status !== "AWAITING_USER_REVIEW" })));
    }
    c.append(details);
  }
  const pdf = artifacts.filter(a => a.media_type === "application/pdf").at(-1);
  if (pdf) { const preview = el("details"); append(preview, el("summary", "PDF 预览"), el("iframe", null, { src: artifactUrl(pdf), title: "本次 PDF 预览", class: "pdf-preview" })); c.append(preview); }
  main.append(c);
  if (pages.length) {
    const reviewCard = card(`逐页视觉复核 · ${pages.length} 个物理页`);
    reviewCard.append(el("p", "请检查每个 overlay 的公式、裁切、遮挡和字号。自动几何检查不能代替人工视觉审核；此处提交将记录页面哈希。已知阻塞问题不能通过“通过”按钮覆盖。", { class: "hint" }));
    const reviewRecords = run.reviews || [];
    for (const artifact of pages) {
      const meta = artifact.metadata; const review = reviewRecords.findLast?.(r => r.artifact_id === artifact.artifact_id && r.sha256 === artifact.sha256);
      const page = el("details", null, { class: `page-review ${review?.verdict === "pass" ? "reviewed" : ""}`, "data-page-id": artifact.artifact_id });
      const label = `物理页 ${meta.physical_page} · frame ${meta.frame_id || "待映射"} · overlay ${meta.overlay_index ?? "待映射"}`;
      append(page, el("summary", `${label}${review ? ` · 已记录：${review.verdict === "pass" ? "通过" : "发现问题"}` : " · 尚未人工复核"}`), el("img", null, { src: artifactUrl(artifact), alt: label, loading: "lazy" }), el("p", `页面 SHA-256：${artifact.sha256}`, { class: "hash" }));
      if (meta.issues?.length) page.append(detail("自动检查定位", meta.issues, true));
      const note = el("textarea", review?.note || "", { placeholder: "记录问题位置或复核说明", "aria-label": `物理页 ${meta.physical_page} 复核说明` }); page.append(note);
      const submit = verdict => async () => { if (verdict === "issue" && !note.value.trim()) throw new Error("请填写具体问题与位置。"); await api(`/api/runs/${run.id}/reviews`, { artifact_id: artifact.artifact_id, sha256: artifact.sha256, verdict, note: note.value.trim() }); await refreshRun(true); };
      append(page, append(el("div", null, { class: "actions" }), button("本页人工复核通过", submit("pass"), "", { "data-verdict": "pass", disabled: run.status !== "AWAITING_USER_REVIEW" }), button("记录本页问题", submit("issue"), "danger", { "data-verdict": "issue", disabled: run.status !== "AWAITING_USER_REVIEW" }))); reviewCard.append(page);
    }
    main.append(reviewCard);
  }
}
function renderEvents() {
  const list = document.querySelector("#event-list"); if (!list) return;
  list.replaceChildren();
  for (const event of state.events.slice(-100).reverse()) list.append(el("li", `#${event.sequence} · ${event.timestamp || ""} · ${event.type}\n${pretty(event.payload || {})}`));
  if (!state.events.length) list.append(el("li", "暂无事件"));
  const fallbacks = document.querySelector("#model-fallback-events");
  if (fallbacks) {
    fallbacks.replaceChildren();
    for (const event of state.events.filter(event => ["provider.routing", "provider.result"].includes(event.type) && event.payload?.event === "model_fallback").slice(-10).reverse()) {
      const payload = event.payload;
      fallbacks.append(el("li", `${modelLabel(payload.from_model_id)} → ${modelLabel(payload.to_model_id)} · ${payload.error_code || payload.code || "接口调用失败"}${payload.reason ? `：${payload.reason}` : ""}`, { "data-fallback-sequence": event.sequence }));
    }
  }
}
async function poll() {
  if (state.polling || state.busy || document.hidden) return;
  state.polling = true;
  try {
    if (state.selected) await refreshRun(); await refreshList();
    if (Date.now() - state.healthCheckedAt > 5000) { const health = await api("/api/health"); state.caps.worker = health.worker; state.healthCheckedAt = Date.now(); }
    document.querySelector("#connection").textContent = state.caps.worker?.alive ? "本地服务与任务进程已连接" : "本地服务已连接 · 任务进程未就绪";
  }
  catch { document.querySelector("#connection").textContent = "连接中断 · 自动重连"; }
  finally { state.polling = false; }
}
async function initialize() {
  try {
    state.csrf = (await api("/api/session")).csrf_token;
    state.caps = await api("/api/capabilities"); renderCapabilities();
    await refreshList();
    if (state.selected && state.runs.some(r => r.id === state.selected)) await selectRun(state.selected); else renderNew();
    document.querySelector("#connection").textContent = state.caps.worker?.alive ? "本地服务与任务进程已连接" : "本地服务已连接 · 任务进程未就绪";
    document.querySelector("#new-run").onclick = renderNew;
    window.setInterval(poll, 1500);
  } catch (error) { notify(error.message); document.querySelector("#connection").textContent = "无法连接本地服务"; main.replaceChildren(el("h1", "本地服务未就绪"), el("p", "请检查启动窗口和本机日志，再刷新本页。")); }
}
initialize();
