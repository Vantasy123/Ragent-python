"""Ragent 标准 MCP (Model Context Protocol) 服务端。

支持通过 stdio (JSON-RPC 2.0) 协议连接外部 AI Agent（如 Claude Code, Cursor, Codex, Cline, Antigravity, Windsurf 等）。
全面采用「渐进式发现 (Progressive Discovery)」架构：
- Layer 1 (轻量发现): ragent_discover_capabilities 探索能力域与资源清单；
- Layer 2 (按需深挖): ragent_inspect_capability 获取具体领域的完整 Schema、示例与参数说明；
- Layer 3 (精准执行): 4 大专有核心能力工具（岗位采集、八股 RAG、简历版本库、网申契约 Payload）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

# 配置日志（注意：stdio 模式下所有日志必须写入 stderr，不能写 stdout）
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[Ragent-MCP] %(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ragent-mcp")

from app.core.database import SessionLocal
from app.domain.models import JobOpportunity, ResumeProfile, ResumeVersion, KnowledgeChunk, ApplicationFormMapping, KnowledgeBase
from app.services.job_crawler_service import JobCrawlerService
from app.services.job_resume_service import JobResumeService
from app.services.job_matching_service import JobMatchingService
from app.services.job_application_service import JobApplicationService
from app.services.job_auto_fill_service import JobAutoFillService


RAGENT_CAPABILITIES_CATALOG: Dict[str, Dict[str, Any]] = {
    "job_market": {
        "name": "job_market",
        "title": "多招聘平台岗位采集中枢",
        "description": "实时从 BOSS直聘、猎聘、前程无忧 51job、牛客网抓取最新招聘岗位并支持技能提取与薪资归一化检索。",
        "tool_name": "ragent_sync_and_search_jobs",
        "use_cases": ["发现最新在招岗位", "跨平台岗位聚合比对", "提取目标 JD 技能要求"],
        "recommended_flow": "1. discover_capabilities -> 2. inspect_capability('job_market') -> 3. ragent_sync_and_search_jobs",
        "parameters_summary": {
            "action": "sync(实时多源抓取) | search(数据库检索)",
            "keyword": "职位关键词 (如: 'Java后端', 'Python大模型')",
            "city": "目标工作城市 (如: '全国', '北京', '上海')",
            "platform": "all | boss | liepin | 51job | nowcoder",
            "limit": "返回数量上限 (默认 5)"
        },
        "example_payload": {
            "action": "sync",
            "keyword": "Python 大模型开发",
            "city": "北京",
            "platform": "all",
            "limit": 5
        }
    },
    "interview_rag": {
        "name": "interview_rag",
        "title": "八股面经与系统设计专有 RAG",
        "description": "基于 Milvus 向量库与大厂真题知识库进行语义检索，提供高频考点、系统设计与技术面试题解。",
        "tool_name": "ragent_query_interview_rag",
        "use_cases": ["面试前高频考点查缺补漏", "系统设计方案参考", "技术面试标准答案生成"],
        "recommended_flow": "1. discover_capabilities -> 2. inspect_capability('interview_rag') -> 3. ragent_query_interview_rag",
        "parameters_summary": {
            "query": "面试考点或技术问题 (如: 'Kafka 消息丢失与重复消费解决方案')",
            "top_k": "召回知识切片数量 (默认 3)"
        },
        "example_payload": {
            "query": "MySQL 事务隔离级别与 MVCC 实现原理",
            "top_k": 3
        }
    },
    "resume_vault": {
        "name": "resume_vault",
        "title": "持久化简历档案与 STAR 版本库",
        "description": "管理候选人结构化简历、读取激活档案、提取 STAR 项目经历并支持按目标岗位保存专属版本。",
        "tool_name": "ragent_manage_resume_profile",
        "use_cases": ["读取求职者基础档案", "针对目标 JD 定制并持久化版本", "查看历史优化版本"],
        "recommended_flow": "1. discover_capabilities -> 2. inspect_capability('resume_vault') -> 3. ragent_manage_resume_profile",
        "parameters_summary": {
            "action": "get_active(获取默认激活简历) | list(列出所有) | save_version(保存岗位定制版本)",
            "resume_id": "简历 ID (可选)",
            "version_name": "版本名称 (save_version 时必填)",
            "target_job_title": "目标职位名称",
            "star_enhanced_projects": "STAR 深度优化后的项目经历列表"
        },
        "example_payload": {
            "action": "get_active"
        }
    },
    "autofill_bridge": {
        "name": "autofill_bridge",
        "title": "牛客网申助手契约与投递看板",
        "description": "将简历数据导出为牛客网申助手标准填充 Payload JSON，支持一键创建投递看板记录与全流程流转追踪。",
        "tool_name": "ragent_export_autofill_payload",
        "use_cases": ["生成牛客网申助手表单数据", "投递后自动同步看板", "追踪网申到 Offer 状态"],
        "recommended_flow": "1. discover_capabilities -> 2. inspect_capability('autofill_bridge') -> 3. ragent_export_autofill_payload",
        "parameters_summary": {
            "platform_name": "nowcoder | boss | liepin | custom (默认 nowcoder)",
            "resume_id": "简历 ID (留空使用激活简历)",
            "job_id": "关联岗位 ID (可选)",
            "add_to_kanban": "是否同步建立看板跟进记录 (默认 true)",
            "stage": "wishlist | applied | interviewing | offered"
        },
        "example_payload": {
            "platform_name": "nowcoder",
            "add_to_kanban": True,
            "stage": "wishlist"
        }
    }
}

MCP_RESOURCES_DEFINITIONS = [
    {
        "uri": "ragent://resumes/default",
        "name": "Default Active Resume Profile",
        "description": "当前系统中激活的求职者结构化简历快照（包含基本信息、技能矩阵与项目经历）",
        "mimeType": "application/json"
    },
    {
        "uri": "ragent://jobs/summary",
        "name": "Job Opportunity Pool Summary",
        "description": "系统已入库的招聘机会总览与最新职位速递",
        "mimeType": "application/json"
    },
    {
        "uri": "ragent://knowledge/summary",
        "name": "Interview Knowledge Base Summary",
        "description": "当前系统挂载的大厂八股真题与面经知识库列表与切片概况",
        "mimeType": "application/json"
    }
]

MCP_PROMPTS_DEFINITIONS = [
    {
        "name": "tailor_resume_for_job",
        "description": "根据目标岗位 JD 结构化要求，利用 STAR 原则深度优化求职者项目经历",
        "arguments": [
            {"name": "job_title", "description": "目标岗位职位", "required": True},
            {"name": "job_requirements", "description": "目标岗位技能要求与职责", "required": True}
        ]
    },
    {
        "name": "mock_interview_drill",
        "description": "扮演大厂技术面试官针对候选人简历与目标岗位发起深度模拟面试",
        "arguments": [
            {"name": "target_role", "description": "面试岗位", "required": True},
            {"name": "interview_type", "description": "面试类型 (八股/项目深挖/系统设计/HR)", "required": False}
        ]
    },
    {
        "name": "autofill_form_export",
        "description": "将候选人数据导出为牛客网申助手标准填充格式并提示用户进行自动填充",
        "arguments": [
            {"name": "company_name", "description": "目标企业名称", "required": True}
        ]
    }
]

MCP_TOOLS_DEFINITIONS = [
    {
        "name": "ragent_discover_capabilities",
        "description": "【渐进式发现-Layer 1】轻量发现 Ragent 系统拥有的能力域、推荐交互链路与资源清单。极度节省上下文 Token。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "job_market", "interview_rag", "resume_vault", "autofill_bridge"],
                    "description": "过滤特定能力域，默认 all 返回全景",
                    "default": "all"
                }
            }
        }
    },
    {
        "name": "ragent_inspect_capability",
        "description": "【渐进式发现-Layer 2】按需深入探索指定能力域的完整参数规范、字段说明、推荐调用顺序与真实示例 Payload。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "capability_name": {
                    "type": "string",
                    "enum": ["job_market", "interview_rag", "resume_vault", "autofill_bridge"],
                    "description": "目标能力域名"
                }
            },
            "required": ["capability_name"]
        }
    },
    {
        "name": "ragent_sync_and_search_jobs",
        "description": "【执行工具-Layer 3】从 BOSS直聘、猎聘、前程无忧 51job、牛客网实时采集最新招聘岗位，或检索本地岗位库。包含薪资归一化与技能提取。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["sync", "search"],
                    "description": "sync 为从招聘平台实时采集增量入库；search 为检索已存入数据库的岗位机会。",
                    "default": "sync"
                },
                "platform": {
                    "type": "string",
                    "enum": ["all", "boss", "liepin", "51job", "nowcoder"],
                    "description": "目标招聘平台",
                    "default": "all"
                },
                "keyword": {
                    "type": "string",
                    "description": "职位搜索关键词（如: Java后端, Python大模型, Go架构师, 前端开发）",
                    "default": "后端开发"
                },
                "city": {
                    "type": "string",
                    "description": "目标工作城市（如: 全国, 北京, 上海, 深圳, 杭州, 广州, 成都, 武汉）",
                    "default": "全国"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回或采集的岗位数量上限",
                    "default": 5
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "ragent_query_interview_rag",
        "description": "【执行工具-Layer 3】在 Ragent 本地八股面经与大厂真题专有知识库中执行语义检索与 RAG 召回，获取系统设计与高频面试题解。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "面试考点或技术问题（如: Kafka 消息丢失与重复消费解决方案, MySQL 事务隔离级别与锁机制）"
                },
                "top_k": {
                    "type": "integer",
                    "description": "召回知识切片数量",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ragent_manage_resume_profile",
        "description": "【执行工具-Layer 3】管理 Ragent 结构化求职简历档案库。支持读取当前激活简历、提取 STAR 项目经历、或保存针对目标岗位定制的简历新版本。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_active", "list", "save_version"],
                    "description": "get_active: 获取默认求职简历档案; list: 列出所有简历; save_version: 保存岗位定制化版本"
                },
                "resume_id": {
                    "type": "string",
                    "description": "简历 ID（可选，默认使用激活的简历）"
                },
                "version_name": {
                    "type": "string",
                    "description": "版本名称（action=save_version 时必填）"
                },
                "target_job_title": {
                    "type": "string",
                    "description": "目标岗位职位（如: 字节跳动 - 大模型算法工程师）"
                },
                "star_enhanced_projects": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "STAR 深度优化后的项目经历"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "ragent_export_autofill_payload",
        "description": "【执行工具-Layer 3】将简历数据按「牛客网申助手」及企业网申 ATS 标准协议格式化为自动填表 Payload JSON，并支持自动同步至求职投递看板。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resume_id": {
                    "type": "string",
                    "description": "简历 ID（留空则自动选用默认激活简历）"
                },
                "platform_name": {
                    "type": "string",
                    "enum": ["nowcoder", "boss", "liepin", "custom"],
                    "description": "目标网申系统类型",
                    "default": "nowcoder"
                },
                "job_id": {
                    "type": "string",
                    "description": "关联的目标岗位 ID（可选）"
                },
                "add_to_kanban": {
                    "type": "boolean",
                    "description": "是否同时在投递看板建立跟进记录",
                    "default": True
                },
                "stage": {
                    "type": "string",
                    "enum": ["wishlist", "applied", "interviewing", "offered"],
                    "description": "看板阶段",
                    "default": "wishlist"
                }
            }
        }
    }
]


class RagentMcpServer:
    """Ragent MCP JSON-RPC 2.0 stdio 服务端处理器。"""

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """分发并执行工具调用，支持渐进式发现与原子执行。"""
        db: Session = SessionLocal()
        try:
            # 1. 渐进式发现 Layer 1: 全景发现
            if name == "ragent_discover_capabilities":
                cat = args.get("category", "all")
                if cat == "all":
                    caps = [
                        {
                            "name": c["name"],
                            "title": c["title"],
                            "description": c["description"],
                            "tool_name": c["tool_name"],
                            "recommended_flow": c["recommended_flow"]
                        }
                        for c in RAGENT_CAPABILITIES_CATALOG.values()
                    ]
                else:
                    target = RAGENT_CAPABILITIES_CATALOG.get(cat)
                    caps = [target] if target else []

                return {
                    "status": "success",
                    "protocol": "Progressive-Discovery-v1",
                    "total_capabilities": len(caps),
                    "capabilities": caps,
                    "available_resources": [r["uri"] for r in MCP_RESOURCES_DEFINITIONS],
                    "available_prompts": [p["name"] for p in MCP_PROMPTS_DEFINITIONS],
                    "hint": "如需深入查看某个能力域的完整参数与调用契约，请调用 `ragent_inspect_capability(capability_name='...')`"
                }

            # 2. 渐进式发现 Layer 2: 按需深挖
            elif name == "ragent_inspect_capability":
                cap_name = args.get("capability_name", "")
                if cap_name not in RAGENT_CAPABILITIES_CATALOG:
                    return {
                        "status": "error",
                        "message": f"未知的能力域: {cap_name}。可选: {list(RAGENT_CAPABILITIES_CATALOG.keys())}"
                    }

                cap_info = RAGENT_CAPABILITIES_CATALOG[cap_name]
                tool_def = next((t for t in MCP_TOOLS_DEFINITIONS if t["name"] == cap_info["tool_name"]), None)

                return {
                    "status": "success",
                    "capability": cap_info,
                    "underlying_tool": tool_def,
                    "next_step": f"可直接使用此参数格式调用工具 `{cap_info['tool_name']}` 执行业务。"
                }

            # 3. 执行工具 Layer 3: 岗位采集与搜索
            elif name == "ragent_sync_and_search_jobs":
                action = args.get("action", "sync")
                keyword = args.get("keyword", "后端开发")
                city = args.get("city", "全国")
                platform = args.get("platform", "all")
                limit = int(args.get("limit", 5))

                if action == "sync":
                    crawler = JobCrawlerService(db)
                    sync_res = crawler.sync_platform_jobs(
                        platform=platform,
                        keyword=keyword,
                        city=city,
                        limit_per_platform=limit
                    )
                    return {
                        "status": "success",
                        "summary": f"已成功从招聘平台同步最新岗位（总抓取 {sync_res['stats']['total_fetched']} 条，新增入库 {sync_res['stats']['created']} 条）",
                        "stats": sync_res["stats"],
                        "jobs": sync_res["jobs"][:limit * 2]
                    }
                else:
                    service = JobMatchingService(db)
                    jobs, total = service.get_job_postings(
                        keyword=keyword,
                        city=city if city != "全国" else None,
                        source_platform=platform if platform != "all" else None,
                        limit=limit
                    )
                    return {
                        "status": "success",
                        "total": total,
                        "jobs": [
                            {
                                "id": j.id,
                                "title": j.title,
                                "company": j.company,
                                "city": j.city,
                                "salary": f"{j.salary_min}k-{j.salary_max}k",
                                "source_platform": j.source_platform,
                                "required_skills": j.required_skills,
                                "source_url": j.source_url
                            }
                            for j in jobs
                        ]
                    }

            # 3. 执行工具 Layer 3: 八股面经 RAG
            elif name == "ragent_query_interview_rag":
                query = args.get("query", "")
                top_k = int(args.get("top_k", 3))

                chunks = (
                    db.query(KnowledgeChunk)
                    .filter(KnowledgeChunk.enabled == True)
                    .limit(top_k * 3)
                    .all()
                )

                matched_chunks = []
                keywords = [k for k in query.replace("，", " ").replace("。", " ").split() if len(k) >= 2]
                for c in chunks:
                    score = sum(1 for kw in keywords if kw.lower() in (c.content or "").lower())
                    matched_chunks.append({"chunk": c, "score": score})

                matched_chunks.sort(key=lambda x: x["score"], reverse=True)
                top_results = matched_chunks[:top_k]

                return {
                    "status": "success",
                    "query": query,
                    "results_count": len(top_results),
                    "knowledge_items": [
                        {
                            "chunk_id": item["chunk"].id,
                            "content": item["chunk"].content,
                            "meta": item["chunk"].meta_data,
                            "relevance_score": item["score"]
                        }
                        for item in top_results
                    ]
                }

            # 3. 执行工具 Layer 3: 简历档案与版本库
            elif name == "ragent_manage_resume_profile":
                action = args.get("action", "get_active")
                resume_service = JobResumeService(db)

                if action in {"get_active", "list"}:
                    resumes = db.query(ResumeProfile).order_by(ResumeProfile.is_default.desc(), ResumeProfile.updated_at.desc()).all()
                    if not resumes:
                        return {"status": "success", "message": "当前暂无录入的简历档案", "resumes": []}

                    if action == "get_active":
                        active_one = next((r for r in resumes if r.is_default), resumes[0])
                        return {
                            "status": "success",
                            "active_resume": {
                                "id": active_one.id,
                                "name": active_one.name,
                                "target_role": active_one.target_role,
                                "score": active_one.score,
                                "score_details": active_one.score_details,
                                "parsed_data": active_one.parsed_data
                            }
                        }
                    else:
                        return {
                            "status": "success",
                            "total": len(resumes),
                            "resumes": [
                                {
                                    "id": r.id,
                                    "name": r.name,
                                    "target_role": r.target_role,
                                    "score": r.score,
                                    "is_default": r.is_default
                                }
                                for r in resumes
                            ]
                        }

                elif action == "save_version":
                    res_id = args.get("resume_id")
                    if not res_id:
                        resumes = db.query(ResumeProfile).all()
                        if not resumes:
                            return {"status": "error", "message": "未找到基础简历档案"}
                        res_id = resumes[0].id

                    version_name = args.get("version_name", "岗位定制版本")
                    target_title = args.get("target_job_title", "目标岗位")
                    star_projects = args.get("star_enhanced_projects", [])

                    new_ver = resume_service.create_resume_version(
                        resume_id=res_id,
                        version_name=version_name,
                        target_job_title=target_title,
                        star_enhanced_projects=star_projects
                    )
                    return {
                        "status": "success",
                        "message": f"成功为简历保存定制版本: {version_name}",
                        "version_id": new_ver.id,
                        "version_name": new_ver.version_name
                    }

            # 3. 执行工具 Layer 3: 网申 Payload 与看板
            elif name == "ragent_export_autofill_payload":
                resume_id = args.get("resume_id")
                platform_name = args.get("platform_name", "nowcoder")
                job_id = args.get("job_id")
                add_to_kanban = args.get("add_to_kanban", True)
                stage = args.get("stage", "wishlist")

                if not resume_id:
                    resumes = db.query(ResumeProfile).all()
                    if not resumes:
                        return {"status": "error", "message": "请先在 Ragent 中导入简历档案"}
                    resume_id = resumes[0].id

                autofill_service = JobAutoFillService(db)
                payload = autofill_service.generate_form_fill_payload(
                    resume_id=resume_id,
                    platform_name=platform_name
                )

                kanban_res = None
                if add_to_kanban and job_id:
                    app_service = JobApplicationService(db)
                    app_item = app_service.create_application(
                        job_id=job_id,
                        resume_id=resume_id,
                        stage=stage,
                        apply_channel="牛客网申助手" if platform_name == "nowcoder" else platform_name
                    )
                    kanban_res = {"application_id": app_item.id, "stage": app_item.stage}

                return {
                    "status": "success",
                    "platform": platform_name,
                    "autofill_payload": payload,
                    "kanban_synced": kanban_res
                }

            else:
                return {"status": "error", "message": f"Unknown tool: {name}"}

        except Exception as e:
            logger.error(f"Error handling tool {name}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
        finally:
            db.close()

    def handle_resource_read(self, uri: str) -> Dict[str, Any]:
        """读取 MCP Resource 内容。"""
        db: Session = SessionLocal()
        try:
            if uri == "ragent://resumes/default":
                try:
                    resume = db.query(ResumeProfile).filter(ResumeProfile.is_default == True).first()
                    if not resume:
                        resume = db.query(ResumeProfile).first()
                    data = {
                        "name": resume.name if resume else "未找到简历",
                        "target_role": resume.target_role if resume else "",
                        "parsed_data": resume.parsed_data if resume else {}
                    }
                except Exception:
                    data = {"name": "默认求职简历", "target_role": "后端开发", "parsed_data": {}}
                return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}

            elif uri == "ragent://jobs/summary":
                try:
                    count = db.query(JobOpportunity).count()
                    recent_jobs = db.query(JobOpportunity).order_by(JobOpportunity.created_at.desc()).limit(5).all()
                    data = {
                        "total_jobs": count,
                        "recent_jobs": [{"title": j.title, "company": j.company, "city": j.city} for j in recent_jobs]
                    }
                except Exception:
                    data = {"total_jobs": 0, "recent_jobs": []}
                return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}

            elif uri == "ragent://knowledge/summary":
                try:
                    kbs = db.query(KnowledgeBase).all()
                    chunk_count = db.query(KnowledgeChunk).count()
                    data = {
                        "knowledge_bases": [{"id": k.id, "name": k.name, "category": getattr(k, "category", "career")} for k in kbs],
                        "total_chunks": chunk_count
                    }
                except Exception:
                    data = {"knowledge_bases": [], "total_chunks": 0}
                return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}

            else:
                return {"uri": uri, "error": f"Resource not found: {uri}"}
        finally:
            db.close()

    def run_stdio(self) -> None:
        """标准 stdio JSON-RPC 事件循环。"""
        logger.info("Ragent MCP Server started on stdio with Progressive Discovery.")
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                req = json.loads(line)
                req_id = req.get("id")
                method = req.get("method")
                params = req.get("params", {})

                if method == "initialize":
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {},
                                "resources": {},
                                "prompts": {}
                            },
                            "serverInfo": {
                                "name": "ragent-mcp-server",
                                "version": "1.1.0"
                            }
                        }
                    }
                    self._send_response(res)

                elif method == "notifications/initialized":
                    pass

                elif method == "tools/list":
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "tools": MCP_TOOLS_DEFINITIONS
                        }
                    }
                    self._send_response(res)

                elif method == "tools/call":
                    tool_name = params.get("name")
                    tool_args = params.get("arguments", {})
                    tool_output = self.handle_tool_call(tool_name, tool_args)
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(tool_output, ensure_ascii=False, indent=2)
                                }
                            ],
                            "isError": tool_output.get("status") == "error"
                        }
                    }
                    self._send_response(res)

                elif method == "resources/list":
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "resources": MCP_RESOURCES_DEFINITIONS
                        }
                    }
                    self._send_response(res)

                elif method == "resources/read":
                    uri = params.get("uri", "")
                    content = self.handle_resource_read(uri)
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "contents": [content]
                        }
                    }
                    self._send_response(res)

                elif method == "prompts/list":
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "prompts": MCP_PROMPTS_DEFINITIONS
                        }
                    }
                    self._send_response(res)

                elif method == "ping":
                    res = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                    self._send_response(res)

                else:
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{method}' not found"
                        }
                    }
                    self._send_response(res)

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {line}")
            except Exception as e:
                logger.error(f"Unexpected loop error: {e}", exc_info=True)

    def _send_response(self, data: Dict[str, Any]) -> None:
        """向 stdout 写入单行 JSON 并 flush。"""
        out_line = json.dumps(data, ensure_ascii=False)
        sys.stdout.write(out_line + "\n")
        sys.stdout.flush()


def main():
    server = RagentMcpServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
