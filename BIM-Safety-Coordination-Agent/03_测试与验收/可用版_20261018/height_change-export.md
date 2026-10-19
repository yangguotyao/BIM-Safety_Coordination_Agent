# Safety Case CASE-20261018-21A60A

- 标题：可用版演示 · 审批提高到1.5m
- 状态：`reopened`
- 检查时刻：2026-10-16T09:00:00+08:00
- 项目 / 模型 / 区域：S1-DEMO / S1-bSDD-example @ 4075c44a6e47 / ZONE-S1-L05-EDGE
- 数据性质：mixed_real_bim_simulated_site_state
- 模式：demo

> 本案例用于研究与文献综述展示。板边为人工标注检查边界；现场观察、施工活动和防护状态为模拟输入。

## 1. 构件与证据

| 构件 GUID | 证据 | 规范 |
|---|---|---|
| 0FOHK4aT910wgskSbVHn0U | EV-001, EV-010 | GB-3.2.3, JGJ-4.3.1, GB-3.2.1 |

## 2. Findings

### F-001 模拟临边无防护且有人员暴露

- 结果：`risk_candidate`
- 风险级别：演示管理策略：高（非事故概率）
- 适用条款：GB-3.2.3, JGJ-4.3.1, GB-3.2.1
- 范围说明：只对已检查项目和演示输入成立，不代表整个现场安全。

| 检查项 | 结果 | 来源 |
|---|---|---|
| 任务时间窗 | pass | schedule_query |
| 证据匹配 | pass | evidence_check |
| 观察字段完整性 | pass | evidence_check |
| 标注边界暴露 | pass | 检查区域标注 |
| 防护存在性 | fail | 模拟观察 |
| 防护高度 ≥ 1.2 m | fail | 模拟观察 |
| 固定与连续性 | fail | 模拟观察 |
| 人员暴露 | pass | 模拟观察 |
| 与标注边线距离 ≤ 演示阈值 | pass | spatial_check |

不确定性：
- 真实临边、防护高度、人员状态和坠落基准面未经现场确认。

## 3. 控制措施

### CTRL-001（v2）

- 措施：设置高度不低于1.5 m的连续防护栏杆，并在复核前限制进入。
- 责任人：演示机电班组
- 状态：`verification_failed`
- 验证要求：同项目、同模型版本、同区域、同构件的实施后证据；证据时间晚于人工记录的实施时刻；防护存在、高度 ≥ 1.2 m、固定与连续性标注；演示安全员人工复核确认
- 验收参数：{"guardrail_required": true, "min_height_m": 1.5, "fixed_required": true, "continuous_required": true, "manual_requirements": ["防护栏杆固定与连续性已逐项核对"]}

## 4. 审核、实施与复核

- 审核：{"decision": "approve", "reviewer": "演示安全员", "reviewed_at": "2026-10-16T09:10:00+08:00", "control_version": 2, "comment": "同意进入演示实施。", "verification_snapshot": {"CTRL-001": {"guardrail_required": true, "min_height_m": 1.5, "fixed_required": true, "continuous_required": true, "manual_requirements": ["防护栏杆固定与连续性已逐项核对"]}}}
- 实施：{"owner": "演示机电班组", "implemented_at": "2026-10-16T09:20:00+08:00", "comment": "模拟实施记录，不代表现场实际施工。", "provenance": "simulated_human_record"}
- 复核：{"verified_at": "2026-10-16T09:40:00+08:00", "evidence_ids": ["EV-010"], "checks": [{"name": "已记录人工实施", "result": "pass", "source": "cases.implementation"}, {"name": "项目/模型版本/区域匹配：EV-010", "result": "pass", "source": "evidence_check"}, {"name": "证据晚于人工实施时刻：EV-010", "result": "pass", "source": "时间比较"}, {"name": "证据不晚于复核时刻：EV-010", "result": "pass", "source": "时间比较"}, {"name": "模拟防护存在：EV-010", "result": "pass", "source": "after 证据观察"}, {"name": "模拟防护高度 ≥ 1.5 m：EV-010", "result": "fail", "source": "批准措施版本的验收参数"}, {"name": "模拟固定与连续性：EV-010", "result": "pass", "source": "after 证据观察"}, {"name": "标注边界仍暴露（检查范围成立）：EV-010", "result": "pass", "source": "检查区域"}, {"name": "演示安全员人工确认", "result": "pass", "source": "verify 请求"}, {"name": "修改措施的人工核验项逐项确认", "result": "pass", "source": "批准措施及独立人工核验"}], "reviewer_confirmed": true, "manual_checks_confirmed": true, "approved_criteria": [{"guardrail_required": true, "min_height_m": 1.5, "fixed_required": true, "continuous_required": true, "manual_requirements": ["防护栏杆固定与连续性已逐项核对"]}], "control_version": 2, "result": "fail", "remaining_risk": "EV-010 未满足全部复核检查项。", "evidence_records": [{"evidence_id": "EV-010", "project_id": "S1-DEMO", "model_id": "S1-bSDD-example", "model_version": "4075c44a6e47", "zone_id": "ZONE-S1-L05-EDGE", "file_path": "07_案例与验收模板/演示证据图/EV-010.png", "kind": "simulated_inspection_diagram", "captured_at": "2026-10-16T09:30:00+08:00", "stage": "after", "provenance": "真实IFC几何派生；现场观察为模拟，非照片检测结果", "label": "复核通过", "source": "seed", "created_at": "2026-10-16T09:00:00+08:00", "bim_guids": ["0FOHK4aT910wgskSbVHn0U"], "observation": {"guardrail_state": "present", "guardrail_height_m": 1.2, "worker_present": true, "drop_height_m": 2.5, "boundary_is_exposed": true, "guardrail_fixed": true, "guardrail_continuous": true, "ppe_confirmed": true, "simulated": true}, "checks": {"项目/模型版本/区域匹配": true, "证据晚于人工实施时刻": true, "证据不晚于复核时刻": true, "模拟防护存在": true, "模拟防护高度 ≥ 1.5 m": false, "模拟固定与连续性": true, "标注边界仍暴露（检查范围成立）": true}}]}

## 5. 事件日志

| 时间 | 状态 | 事件 | 操作者 |
|---|---|---|---|
| 2026-10-18T23:23:19+08:00 | `draft` | case_created | 演示安全员 |
| 2026-10-18T23:23:19+08:00 | `analyzing` | analysis_started | 演示安全员 |
| 2026-10-18T23:23:19+08:00 | `pending_review` | analysis_completed | Safety Coordinator |
| 2026-10-18T23:23:38+08:00 | `pending_review` | controls_modified | 演示安全员 |
| 2026-10-18T23:23:41+08:00 | `approved` | review_approved | 演示安全员 |
| 2026-10-18T23:23:45+08:00 | `rectifying` | implementation_recorded | 演示机电班组 |
| 2026-10-18T23:23:54+08:00 | `pending_verification` | evidence_added | 演示安全员 |
| 2026-10-18T23:23:58+08:00 | `reopened` | verification_failed | 演示安全员 |

## 6. 边界与假设

- 板边已在演示中标注为需检查边界，不等于真实项目临空侧。
- 坠落高度 2.5 m、人员作业和防护缺失均为模拟观察。
- 17.3 m 是模型世界 Z 高程，不是坠落高度。

## 7. 任务理解与工具计划

```json
{
  "request": "全面检查L05临边风险",
  "zone_id": "ZONE-S1-L05-EDGE",
  "as_of": "2026-10-16T09:00:00+08:00",
  "focus": [
    "all"
  ],
  "selected_tools": [
    "bim_query",
    "schedule_query",
    "evidence_check",
    "spatial_check",
    "rule_retrieval",
    "risk_assessment"
  ],
  "retrieval_query": "L05板边区域机电材料转运演示 临边 防护 栏杆 坠落 高度 人员 2m 1.2m 安全 作业 边沿 周边 围护 孔洞 楼层",
  "needs_clarification": false,
  "clarification": "",
  "assumptions": [
    "现场观察来自明确标注的演示输入；只判断本次选定检查项。"
  ],
  "context_inherited": false,
  "mode": "demo_rules"
}
```

## 8. Safety State

```json
{
  "case_id": "CASE-20261018-21A60A",
  "zone_id": "ZONE-S1-L05-EDGE",
  "as_of": "2026-10-16T09:00:00+08:00",
  "model": {
    "id": "S1-bSDD-example",
    "version": "4075c44a6e47",
    "guids": [
      "0FOHK4aT910wgskSbVHn0U"
    ]
  },
  "task_spec": {
    "request": "全面检查L05临边风险",
    "zone_id": "ZONE-S1-L05-EDGE",
    "as_of": "2026-10-16T09:00:00+08:00",
    "focus": [
      "all"
    ],
    "selected_tools": [
      "bim_query",
      "schedule_query",
      "evidence_check",
      "spatial_check",
      "rule_retrieval",
      "risk_assessment"
    ],
    "retrieval_query": "L05板边区域机电材料转运演示 临边 防护 栏杆 坠落 高度 人员 2m 1.2m 安全 作业 边沿 周边 围护 孔洞 楼层",
    "needs_clarification": false,
    "clarification": "",
    "assumptions": [
      "现场观察来自明确标注的演示输入；只判断本次选定检查项。"
    ],
    "context_inherited": false,
    "mode": "demo_rules"
  },
  "activity": "L05板边区域机电材料转运演示",
  "schedule": {
    "task_id": "TASK-S1-001",
    "activity": "L05板边区域机电材料转运演示",
    "planned_start": "2026-10-16T08:00:00+08:00",
    "planned_end": "2026-10-16T12:00:00+08:00",
    "as_of": "2026-10-16T09:00:00+08:00",
    "active": true,
    "owner": "演示机电班组",
    "provenance": "simulated",
    "note": "并非S1项目真实施工进度或真实MEP构件识别"
  },
  "evidence_ids": [
    "EV-001"
  ],
  "observations": {
    "guardrail_state": "absent",
    "guardrail_height_m": null,
    "worker_present": true,
    "drop_height_m": 2.5,
    "boundary_is_exposed": true,
    "guardrail_fixed": false,
    "guardrail_continuous": false,
    "ppe_confirmed": true,
    "simulated": true
  },
  "missing_fields": [],
  "spatial": {
    "zone_id": "ZONE-S1-L05-EDGE",
    "point_m": [
      21.937510528169764,
      30.338090927316102,
      17.300000000149012
    ],
    "edge_segment_m": [
      [
        22.437876190108987,
        32.337999476313314,
        17.300000000149012
      ],
      [
        22.437144849516194,
        28.337999543170696,
        17.300000000149012
      ]
    ],
    "distance_m": 0.5,
    "nearest_point_m": [
      22.438,
      30.338,
      17.3
    ],
    "exposure_threshold_m": 1.0,
    "within_threshold": true,
    "aabb_candidate": true,
    "aabb_note": "AABB 只用于候选筛选，不作为碰撞或风险结论。",
    "drop_height_m": 2.5,
    "drop_height_note": "2.5m是演示假设；17.3m是模型世界Z高程，二者不可等同"
  },
  "provenance": "real_bim_and_simulated_site_observations",
  "incomplete": false
}
```

## 9. 决策包（分析时快照）

```json
{
  "case_id": "CASE-20261018-21A60A",
  "run_id": "RUN-20261018-78E453",
  "status": "candidate",
  "task": {
    "request": "全面检查L05临边风险",
    "zone_id": "ZONE-S1-L05-EDGE",
    "as_of": "2026-10-16T09:00:00+08:00",
    "focus": [
      "all"
    ],
    "selected_tools": [
      "bim_query",
      "schedule_query",
      "evidence_check",
      "spatial_check",
      "rule_retrieval",
      "risk_assessment"
    ],
    "retrieval_query": "L05板边区域机电材料转运演示 临边 防护 栏杆 坠落 高度 人员 2m 1.2m 安全 作业 边沿 周边 围护 孔洞 楼层",
    "needs_clarification": false,
    "clarification": "",
    "assumptions": [
      "现场观察来自明确标注的演示输入；只判断本次选定检查项。"
    ],
    "context_inherited": false,
    "mode": "demo_rules"
  },
  "finding": {
    "finding_id": "F-001",
    "hazard": "模拟临边无防护且有人员暴露",
    "result": "risk_candidate",
    "risk_level": "演示管理策略：高（非事故概率）",
    "bim_guids": [
      "0FOHK4aT910wgskSbVHn0U"
    ],
    "evidence_ids": [
      "EV-001"
    ],
    "rule_ids": [
      "GB-3.2.3",
      "JGJ-4.3.1",
      "GB-3.2.1"
    ],
    "checks": [
      {
        "name": "任务时间窗",
        "result": "pass",
        "source": "schedule_query",
        "note": "检查时刻是否落在模拟活动时间内"
      },
      {
        "name": "证据匹配",
        "result": "pass",
        "source": "evidence_check",
        "note": "项目/模型版本/区域/任务时间窗"
      },
      {
        "name": "观察字段完整性",
        "result": "pass",
        "source": "evidence_check",
        "note": "未知字段不落为 false，也不输出无风险。"
      },
      {
        "name": "标注边界暴露",
        "result": "pass",
        "source": "检查区域标注",
        "note": "人工标注边界，不等同经现场确认的坠落边缘。"
      },
      {
        "name": "防护存在性",
        "result": "fail",
        "source": "模拟观察",
        "note": ""
      },
      {
        "name": "防护高度 ≥ 1.2 m",
        "result": "fail",
        "source": "模拟观察",
        "note": ""
      },
      {
        "name": "固定与连续性",
        "result": "fail",
        "source": "模拟观察",
        "note": ""
      },
      {
        "name": "人员暴露",
        "result": "pass",
        "source": "模拟观察",
        "note": ""
      },
      {
        "name": "与标注边线距离 ≤ 演示阈值",
        "result": "pass",
        "source": "spatial_check",
        "note": "0.5 m ≤ 1.0 m 为演示项目策略，不是国家规范距离限值。"
      }
    ],
    "uncertainties": [
      "真实临边、防护高度、人员状态和坠落基准面未经现场确认。"
    ],
    "provenance": "mixed_real_bim_simulated_site_observation",
    "scope_note": "只对已检查项目和演示输入成立，不代表整个现场安全。",
    "inputs": {
      "focus": [
        "all"
      ],
      "guardrail_state": "absent",
      "guardrail_height_m": null,
      "worker_present": true,
      "boundary_is_exposed": true,
      "guardrail_fixed": false,
      "guardrail_continuous": false,
      "drop_height_m": 2.5
    },
    "narrative": {
      "summary": "模拟临边无防护且有人员暴露。依据 GB-3.2.3, JGJ-4.3.1, GB-3.2.1 与 EV-001，检查结果为 risk_candidate；结论只对已检查项成立。",
      "reasoning_basis": [
        {
          "type": "evidence",
          "id": "EV-001"
        },
        {
          "type": "rule",
          "id": "GB-3.2.3"
        },
        {
          "type": "rule",
          "id": "JGJ-4.3.1"
        },
        {
          "type": "rule",
          "id": "GB-3.2.1"
        },
        {
          "type": "finding",
          "id": "F-001"
        }
      ],
      "uncertainties": [
        "真实临边、防护高度、人员状态和坠落基准面未经现场确认。"
      ],
      "label": "演示模型输出（确定性模板）"
    }
  },
  "evidence": [
    "EV-001"
  ],
  "governing_rules": [
    {
      "rule_id": "GB-3.2.3",
      "standard": "GB 55034-2022",
      "clause": "3.2.3",
      "text": "孔洞及无围护或围护不足1.2m的楼层周边等边沿，应采取安全防护，防护设施不得随意拆除。",
      "text_kind": "人工核对官方原文后的释义",
      "source_path": "04_安全规范/GB55034-2022_官方原文.pdf",
      "pdf_page": 6,
      "source_url": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2022/art_17339_768953.html",
      "status": "active",
      "effective_from": "2023-06-01",
      "checked_on": "2026-10-16",
      "jurisdiction": "中国；国外模型仅用于研究演示",
      "applicability": "需确认对象属于条文范围；防护状态必须有现场或演示标注证据",
      "version": "v1",
      "human_page_checked": 1,
      "score": 24.743
    },
    {
      "rule_id": "JGJ-4.3.1",
      "standard": "JGJ 80-2016",
      "clause": "4.3.1",
      "text": "临边栏杆由横杆、立杆和挡脚板组成；规定上杆1.2m、增设横杆间距、立杆不超过2m及挡脚板不低于180mm等构造要求。",
      "text_kind": "人工核对官方原文后的释义",
      "source_path": "04_安全规范/JGJ80-2016_官方原文.pdf",
      "pdf_page": 14,
      "source_url": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2016/art_17339_228384.html",
      "status": "active",
      "effective_from": "2016-12-01",
      "checked_on": "2026-10-16",
      "jurisdiction": "中国；国外模型仅用于研究演示",
      "applicability": "仅核对该条细部要求；不得仅凭一项高度判断整体合格",
      "version": "v1",
      "human_page_checked": 1,
      "score": 14.538
    },
    {
      "rule_id": "GB-3.2.1",
      "standard": "GB 55034-2022",
      "clause": "3.2.1",
      "text": "坠落高度基准面上方达到2m的高处作业，需要安全防护、防滑及正确佩戴劳动防护用品。",
      "text_kind": "人工核对官方原文后的释义",
      "source_path": "04_安全规范/GB55034-2022_官方原文.pdf",
      "pdf_page": 6,
      "source_url": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2022/art_17339_768953.html",
      "status": "active",
      "effective_from": "2023-06-01",
      "checked_on": "2026-10-16",
      "jurisdiction": "中国；国外模型仅用于研究演示",
      "applicability": "需要有可追溯的坠落高度基准面，不能以模型绝对Z坐标代替坠落高度",
      "version": "v1",
      "human_page_checked": 1,
      "score": 12.718
    }
  ],
  "risk": {
    "level": "演示管理策略：高（非事故概率）",
    "result": "risk_candidate"
  },
  "controls": [
    {
      "control_id": "CTRL-001",
      "finding_id": "F-001",
      "action": "由演示班组设置连续的临边防护栏杆，并限制无防护区域进入。",
      "owner": "演示机电班组",
      "verification_requirements": [
        "同项目、同模型版本、同区域、同构件的实施后证据",
        "证据时间晚于人工记录的实施时刻",
        "防护存在、高度 ≥ 1.2 m、固定与连续性标注",
        "演示安全员人工复核确认"
      ],
      "status": "proposed",
      "version": 1,
      "provenance": "demo_template",
      "verification_criteria": {
        "guardrail_required": true,
        "min_height_m": 1.2,
        "fixed_required": true,
        "continuous_required": true,
        "manual_requirements": []
      },
      "scope_note": "仅为演示候选措施，不替代施工单位专项方案。"
    }
  ],
  "owners": [
    "演示机电班组"
  ],
  "assumptions": [
    "板边已在演示中标注为需检查边界，不等于真实项目临空侧。",
    "坠落高度 2.5 m、人员作业和防护缺失均为模拟观察。",
    "17.3 m 是模型世界 Z 高程，不是坠落高度。",
    "现场观察来自明确标注的演示输入；只判断本次选定检查项。"
  ],
  "reviewer": "演示安全员（待人工审核）",
  "approval_required": true,
  "scope": "仅对选定检查项成立；审批和实施由人工操作",
  "mode": "demo_rules"
}
```

---

本导出不替代真实安全审批，不证明现场合规，不构成事故概率判断。
