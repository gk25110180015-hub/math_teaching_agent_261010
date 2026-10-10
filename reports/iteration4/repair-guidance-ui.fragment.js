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
