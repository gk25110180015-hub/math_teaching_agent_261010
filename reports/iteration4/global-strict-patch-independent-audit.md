# 严格全局补丁与显式迁移独立审查

状态：INDEPENDENT_REVIEW_PASS，未发现阻止本候选部署的剩余问题。本报告仅审候选、代码及证据；没有改生产、数据库、原稿或生成正文，也没有调用真实 API。

## 实际问题与受限修复

CH02 第 118 次请求的全局提案只获准修改 S02.U14，却在返回整节正文时误改非目标 S02.U16 的 S02.C03 核算 AST。实际 n=1，原等式两边均为 3，提案两边为 4 和 3。原范围门禁拒绝正确，不能放宽后接受；完整证据见 `CH02-global-r3-rejected-proposal-evidence.json`。

候选改为现有 `repair_local_patch` + `LocalPatch` + `apply_local_patch`。模型仅提供授权单元的 tex 替换和合法目标核算更新/追加，不再被要求重写整节。程序保留其他所有单元、身份/顺序/关联、非目标核算及旧不确定性/限制记录；只对目标正文做归一化，仍复核非目标字段未变。完整节响应不会被静默裁成补丁，越界计算仍拒绝并保存提案。新候选仅进入 checking，后续数学审阅、核算和编译仍须执行。

原 U14 的 n≥N 本来正确；改为 n≥N+1 属无必要收窄。这次工作流修复不会清除或重新抽取旧疑点，也不能宣称解决了模型数学推理误报。

## 迁移边界

- 只匹配 schema_version=1 且完整 identity 精确等于已部署白名单。旧 repair prompt=`46c1ff3b8ea3f0fba7afe1f6a3b99f3286324551522140dc61d8b646807759f9`、WrittenSection schema=`4e9b07e27f359212c0460381e3cbd6e548d18a48490e553e60b0c56d30d9ada7`、normalizer=`25d2fff448b21fcad71b5e7aae512cf6ab27f66bdeefd9e459ca57652a1fd74c`，并绑定当前批准计划、偏好模型和 provider。未知、缺失或额外 identity 字段不自动迁移。
- v2 identity 增加补丁 schema/validator、核算协议、迁移 helper 及相关 prompt/normalizer hash；helper 本身纳入节检查契约。改变契约不能悄悄沿用旧通过状态。
- 迁移保留 rounds_used、phase、issues、pending、sections、round_directory 和原候选 SHA；仅改变版本/契约并加入审计标记。不清请求数、不改审批、不把 validated 还原为初始稿，也不采纳旧拒绝提案。
- 已有 section 候选只须是批准计划的合法子集：真实 CH02 是 S02–S05，CH03 是 S03–S05。pending 的目标必须真实存在且与保留疑点对应；邻节规格必须对应批准的实际相邻节。候选路径、来源 round 目录、SHA 和结构继续核验。
- 在真实 job lease/fence 和批准计划核对下保存旧 state 原字节、迁移后字节及不可覆盖 journal，随后原子替换 state 并记录迁移事件。journal 后/state 前及 state 后/event 前的崩溃分别可恢复，事件幂等；不相符的证明或孤立标记阻断。

## 独审发现与修订跟踪

初候选在迁移事件已存在后，只验证归档 before/after，没有验证当前状态的轮次下界。若当前 rounds 被回退到 0 或 2，旧的 3 轮迁移记录仍可被载入。已要求并看到候选增加：每次 v2 load 验证当前合法状态，且当前 rounds 不得低于迁移时保留值；合法后续 rounds=4 允许继续。

初候选复用预提交 journal 时未核对其中 approval/input/request-count 与当前 run。已要求并看到候选在写回 state 前作相同核对；批准计划比较已扩展为完整实际 plan 对象一致。

另要求 journal 中 pending_scope 必须等于旧 pending 的准确投影，保留请求数不得为负。最终候选已补两项检查和损坏回归。validated 回归也已走真实可达路径：先实际生成并完成检查、将契约设为精确已部署 v1、执行迁移，再通过真实 `_lecture_sections` 重查；断言已接受正文完整相同、writer/repair 不重跑、轮次保留。独审已核对这些实现及测试断言。

## 测试分类

最终证据为 `global-patch-validation/20260920-192019-2329bb`：196 PASS，其中 40 项新增和 156 项既有，45.62 秒；1 项 Windows 编译测试明确 deselected，外网尝试记录为 0。独审核对了 result、context、pytest 日志和 JUnit，并重新计算全部 8 个 manifest 文件与实际隔离包文件 SHA，逐项相符；所有 Python 候选语法解析通过。这里是禁真实模型网络的本地/mock 回归，包含实际隔离 SQLite/恢复状态测试，不能当作真实模型或 Windows 编译验收。

冻结生产候选：pipeline=`bc99fd54a18fa71aaae1cac1bd3c554d593a04bd18a34701343c6d613992b2b5`；新 helper=`8c1167ba608adbc1b74d9fe4d5852152eba74069606c466a4c2db606c8df2186`；40 项新增测试=`a387953aaa2cfcb27dbb61228d9d0157696527c72fd0e9773b5c68cd68502ec1`。

有意义旧基线红测 21 FAIL / 10 PASS、候选初轮 29 PASS / 2 夹具失败、中间 187 PASS 和 194 PASS 均作为历史保留，不与最终 196 相加。独审发现的轮次回退、预提交 journal 身份核对及审计字段检查已纳入最终代码和测试。本报告不会把 mock compiler 当作 Windows XeLaTeX，也不把只读真实状态形状验证当作实际生产迁移。

真实 API、新 Windows 编译、实际生产迁移/恢复、最终 PDF 逐页审读及教师验收，在此独审中均 NOT_RUN。CH02 的 BLOCKED / 118 请求及原第 3 轮待修状态仍作为真实阻塞保留。
