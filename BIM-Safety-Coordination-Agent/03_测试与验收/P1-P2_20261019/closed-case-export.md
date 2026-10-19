# Safety Case CASE-20261019-4CF647

- 标题：P1 / P2 · 多工种错时与文本澄清闭环
- 状态：`closed`
- 检查时刻：2019-05-29T08:34:40+08:00
- 项目 / 模型 / 区域：S1-DEMO / S1-bSDD-example @ 4075c44a6e47 / ZONE-SELECTED-57CEAF2297
- 数据性质：mixed_real_bim_simulated_site_state
- 模式：live

> 本案例用于研究与文献综述展示。板边为人工标注检查边界；现场观察、施工活动和防护状态为模拟输入。

## 1. 构件与证据

| 构件 GUID | 证据 | 规范 |
|---|---|---|
| 2riKNFXuDAvQJxT4q2Dk7a | EV-UP-20261019-B981A9, EV-UP-20261019-154B73 | JGJ-4.3.1 |

## 2. Findings

### F-001 已检查项未发现防护缺失或高度不足

- 结果：`no_issue_in_checked_items`
- 风险级别：未判定
- 适用条款：JGJ-4.3.1
- 范围说明：只对已检查项目和演示输入成立，不代表整个现场安全。

| 检查项 | 结果 | 来源 |
|---|---|---|
| 任务时间窗 | pass | schedule_query |
| 证据匹配 | pass | evidence_check |
| 观察字段完整性 | pass | evidence_check |
| 标注边界暴露 | pass | 检查区域标注 |
| 防护存在性 | pass | 模拟观察 |
| 防护高度 ≥ 1.2 m | pass | 模拟观察（演示策略阈值） |
| 固定与连续性 | pass | 模拟观察 |
| 人员暴露 | pass | 模拟观察 |
| 与标注边线距离 ≤ 演示阈值 | pass | spatial_check |

不确定性：
- 真实临边、防护高度、人员状态和坠落基准面未经现场确认。

### F-SPACE-001 作业空间冲突：板边材料转运 / 相邻区域安装

- 结果：`risk_candidate`
- 风险级别：计划冲突待处置
- 适用条款：
- 范围说明：基于编制的作业空间体与时间窗，不等同现场真实碰撞。

| 检查项 | 结果 | 来源 |
|---|---|---|
| 计划时间交叠 | fail | activity_conflict_check |
| 三维作业范围交叠 | fail | activity_conflict_check |

## 3. 控制措施

### CTRL-F-SPACE-001（v1）

- 措施：在L05临边演示区域（ZONE-SELECTED-57CEAF2297，涉及IfcSlab 2riKNFXuDAvQJxT4q2Dk7a）对板边材料转运（ACT-P1-01）与相邻区域安装（ACT-P1-02）实施错时作业或调整三维作业范围，使09:00–10:00交叠时段及交叠体[25.222,21.378,17.3]–[28.222,24.378,19.3]内实现人员与相邻作业隔离；协同运输与安装负责人确认方案后，须复核调整后的时间窗和作业范围无时间及空间交叠、补充实施后证据并人工确认，方可开放该区域作业；复核前不得开放。
- 责任人：演示协调员
- 状态：`verified`
- 验证要求：保留批准活动及责任主体；复核调整后的时间窗和作业范围；提供实施后证据并人工确认
- 验收参数：{"guardrail_required": false, "min_height_m": 1.2, "fixed_required": false, "continuous_required": false, "coordination_required": true, "manual_requirements": []}

## 4. 审核、实施与复核

- 审核：{"decision": "approve", "reviewer": "演示安全员", "reviewed_at": "2019-05-29T08:44:40+08:00", "control_version": 1, "comment": "批准错时作业措施，保留两项活动及责任主体。", "verification_snapshot": {"CTRL-F-SPACE-001": {"guardrail_required": false, "min_height_m": 1.2, "fixed_required": false, "continuous_required": false, "coordination_required": true, "manual_requirements": []}}, "activity_plan_revision": 1, "coordination_task_ids": ["ACT-P1-01", "ACT-P1-02"]}
- 实施：{"owner": "演示协调员", "implemented_at": "2019-06-03T07:50:00+08:00", "comment": "演示实施记录：已按批准措施错时安排并复核工作范围。", "provenance": "simulated_human_record"}
- 复核：{"verified_at": "2019-06-03T08:10:00+08:00", "evidence_ids": ["EV-UP-20261019-154B73"], "checks": [{"name": "已记录人工实施", "result": "pass", "source": "cases.implementation"}, {"name": "新观察已人工确认：EV-UP-20261019-154B73", "result": "pass", "source": "evidence.perception"}, {"name": "项目/模型版本/区域匹配：EV-UP-20261019-154B73", "result": "pass", "source": "evidence_check"}, {"name": "证据晚于人工实施时刻：EV-UP-20261019-154B73", "result": "pass", "source": "时间比较"}, {"name": "证据不晚于复核时刻：EV-UP-20261019-154B73", "result": "pass", "source": "时间比较"}, {"name": "演示安全员人工确认", "result": "pass", "source": "verify 请求"}, {"name": "批准活动的时空冲突已消除", "result": "pass", "source": "activity_conflict_check"}], "reviewer_confirmed": true, "manual_checks_confirmed": false, "approved_criteria": [{"guardrail_required": false, "min_height_m": 1.2, "fixed_required": false, "continuous_required": false, "coordination_required": true, "manual_requirements": []}], "control_version": 1, "result": "pass_in_demo_scope", "remaining_risk": "只验证演示中列明项目，真实现场未检查。", "evidence_records": [{"evidence_id": "EV-UP-20261019-154B73", "project_id": "S1-DEMO", "model_id": "S1-bSDD-example", "model_version": "4075c44a6e47", "zone_id": "ZONE-SELECTED-57CEAF2297", "file_path": "D:\\BIM-Safety_Coordination_Agent\\BIM-Safety-Coordination-Agent\\02_网站源码\\backend\\runtime\\uploads\\c8e17124960b4a219e908172ccdd79c2.jpg", "kind": "uploaded_inspection", "captured_at": "2019-06-03T08:00:24+08:00", "stage": "after", "provenance": "人工确认的演示模拟观察", "label": "S1原始公开照片；构件关联与观察量测为人工模拟，不声称真实整改前后对应。", "source": "upload", "created_at": "2026-10-19T16:17:41+08:00", "bim_guids": ["2riKNFXuDAvQJxT4q2Dk7a"], "observation": {"guardrail_state": "present", "guardrail_height_m": 1.3, "worker_present": true, "drop_height_m": 2.5, "boundary_is_exposed": true, "guardrail_fixed": true, "guardrail_continuous": true, "ppe_confirmed": true, "worker_point_m": null, "simulated": true}, "perception": {"summary": "Aerial view of an active construction site featuring a concrete structure with exposed rebar, a large yellow tower crane, and stacked prefabricated wall panels. Several workers are visible on the upper concrete slab. The site boundaries show varying levels of protection, including orange mesh fencing on the left and blue hoarding panels on the right.", "observation": {"guardrail_state": "present", "guardrail_height_m": null, "worker_present": true, "drop_height_m": null, "boundary_is_exposed": true, "guardrail_fixed": null, "guardrail_continuous": false, "ppe_confirmed": null, "worker_point_m": null}, "image_kind": "photo", "visible_features": ["Tower crane", "Concrete slab", "Exposed rebar", "Prefabricated wall panels", "Construction workers", "Orange safety fencing", "Blue hoarding", "Temporary site offices", "Building materials", "Adjacent residential building"], "uncertainties": ["Specific height of the working platform", "Detailed PPE compliance due to distance", "Structural stability of temporary edges", "Exact dimensions of the drop zones"], "status": "confirmed", "model": "qwen3.7-plus", "confirmed": true, "note": "模型观察候选，测量参数与现场性质需人工确认", "source": "simulated", "human_note": "演示编制观察；高度、固定情况和构件关联由人工模拟，不是图像模型测量或原项目实测。"}, "checks": {"新观察已人工确认": true, "项目/模型版本/区域匹配": true, "证据晚于人工实施时刻": true, "证据不晚于复核时刻": true}}]}

## 5. 事件日志

| 时间 | 状态 | 事件 | 操作者 |
|---|---|---|---|
| 2026-10-19T16:17:18+08:00 | `draft` | case_created | 演示安全员 |
| 2026-10-19T16:17:18+08:00 | `draft` | scope_updated | 演示安全员 |
| 2026-10-19T16:17:18+08:00 | `draft` | evidence_uploaded | 演示安全员 |
| 2026-10-19T16:17:27+08:00 | `draft` | observation_confirmed | 演示安全员 |
| 2026-10-19T16:17:27+08:00 | `draft` | activity_plan_updated | 演示安全员 |
| 2026-10-19T16:17:27+08:00 | `draft` | site_note_added | 演示安全员 |
| 2026-10-19T16:17:27+08:00 | `analyzing` | analysis_started | 演示安全员 |
| 2026-10-19T16:17:32+08:00 | `needs_evidence` | analysis_completed | Safety Coordinator |
| 2026-10-19T16:17:33+08:00 | `draft` | text_conflict_resolved | 演示安全员 |
| 2026-10-19T16:17:33+08:00 | `analyzing` | analysis_started | 演示安全员 |
| 2026-10-19T16:17:41+08:00 | `pending_review` | analysis_completed | Safety Coordinator |
| 2026-10-19T16:17:41+08:00 | `approved` | review_approved | 演示安全员 |
| 2026-10-19T16:17:41+08:00 | `approved` | activity_plan_adjusted | 演示安全员 |
| 2026-10-19T16:17:41+08:00 | `rectifying` | implementation_recorded | 演示协调员 |
| 2026-10-19T16:17:41+08:00 | `rectifying` | evidence_uploaded | 演示安全员 |
| 2026-10-19T16:17:48+08:00 | `pending_verification` | observation_confirmed | 演示安全员 |
| 2026-10-19T16:17:48+08:00 | `closed` | verification_passed | 演示安全员 |

## 6. 边界与假设

- 检查边线来自选定IFC构件上表面，临空性质需人工确认。
- 施工时间窗、人员点和责任主体为人工编制的演示输入。
- 图像观察及测量参数需人工确认，不把模型绝对标高当作坠落高度。

## 7. 任务理解与工具计划

```json
{
  "request": "检查所选楼板的人员暴露、防护状态、多工种时间与三维范围冲突，并核对巡检文字与确认观察的差异。",
  "zone_id": "ZONE-SELECTED-57CEAF2297",
  "as_of": "2019-05-29T08:34:40+08:00",
  "focus": [
    "all"
  ],
  "selected_tools": [
    "bim_query",
    "schedule_query",
    "evidence_check",
    "spatial_check",
    "rule_retrieval",
    "risk_assessment",
    "activity_conflict_check",
    "site_text_query"
  ],
  "retrieval_query": "临边防护栏杆高度与完整性 楼板边缘人员暴露 多工种交叉作业时间与三维范围冲突 巡检记录与现场观察差异 建筑施工高处作业规范",
  "needs_clarification": false,
  "clarification": "",
  "assumptions": [
    "所选区域为当前L05临边演示区域，其构件与标注边线数据已存在于当前模型与证据中"
  ],
  "context_inherited": true,
  "mode": "live_model"
}
```

## 8. Safety State

```json
{
  "case_id": "CASE-20261019-4CF647",
  "zone_id": "ZONE-SELECTED-57CEAF2297",
  "as_of": "2019-05-29T08:34:40+08:00",
  "model": {
    "id": "S1-bSDD-example",
    "version": "4075c44a6e47",
    "guids": [
      "2riKNFXuDAvQJxT4q2Dk7a"
    ]
  },
  "task_spec": {
    "request": "检查所选楼板的人员暴露、防护状态、多工种时间与三维范围冲突，并核对巡检文字与确认观察的差异。",
    "zone_id": "ZONE-SELECTED-57CEAF2297",
    "as_of": "2019-05-29T08:34:40+08:00",
    "focus": [
      "all"
    ],
    "selected_tools": [
      "bim_query",
      "schedule_query",
      "evidence_check",
      "spatial_check",
      "rule_retrieval",
      "risk_assessment",
      "activity_conflict_check",
      "site_text_query"
    ],
    "retrieval_query": "临边防护栏杆高度与完整性 楼板边缘人员暴露 多工种交叉作业时间与三维范围冲突 巡检记录与现场观察差异 建筑施工高处作业规范",
    "needs_clarification": false,
    "clarification": "",
    "assumptions": [
      "所选区域为当前L05临边演示区域，其构件与标注边线数据已存在于当前模型与证据中"
    ],
    "context_inherited": true,
    "mode": "live_model"
  },
  "activity": "05层板边多工种安全检查",
  "schedule": {
    "task_id": "TASK-SELECTED-57CEAF2297",
    "activity": "05层板边多工种安全检查",
    "planned_start": "2019-05-29T08:00:00+08:00",
    "planned_end": "2019-06-03T12:00:00+08:00",
    "as_of": "2019-05-29T08:34:40+08:00",
    "active": true,
    "owner": "演示协调员",
    "provenance": "human_authored_demo_schedule",
    "note": "用户编制的演示活动，关联实际选中IFC构件，非原项目实测进度。"
  },
  "evidence_ids": [
    "EV-UP-20261019-B981A9"
  ],
  "observations": {
    "guardrail_state": "present",
    "guardrail_height_m": 1.3,
    "worker_present": true,
    "drop_height_m": 2.5,
    "boundary_is_exposed": true,
    "guardrail_fixed": true,
    "guardrail_continuous": true,
    "ppe_confirmed": true,
    "worker_point_m": null,
    "simulated": true
  },
  "missing_fields": [],
  "bim_context": {
    "model_id": "S1-bSDD-example",
    "model_version": "4075c44a6e47",
    "schema": "IFC2X3",
    "storey_guid": "1Vhy2b2Mj9FRewx9CZZoux",
    "storey_name": "05 vijfde verdieping",
    "zone_id": "ZONE-SELECTED-57CEAF2297",
    "target_guid": "2riKNFXuDAvQJxT4q2Dk7a",
    "target_bbox_m": {
      "min": [
        22.540094872972695,
        21.67750176873051,
        17.210000000223516
      ],
      "max": [
        31.975119134447304,
        32.70503529991948,
        17.300000000149012
      ]
    },
    "elements": [
      {
        "model_id": "S1-bSDD-example",
        "guid": "2riKNFXuDAvQJxT4q2Dk7a",
        "ifc_class": "IfcSlab",
        "name": "IfcSlab - 43_DD_Floor_vloerafwerking 70-20",
        "storey_guid": "1Vhy2b2Mj9FRewx9CZZoux",
        "storey_name": "05 vijfde verdieping",
        "geometry_available": true,
        "bbox_m": {
          "min": [
            22.540094872972695,
            21.67750176873051,
            17.210000000223516
          ],
          "max": [
            31.975119134447304,
            32.70503529991948,
            17.300000000149012
          ]
        }
      }
    ],
    "nearby_elements": [
      {
        "guid": "0Mh0lDp2bByg5RpNcCER_H",
        "ifc_class": "IfcWall",
        "distance_m": 0.0,
        "relation": "bbox_overlap_candidate"
      },
      {
        "guid": "3JNpmVKIzB8P5CS1THKSgW",
        "ifc_class": "IfcWall",
        "distance_m": 0.0,
        "relation": "bbox_overlap_candidate"
      },
      {
        "guid": "0DFqg9H1n2_Q_5VlJfIHjP",
        "ifc_class": "IfcWall",
        "distance_m": 0.0,
        "relation": "bbox_overlap_candidate"
      },
      {
        "guid": "3e9cEngq19tPPMucIIh3tX",
        "ifc_class": "IfcWall",
        "distance_m": 0.0,
        "relation": "bbox_overlap_candidate"
      },
      {
        "guid": "2Ldd44_Hz30w7DxUKKMsJv",
        "ifc_class": "IfcWall",
        "distance_m": 0.0,
        "relation": "bbox_overlap_candidate"
      },
      {
        "guid": "0FOHK4aT910wgskSbVHn0U",
        "ifc_class": "IfcSlab",
        "distance_m": 0.05,
        "relation": "nearby_bbox"
      },
      {
        "guid": "2opE9$TM1F6wk9pl53XQlY",
        "ifc_class": "IfcWall",
        "distance_m": 0.1,
        "relation": "nearby_bbox"
      },
      {
        "guid": "3pjO8jOADErANGJwNGJrfU",
        "ifc_class": "IfcWall",
        "distance_m": 1.096,
        "relation": "nearby_bbox"
      }
    ],
    "spatial_context_method": "已加载区域几何的包围盒邻近候选；不是精确碰撞或全模型拓扑",
    "preview_scope": {
      "mesh_count": 35,
      "element_count_on_storey": 1247,
      "class_counts": {
        "IfcSlab": 4,
        "IfcWall": 31
      },
      "note": "首屏只加载 35 个区域预览对象；原始 IFC 仍为查询源，可按需提取选中构件。"
    },
    "geometry_source": "selected_ifc_top_surface_boundary"
  },
  "perception_candidates": [
    {
      "summary": "这是一张建筑工地的垂直俯拍照片，展示了正在施工的混凝土楼板层。画面中可见多名佩戴安全帽的工人分布在楼板上进行作业，周围散落着钢筋、木材和蓝色防护布等建筑材料。右侧矗立着一座橙黄色的塔式起重机。由于拍摄角度为垂直俯视且距离较远，无法清晰辨认边缘防护栏杆的具体细节或工人的面部特征及具体PPE穿戴情况。",
      "observation": {
        "guardrail_state": "unknown",
        "guardrail_height_m": null,
        "worker_present": true,
        "drop_height_m": null,
        "boundary_is_exposed": null,
        "guardrail_fixed": null,
        "guardrail_continuous": null,
        "ppe_confirmed": null,
        "worker_point_m": null
      },
      "image_kind": "photo",
      "visible_features": [
        "混凝土楼板",
        "钢筋网",
        "塔式起重机",
        "建筑工人",
        "安全帽",
        "建筑材料堆",
        "地面车辆",
        "周边住宅楼",
        "蓝色防尘布",
        "木质模板"
      ],
      "uncertainties": [
        "由于垂直俯视角度，难以确认楼板边缘是否安装了标准的防护栏杆",
        "距离较远，无法确认工人是否规范佩戴了安全带或其他个人防护装备",
        "无法从单张图片判断具体的坠落高度数值",
        "无法确认现有临时防护设施的固定强度和连续性"
      ],
      "status": "confirmed",
      "model": "qwen3.7-plus",
      "confirmed": true,
      "note": "模型观察候选，测量参数与现场性质需人工确认",
      "source": "simulated",
      "human_note": "演示编制观察；高度、固定情况和构件关联由人工模拟，不是图像模型测量或原项目实测。"
    }
  ],
  "spatial": {
    "zone_id": "ZONE-SELECTED-57CEAF2297",
    "point_m": [
      26.222088065083597,
      22.377949994460387,
      17.3
    ],
    "edge_segment_m": [
      [
        22.6451,
        21.6784,
        17.3
      ],
      [
        29.7989,
        21.6775,
        17.3
      ]
    ],
    "distance_m": 0.7,
    "nearest_point_m": [
      26.222,
      21.678,
      17.3
    ],
    "exposure_threshold_m": 1.0,
    "within_threshold": true,
    "aabb_candidate": true,
    "aabb_note": "AABB 只用于候选筛选，不作为碰撞或风险结论。",
    "drop_height_m": null,
    "drop_height_note": "坠落高度需另行测量或明确作为模拟观察录入。"
  },
  "coordination": {
    "configured": true,
    "revision": 1,
    "complete": true,
    "activities": [
      {
        "task_id": "ACT-P1-01",
        "activity": "板边材料转运",
        "trade": "运输班组",
        "owner": "演示运输负责人",
        "planned_start": "2019-05-29T08:00:00+08:00",
        "planned_end": "2019-05-29T10:00:00+08:00",
        "bim_guids": [
          "2riKNFXuDAvQJxT4q2Dk7a"
        ],
        "workspace": {
          "min": [
            24.222088065083597,
            20.377949994460387,
            17.3
          ],
          "max": [
            28.222088065083597,
            24.377949994460387,
            19.3
          ]
        }
      },
      {
        "task_id": "ACT-P1-02",
        "activity": "相邻区域安装",
        "trade": "安装班组",
        "owner": "演示安装负责人",
        "planned_start": "2019-05-29T09:00:00+08:00",
        "planned_end": "2019-05-29T11:00:00+08:00",
        "bim_guids": [
          "2riKNFXuDAvQJxT4q2Dk7a"
        ],
        "workspace": {
          "min": [
            25.222088065083597,
            21.377949994460387,
            17.3
          ],
          "max": [
            29.222088065083597,
            25.377949994460387,
            19.3
          ]
        }
      }
    ],
    "pairs": [
      {
        "pair_id": "ACT-P1-01__ACT-P1-02",
        "task_ids": [
          "ACT-P1-01",
          "ACT-P1-02"
        ],
        "activities": [
          "板边材料转运",
          "相邻区域安装"
        ],
        "owners": [
          "演示运输负责人",
          "演示安装负责人"
        ],
        "time_overlap": true,
        "overlap_start": "2019-05-29T09:00:00+08:00",
        "overlap_end": "2019-05-29T10:00:00+08:00",
        "spatial_overlap": true,
        "intersection_m": {
          "min": [
            25.222088065083597,
            21.377949994460387,
            17.3
          ],
          "max": [
            28.222088065083597,
            24.377949994460387,
            19.3
          ]
        },
        "distance_m": 0.0,
        "conflict": true,
        "active_at_check": false,
        "bim_guids": [
          "2riKNFXuDAvQJxT4q2Dk7a"
        ]
      }
    ],
    "conflicts": [
      {
        "pair_id": "ACT-P1-01__ACT-P1-02",
        "task_ids": [
          "ACT-P1-01",
          "ACT-P1-02"
        ],
        "activities": [
          "板边材料转运",
          "相邻区域安装"
        ],
        "owners": [
          "演示运输负责人",
          "演示安装负责人"
        ],
        "time_overlap": true,
        "overlap_start": "2019-05-29T09:00:00+08:00",
        "overlap_end": "2019-05-29T10:00:00+08:00",
        "spatial_overlap": true,
        "intersection_m": {
          "min": [
            25.222088065083597,
            21.377949994460387,
            17.3
          ],
          "max": [
            28.222088065083597,
            24.377949994460387,
            19.3
          ]
        },
        "distance_m": 0.0,
        "conflict": true,
        "active_at_check": false,
        "bim_guids": [
          "2riKNFXuDAvQJxT4q2Dk7a"
        ]
      }
    ],
    "missing_fields": [],
    "method": "time_interval_intersection_and_axis_aligned_work_volumes",
    "provenance": "human_authored_demo_schedule",
    "units": "m"
  },
  "site_text": {
    "facts": [
      {
        "field": "guardrail_state",
        "value": "present",
        "paragraph_id": "NOTE-A1E0E8D6D064:P1",
        "quote": "临边防护已设置",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      },
      {
        "field": "guardrail_height_m",
        "value": 1.3,
        "paragraph_id": "NOTE-A1E0E8D6D064:P1",
        "quote": "防护高度1.3m",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      },
      {
        "field": "worker_present",
        "value": false,
        "paragraph_id": "NOTE-A1E0E8D6D064:P2",
        "quote": "该区域未见人员",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      }
    ],
    "conflicts": [
      {
        "field": "worker_present",
        "value": false,
        "paragraph_id": "NOTE-A1E0E8D6D064:P2",
        "quote": "该区域未见人员",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00",
        "conflict_id": "NOTE-A1E0E8D6D064:P2:worker_present",
        "observation_hash": "172c6f6ecd1a828c5e317a23",
        "observation_value": true,
        "text_value": false,
        "evidence_id": "EV-UP-20261019-B981A9",
        "resolution": {
          "decision": "retain_observation",
          "reason": "演示记录中的无人描述与本Case已确认的模拟观察不一致；保留确认观察，将该文字记为不可靠。",
          "at": "2026-10-19T16:17:33+08:00"
        }
      }
    ],
    "pending_notes": [],
    "excluded_notes": [],
    "missing_fields": [],
    "complete": true
  },
  "provenance": "real_bim_and_simulated_site_observations",
  "incomplete": false
}
```

## 9. 决策包（分析时快照）

```json
{
  "case_id": "CASE-20261019-4CF647",
  "run_id": "RUN-20261019-BB90A3",
  "status": "candidate",
  "task": {
    "request": "检查所选楼板的人员暴露、防护状态、多工种时间与三维范围冲突，并核对巡检文字与确认观察的差异。",
    "zone_id": "ZONE-SELECTED-57CEAF2297",
    "as_of": "2019-05-29T08:34:40+08:00",
    "focus": [
      "all"
    ],
    "selected_tools": [
      "bim_query",
      "schedule_query",
      "evidence_check",
      "spatial_check",
      "rule_retrieval",
      "risk_assessment",
      "activity_conflict_check",
      "site_text_query"
    ],
    "retrieval_query": "临边防护栏杆高度与完整性 楼板边缘人员暴露 多工种交叉作业时间与三维范围冲突 巡检记录与现场观察差异 建筑施工高处作业规范",
    "needs_clarification": false,
    "clarification": "",
    "assumptions": [
      "所选区域为当前L05临边演示区域，其构件与标注边线数据已存在于当前模型与证据中"
    ],
    "context_inherited": true,
    "mode": "live_model"
  },
  "finding": {
    "finding_id": "F-001",
    "hazard": "已检查项未发现防护缺失或高度不足",
    "result": "no_issue_in_checked_items",
    "risk_level": "未判定",
    "bim_guids": [
      "2riKNFXuDAvQJxT4q2Dk7a"
    ],
    "evidence_ids": [
      "EV-UP-20261019-B981A9"
    ],
    "rule_ids": [
      "JGJ-4.3.1"
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
        "result": "pass",
        "source": "模拟观察",
        "note": ""
      },
      {
        "name": "防护高度 ≥ 1.2 m",
        "result": "pass",
        "source": "模拟观察（演示策略阈值）",
        "note": "1.2 m 只是一项检查，不证明锚固、强度、连续性和全部安全要求合格。"
      },
      {
        "name": "固定与连续性",
        "result": "pass",
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
        "note": "0.7 m ≤ 1.0 m 为演示项目策略，不是国家规范距离限值。"
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
      "guardrail_state": "present",
      "guardrail_height_m": 1.3,
      "worker_present": true,
      "boundary_is_exposed": true,
      "guardrail_fixed": true,
      "guardrail_continuous": true,
      "drop_height_m": 2.5
    },
    "narrative": {
      "summary": "05层板边多工种安全检查（CASE-20261019-4CF647，模型S1-bSDD-example 4075c44a6e47，区域ZONE-SELECTED-57CEAF2297，检查时刻2019-05-29T08:34:40+08:00）整体结论为 risk_candidate：已检查项（时间窗、证据匹配、字段完整性、防护存在性、模拟高度1.3m≥1.2m、固定连续性、人员暴露、距标注边线0.7m≤1.0m）未发现防护缺失或高度不足（F-001），但补充发现作业空间冲突待处置（F-SPACE-001）：板边材料转运与相邻区域安装在09:00-10:00时间交叠且三维作业范围相交，检查时刻未处于活动状态。巡检文字称该区域未见人员，与已确认模拟观察（worker_present=true）冲突，保留观察、将其记为不可靠。上述防护与人员数据均属人工模拟，非实测。",
      "reasoning_basis": [
        {
          "type": "evidence",
          "id": "EV-UP-20261019-B981A9"
        },
        {
          "type": "rule",
          "id": "JGJ-4.3.1"
        },
        {
          "type": "finding",
          "id": "F-001"
        },
        {
          "type": "finding",
          "id": "F-SPACE-001"
        },
        {
          "type": "guid",
          "id": "2riKNFXuDAvQJxT4q2Dk7a"
        }
      ],
      "uncertainties": [
        "防护栏杆高度1.3m、固定与连续性、人员在场及PPE均为人工模拟观察，未经现场确认，不构成真实合格结论。",
        "坠落高度2.5m为模拟录入，spatial_check未提供实测坠落基准面。",
        "巡检记录“该区域未见人员”与已确认模拟观察不一致，冲突已裁决保留观察，文字可靠性存疑。",
        "图像感知候选对护栏状态/高度、PPE、坠落高度均为unknown，需人工核对。",
        "F-SPACE-001基于人工编制的作业空间体与时间窗，不等同现场真实碰撞；检查时刻冲突未激活。",
        "邻近构件为包围盒邻近候选，非精确碰撞或全模型拓扑。",
        "JGJ-4.3.1为人工核对原文后的释义，未逐条现场验证栏杆构造细节。"
      ],
      "label": "真实模型输出（已校验）",
      "provider": "https://api.deepseek.com",
      "model": "deepseek-v4-flash"
    }
  },
  "evidence": [
    "EV-UP-20261019-B981A9"
  ],
  "governing_rules": [
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
      "score": 9.574
    }
  ],
  "risk": {
    "level": "未判定",
    "result": "no_issue_in_checked_items"
  },
  "controls": [
    {
      "control_id": "CTRL-F-SPACE-001",
      "finding_id": "F-SPACE-001",
      "kind": "coordination",
      "action": "在L05临边演示区域（ZONE-SELECTED-57CEAF2297，涉及IfcSlab 2riKNFXuDAvQJxT4q2Dk7a）对板边材料转运（ACT-P1-01）与相邻区域安装（ACT-P1-02）实施错时作业或调整三维作业范围，使09:00–10:00交叠时段及交叠体[25.222,21.378,17.3]–[28.222,24.378,19.3]内实现人员与相邻作业隔离；协同运输与安装负责人确认方案后，须复核调整后的时间窗和作业范围无时间及空间交叠、补充实施后证据并人工确认，方可开放该区域作业；复核前不得开放。",
      "owner": "演示协调员",
      "verification_requirements": [
        "保留批准活动及责任主体",
        "复核调整后的时间窗和作业范围",
        "提供实施后证据并人工确认"
      ],
      "verification_criteria": {
        "guardrail_required": false,
        "min_height_m": 1.2,
        "fixed_required": false,
        "continuous_required": false,
        "coordination_required": true,
        "manual_requirements": []
      },
      "version": 1,
      "status": "proposed",
      "provenance": "live_model_candidate_checked_against_tool_results"
    }
  ],
  "owners": [
    "演示协调员"
  ],
  "additional_findings": [
    {
      "finding_id": "F-SPACE-001",
      "kind": "coordination",
      "hazard": "作业空间冲突：板边材料转运 / 相邻区域安装",
      "result": "risk_candidate",
      "risk_level": "计划冲突待处置",
      "bim_guids": [
        "2riKNFXuDAvQJxT4q2Dk7a"
      ],
      "evidence_ids": [],
      "rule_ids": [],
      "task_ids": [
        "ACT-P1-01",
        "ACT-P1-02"
      ],
      "pair_id": "ACT-P1-01__ACT-P1-02",
      "checks": [
        {
          "name": "计划时间交叠",
          "result": "fail",
          "source": "activity_conflict_check"
        },
        {
          "name": "三维作业范围交叠",
          "result": "fail",
          "source": "activity_conflict_check"
        }
      ],
      "inputs": {
        "pair_id": "ACT-P1-01__ACT-P1-02",
        "task_ids": [
          "ACT-P1-01",
          "ACT-P1-02"
        ],
        "activities": [
          "板边材料转运",
          "相邻区域安装"
        ],
        "owners": [
          "演示运输负责人",
          "演示安装负责人"
        ],
        "time_overlap": true,
        "overlap_start": "2019-05-29T09:00:00+08:00",
        "overlap_end": "2019-05-29T10:00:00+08:00",
        "spatial_overlap": true,
        "intersection_m": {
          "min": [
            25.222088065083597,
            21.377949994460387,
            17.3
          ],
          "max": [
            28.222088065083597,
            24.377949994460387,
            19.3
          ]
        },
        "distance_m": 0.0,
        "conflict": true,
        "active_at_check": false,
        "bim_guids": [
          "2riKNFXuDAvQJxT4q2Dk7a"
        ]
      },
      "uncertainties": [],
      "provenance": "human_authored_demo_schedule",
      "scope_note": "基于编制的作业空间体与时间窗，不等同现场真实碰撞。"
    }
  ],
  "assumptions": [
    "检查边线来自选定IFC构件上表面，临空性质需人工确认。",
    "施工时间窗、人员点和责任主体为人工编制的演示输入。",
    "图像观察及测量参数需人工确认，不把模型绝对标高当作坠落高度。",
    "所选区域为当前L05临边演示区域，其构件与标注边线数据已存在于当前模型与证据中"
  ],
  "reviewer": "演示安全员（待人工审核）",
  "approval_required": true,
  "scope": "仅对选定检查项成立；审批和实施由人工操作",
  "mode": "live_model"
}
```

## 10. 范围与人员标注

```json
{
  "guid": "2riKNFXuDAvQJxT4q2Dk7a",
  "edge_index": 1,
  "edge_segment_m": [
    [
      22.6451,
      21.6784,
      17.3
    ],
    [
      29.7989,
      21.6775,
      17.3
    ]
  ],
  "worker_point_m": [
    26.222088065083597,
    22.377949994460387,
    17.3
  ],
  "worker_point_source": "simulated",
  "worker_point_provenance": "人工模拟标注",
  "distance_to_edge_m": 0.7,
  "boundary_confirmed": true,
  "exposure_threshold_m": 1.0,
  "target": {
    "guid": "2riKNFXuDAvQJxT4q2Dk7a",
    "bbox_m": {
      "min": [
        22.540094872972695,
        21.67750176873051,
        17.210000000223516
      ],
      "max": [
        31.975119134447304,
        32.70503529991948,
        17.300000000149012
      ]
    }
  },
  "geometry_source": "selected_ifc_top_surface_boundary"
}
```

## 11. 作业计划与版本

```json
{
  "case_id": "CASE-20261019-4CF647",
  "revision": 2,
  "updated_at": "2026-10-19T16:17:41+08:00",
  "activities": [
    {
      "task_id": "ACT-P1-01",
      "activity": "板边材料转运",
      "trade": "运输班组",
      "owner": "演示运输负责人",
      "planned_start": "2019-05-29T08:00:00+08:00",
      "planned_end": "2019-05-29T10:00:00+08:00",
      "bim_guids": [
        "2riKNFXuDAvQJxT4q2Dk7a"
      ],
      "workspace": {
        "min": [
          24.222088065083597,
          20.377949994460387,
          17.3
        ],
        "max": [
          28.222088065083597,
          24.377949994460387,
          19.3
        ]
      }
    },
    {
      "task_id": "ACT-P1-02",
      "activity": "相邻区域安装",
      "trade": "安装班组",
      "owner": "演示安装负责人",
      "planned_start": "2019-05-29T10:00:00+08:00",
      "planned_end": "2019-05-29T12:00:00+08:00",
      "bim_guids": [
        "2riKNFXuDAvQJxT4q2Dk7a"
      ],
      "workspace": {
        "min": [
          25.222088065083597,
          21.377949994460387,
          17.3
        ],
        "max": [
          29.222088065083597,
          25.377949994460387,
          19.3
        ]
      }
    }
  ],
  "history": [
    {
      "revision": 2,
      "reason": "按已批准措施将安装调整至转运结束后，保留范围和责任主体。",
      "at": "2026-10-19T16:17:41+08:00",
      "activities": [
        {
          "task_id": "ACT-P1-01",
          "activity": "板边材料转运",
          "trade": "运输班组",
          "owner": "演示运输负责人",
          "planned_start": "2019-05-29T08:00:00+08:00",
          "planned_end": "2019-05-29T10:00:00+08:00",
          "bim_guids": [
            "2riKNFXuDAvQJxT4q2Dk7a"
          ],
          "workspace": {
            "min": [
              24.222088065083597,
              20.377949994460387,
              17.3
            ],
            "max": [
              28.222088065083597,
              24.377949994460387,
              19.3
            ]
          }
        },
        {
          "task_id": "ACT-P1-02",
          "activity": "相邻区域安装",
          "trade": "安装班组",
          "owner": "演示安装负责人",
          "planned_start": "2019-05-29T10:00:00+08:00",
          "planned_end": "2019-05-29T12:00:00+08:00",
          "bim_guids": [
            "2riKNFXuDAvQJxT4q2Dk7a"
          ],
          "workspace": {
            "min": [
              25.222088065083597,
              21.377949994460387,
              17.3
            ],
            "max": [
              29.222088065083597,
              25.377949994460387,
              19.3
            ]
          }
        }
      ]
    },
    {
      "revision": 1,
      "reason": "编制同区域多工种交叉作业演示计划",
      "at": "2026-10-19T16:17:27+08:00",
      "activities": [
        {
          "task_id": "ACT-P1-01",
          "activity": "板边材料转运",
          "trade": "运输班组",
          "owner": "演示运输负责人",
          "planned_start": "2019-05-29T08:00:00+08:00",
          "planned_end": "2019-05-29T10:00:00+08:00",
          "bim_guids": [
            "2riKNFXuDAvQJxT4q2Dk7a"
          ],
          "workspace": {
            "min": [
              24.222088065083597,
              20.377949994460387,
              17.3
            ],
            "max": [
              28.222088065083597,
              24.377949994460387,
              19.3
            ]
          }
        },
        {
          "task_id": "ACT-P1-02",
          "activity": "相邻区域安装",
          "trade": "安装班组",
          "owner": "演示安装负责人",
          "planned_start": "2019-05-29T09:00:00+08:00",
          "planned_end": "2019-05-29T11:00:00+08:00",
          "bim_guids": [
            "2riKNFXuDAvQJxT4q2Dk7a"
          ],
          "workspace": {
            "min": [
              25.222088065083597,
              21.377949994460387,
              17.3
            ],
            "max": [
              29.222088065083597,
              25.377949994460387,
              19.3
            ]
          }
        }
      ]
    }
  ]
}
```

## 12. 现场文本、段落引用与澄清

```json
{
  "notes": [
    {
      "note_id": "NOTE-A1E0E8D6D064",
      "case_id": "CASE-20261019-4CF647",
      "document_id": "NOTE-A1E0E8D6D064",
      "version": 1,
      "title": "05层巡检记录（演示编制）",
      "source": "人工编制的演示巡检记录",
      "captured_at": "2019-05-29T08:30:00+08:00",
      "zone_id": "ZONE-SELECTED-57CEAF2297",
      "model_version": "4075c44a6e47",
      "body": "临边防护已设置，防护高度1.3m。\n该区域未见人员。",
      "created_at": "2026-10-19T16:17:27+08:00",
      "paragraphs": [
        {
          "id": "NOTE-A1E0E8D6D064:P1",
          "text": "临边防护已设置，防护高度1.3m。"
        },
        {
          "id": "NOTE-A1E0E8D6D064:P2",
          "text": "该区域未见人员。"
        }
      ],
      "analysis": {
        "summary": "巡检记录显示临边防护设施已设置，记录高度为1.3m；区域未见人员。",
        "facts": [
          {
            "field": "guardrail_state",
            "value": "present",
            "paragraph_id": "NOTE-A1E0E8D6D064:P1",
            "quote": "临边防护已设置"
          },
          {
            "field": "guardrail_height_m",
            "value": 1.3,
            "paragraph_id": "NOTE-A1E0E8D6D064:P1",
            "quote": "防护高度1.3m"
          },
          {
            "field": "worker_present",
            "value": false,
            "paragraph_id": "NOTE-A1E0E8D6D064:P2",
            "quote": "该区域未见人员"
          }
        ],
        "uncertainties": [],
        "model": "deepseek-v4-flash",
        "extracted_at": "2026-10-19T16:17:30+08:00"
      },
      "bim_guids": [
        "2riKNFXuDAvQJxT4q2Dk7a"
      ],
      "current": true
    }
  ],
  "context": {
    "facts": [
      {
        "field": "guardrail_state",
        "value": "present",
        "paragraph_id": "NOTE-A1E0E8D6D064:P1",
        "quote": "临边防护已设置",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      },
      {
        "field": "guardrail_height_m",
        "value": 1.3,
        "paragraph_id": "NOTE-A1E0E8D6D064:P1",
        "quote": "防护高度1.3m",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      },
      {
        "field": "worker_present",
        "value": false,
        "paragraph_id": "NOTE-A1E0E8D6D064:P2",
        "quote": "该区域未见人员",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00"
      }
    ],
    "conflicts": [
      {
        "field": "worker_present",
        "value": false,
        "paragraph_id": "NOTE-A1E0E8D6D064:P2",
        "quote": "该区域未见人员",
        "note_id": "NOTE-A1E0E8D6D064",
        "title": "05层巡检记录（演示编制）",
        "source": "人工编制的演示巡检记录",
        "version": 1,
        "captured_at": "2019-05-29T08:30:00+08:00",
        "conflict_id": "NOTE-A1E0E8D6D064:P2:worker_present",
        "observation_hash": "172c6f6ecd1a828c5e317a23",
        "observation_value": true,
        "text_value": false,
        "evidence_id": "EV-UP-20261019-B981A9",
        "resolution": {
          "decision": "retain_observation",
          "reason": "演示记录中的无人描述与本Case已确认的模拟观察不一致；保留确认观察，将该文字记为不可靠。",
          "at": "2026-10-19T16:17:33+08:00"
        }
      }
    ],
    "pending_notes": [],
    "excluded_notes": [],
    "missing_fields": [],
    "complete": true
  }
}
```

---

本导出不替代真实安全审批，不证明现场合规，不构成事故概率判断。
