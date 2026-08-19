"""Ragent 标准 MCP (Model Context Protocol) 服务端。

支持通过 stdio (JSON-RPC 2.0) 协议连接外部 AI Agent（如 Claude Code, Cursor, Codex, Cline, Antigravity, Windsurf 等）。
只暴露 Ragent 独有的 4 大专有能力：
1. ragent_sync_and_search_jobs: 多招聘平台（BOSS直聘/猎聘/51job/牛客网）真实岗位实时采集与检索；
2. ragent_query_interview_rag: 八股面经与大厂真题专有向量知识库检索；
3. ragent_manage_resume_profile: 求职者结构化简历档案、STAR 项目库与多版本持久化；
4. ragent_export_autofill_payload: 网申自动填表标准 Payload（牛客网申助手契约）与投递看板流转。
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
from app.domain.models import JobOpportunity, ResumeProfile, ResumeVersion, KnowledgeChunk, ApplicationFormMapping
from app.services.job_crawler_service import JobCrawlerService
from app.services.job_resume_service import JobResumeService
from app.services.job_matching_service import JobMatchingService
from app.services.job_application_service import JobApplicationService
from app.services.job_auto_fill_service import JobAutoFillService

MCP_TOOLS_DEFINITIONS = [
    {
        "name": "ragent_sync_and_search_jobs",
        "description": "从 BOSS直聘、猎聘、前程无忧 51job、牛客网实时采集最新招聘岗位，或检索本地岗位库。包含薪资归一化与大模型结构化技能提取。",
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
        "description": "在 Ragent 本地八股面经与大厂真题专有知识库中执行语义检索与 RAG 召回，获取系统设计、分布式架构与高频面试题解。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "面试考点或技术问题（如: Kafka 消息丢失与重复消费解决方案, MySQL 事务隔离级别与锁机制, Redis 缓存穿透与击穿）"
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
        "description": "管理 Ragent 结构化求职简历档案库。支持读取当前激活简历、提取 STAR 项目经历、或保存针对目标岗位定制的简历新版本。",
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
        "description": "将简历数据按「牛客网申助手」及企业网申 ATS 标准协议格式化为自动填表 Payload JSON，并支持自动同步至求职投递看板。",
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
        """分发并执行工具调用。"""
        db: Session = SessionLocal()
        try:
            if name == "ragent_sync_and_search_jobs":
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

            elif name == "ragent_query_interview_rag":
                query = args.get("query", "")
                top_k = int(args.get("top_k", 3))

                # 查询知识切片
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

    def run_stdio(self) -> None:
        """标准 stdio JSON-RPC 事件循环。"""
        logger.info("Ragent MCP Server started on stdio.")
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
                                "tools": {}
                            },
                            "serverInfo": {
                                "name": "ragent-mcp-server",
                                "version": "1.0.0"
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
