"""智能求职 Agent 专属工具套件（JobToolkit）：提供简历解析、岗位匹配、话术生成、模拟面试与网申填表全套工具。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, Base, engine
from app.services.job_resume_service import JobResumeService
from app.services.job_matching_service import JobMatchingService
from app.services.mock_interview_service import MockInterviewService
from app.services.job_auto_fill_service import JobAutoFillService
from app.services.schema_migrations import run_compatible_migrations

logger = logging.getLogger(__name__)


class JobToolkit:
    """提供给 ReAct Agent 与求职工作流调用的高阶求职工具集。"""

    @classmethod
    def parse_resume(cls, raw_text: str) -> Dict[str, Any]:
        """解析简历文本为结构化 JSON 档案。"""
        try:
            db: Session = SessionLocal()
            service = JobResumeService(db)
            parsed = service.parse_resume_text(raw_text)
            score, score_details = service.calculate_resume_score(parsed)
            db.close()
            return {
                "success": True,
                "parsed_data": parsed,
                "score": score,
                "score_details": score_details
            }
        except Exception as e:
            logger.warning(f"parse_resume failed: {e}")
            return {
                "success": False,
                "status": "failed",
                "error_code": "RESUME_PARSE_FAILED",
                "error": str(e),
            }

    @classmethod
    def optimize_project_star(cls, project_name: str, tech_stack: List[str], background: str, target_jd: str = "") -> Dict[str, Any]:
        """使用 STAR 框架深度润色项目经历。"""
        try:
            db: Session = SessionLocal()
            service = JobResumeService(db)
            res = service.optimize_project_star({
                "project_name": project_name,
                "tech_stack": tech_stack,
                "background": background
            }, target_jd=target_jd)
            db.close()
            return {
                "success": True,
                "star_optimized": res
            }
        except Exception as e:
            logger.warning(f"optimize_project_star failed: {e}")
            return {
                "success": False,
                "status": "failed",
                "error_code": "PROJECT_OPTIMIZATION_FAILED",
                "error": str(e),
            }

    @staticmethod
    def _salary_text(job: Any) -> str:
        if getattr(job, "salary_status", "unknown") == "negotiable":
            return "面议"
        if getattr(job, "salary_status", "unknown") == "unknown":
            return "薪资未知"
        return f"{job.salary_min}k-{job.salary_max}k"

    @classmethod
    def search_jobs(
        cls,
        keyword: str = "",
        city: str = "全国",
        job_type: str = "all",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """检索本地岗位库，不访问外部招聘平台。"""
        try:
            Base.metadata.create_all(bind=engine)
            run_compatible_migrations(engine)
            db: Session = SessionLocal()
            service = JobMatchingService(db)
            jobs, total = service.get_job_postings(keyword=keyword, city=city, job_type=job_type, limit=limit)
            db.close()
            if total > 0:
                return {
                    "success": True,
                    "status": "success",
                    "total": total,
                    "jobs": [
                        {
                            "id": j.id,
                            "title": j.title,
                            "company": j.company,
                            "city": j.city,
                            "salary": cls._salary_text(j),
                            "education_req": j.education_req,
                            "experience_req": j.experience_req,
                            "required_skills": j.required_skills,
                            "source_platform": j.source_platform,
                        }
                        for j in jobs
                    ],
                }
        except Exception as e:
            logger.warning(f"search_jobs db query failed: {e}")
            return {
                "success": False,
                "status": "failed",
                "error_code": "DB_QUERY_FAILED",
                "error": str(e),
                "total": 0,
                "jobs": [],
            }

        return {
            "success": True,
            "status": "empty",
            "total": 0,
            "jobs": [],
            "message": "岗位库中暂无匹配岗位；如需搜索最新平台职位，请调用 job_live_search_postings，并确保真实浏览器已连接。",
        }

    @classmethod
    def live_search_jobs(
        cls,
        platform: str = "all",
        keyword: str = "后端开发",
        city: str = "全国",
        job_type: str = "social",
        limit: int = 5,
        mode: str = "auto",
        cdp_url: str = "http://127.0.0.1:9223",
        page: int = 1,
    ) -> Dict[str, Any]:
        """直接搜索真实招聘平台，不将结果写入本地岗位库。"""
        from app.services.job_crawler_service import JobCrawlerService
        db: Session = SessionLocal()
        try:
            result = JobCrawlerService(db).live_search_platform_jobs(
                platform=platform,
                keyword=keyword,
                city=city,
                job_type=job_type,
                limit_per_platform=limit,
                mode=mode,
                cdp_url=cdp_url,
                **({"page": page} if page != 1 else {}),
            )
            return {"success": result.get("status") in {"success", "partial_success"}, **result}
        except Exception as exc:
            logger.warning("live_search_jobs error: %s", exc)
            return {"success": False, "error": str(exc), "persisted": False, "jobs": [], "total": 0}
        finally:
            db.close()

    @classmethod
    def match_resume_with_job(cls, resume_text: str, jd_text: str, target_title: str = "开发工程师") -> Dict[str, Any]:
        """深度计算简历与目标岗位 JD 的匹配分、优劣势与短板分析。"""
        try:
            db: Session = SessionLocal()
            resume_service = JobResumeService(db)
            matching_service = JobMatchingService(db)
            parsed_resume = resume_service.parse_resume_text(resume_text)
            parsed_jd = matching_service.parse_jd_text(jd_text, title=target_title)
            db.close()
        except Exception:
            resume_service = JobResumeService(None)  # type: ignore
            matching_service = JobMatchingService(None)  # type: ignore
            parsed_resume = resume_service.parse_resume_text(resume_text)
            parsed_jd = matching_service.parse_jd_text(jd_text, title=target_title)

        try:
            prompt = f"""评估以下候选人与岗位匹配：
候选人：{json.dumps(parsed_resume, ensure_ascii=False)[:2000]}
岗位JD：{json.dumps(parsed_jd, ensure_ascii=False)[:2000]}
请输出 JSON 包含 overall_score(0-100), match_level, matched_skills, missing_skills, strong_points, weak_points, customized_greeting, customized_cover_letter。"""
            response = matching_service.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个人岗匹配评估专家，只输出 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            content = response.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            result = json.loads(content.strip())
        except Exception as exc:
            logger.warning("match_resume_with_job failed: %s", exc)
            return {
                "success": False,
                "status": "failed",
                "error_code": "MATCH_ANALYSIS_FAILED",
                "error": str(exc),
            }

        return {
            "success": True,
            "status": "success",
            "match_report": result
        }

    @classmethod
    def generate_interview_questions(cls, target_role: str, jd_text: str = "", resume_text: str = "", count: int = 3) -> Dict[str, Any]:
        """针对岗位生成高频面试试题集。"""
        try:
            db: Session = SessionLocal()
            service = MockInterviewService(db)
            prompt = f"""针对【{target_role}】岗位生成 {count} 道高质量大厂面试题。
JD: {jd_text[:1000] if jd_text else '标准要求'}
简历: {resume_text[:1000] if resume_text else '标准候选人'}
请以 JSON 格式输出列表：[ {{"question": "", "type": "technical/project_deep_dive/system_design/behavioral", "expected_key_points": [], "model_answer": ""}} ]"""
            response = service.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个面试出题器，严格输出 JSON 数组。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            content = response.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            questions = json.loads(content.strip())
            db.close()
        except Exception as exc:
            logger.warning("generate_interview_questions failed: %s", exc)
            return {
                "success": False,
                "status": "failed",
                "error_code": "INTERVIEW_GENERATION_FAILED",
                "error": str(exc),
            }
        return {
            "success": True,
            "status": "success",
            "questions": questions
        }

    @classmethod
    def generate_greeting_and_cover_letter(cls, candidate_name: str, target_role: str, company: str, core_skills: List[str]) -> Dict[str, Any]:
        """一键生成高情商、高回复率的 HR 打招呼破冰语与定制求职信。"""
        greeting = f"您好！我是{candidate_name}，非常关注{company}发布的【{target_role}】机会。我在【{'、'.join(core_skills[:3]) if core_skills else '后端研发'}】等方向有扎实的实战经验，曾主导过核心模块设计与性能优化，与贵司岗位要求高度契合。期待能与您进一步沟通，随时可发完整简历，谢谢！"
        cover_letter = f"""尊敬的 {company} 招聘团队 / 面试官：

您好！我叫 {candidate_name}，获悉贵司正在招募【{target_role}】，特此呈上求职意向。

在过往的开发实践中，我深入掌握了 {'、'.join(core_skills) if core_skills else '主流技术架构'}，主导或参与过大型工程的高并发优化与架构重构，注重代码质量与系统可用性。我具备快速攻坚和跨团队协作能力，非常认可贵司的业务方向与技术文化。

期待能有机会参与面试，深入交流如何为团队创造价值！

祝工作顺利！
{candidate_name}"""
        return {
            "success": True,
            "greeting": greeting,
            "cover_letter": cover_letter
        }

    @classmethod
    def sync_jobs_from_platforms(
        cls,
        platform: str = "all",
        keyword: str = "后端开发",
        city: str = "全国",
        limit: int = 5,
        mode: str = "auto",
        cdp_url: str = "http://127.0.0.1:9223",
        page: int = 1,
        max_pages: int = 1,
        enrich_details: bool = False,
    ) -> Dict[str, Any]:
        """多招聘平台（BOSS直聘/猎聘/51job/牛客网）真实浏览器 CDP 岗位采集与同步工具。"""
        try:
            from app.services.job_crawler_service import JobCrawlerService
            db: Session = SessionLocal()
            service = JobCrawlerService(db)
            result = service.sync_platform_jobs(
                platform=platform,
                keyword=keyword,
                city=city,
                limit_per_platform=limit,
                mode=mode,
                cdp_url=cdp_url,
                page=page,
                max_pages=max_pages,
                enrich_details=enrich_details,
            )
            db.close()
            return {
                "success": True,
                "stats": result["stats"],
                "synced_jobs": result["jobs"]
            }
        except Exception as e:
            logger.warning(f"sync_jobs_from_platforms error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

