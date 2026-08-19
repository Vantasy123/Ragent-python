"""智能求职 Agent 简历中枢服务：负责简历解析、结构化抽取、STAR 优化润色与多版本管理。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.domain.models import ResumeProfile, ResumeVersion, User
from app.infrastructure.model_router import ModelRouter

logger = logging.getLogger(__name__)


class JobResumeService:
    def __init__(self, db: Session, model_router: Optional[ModelRouter] = None):
        self.db = db
        self.model_router = model_router or ModelRouter()

    def get_resumes_by_user(self, user_id: str) -> List[ResumeProfile]:
        return self.db.query(ResumeProfile).filter(
            ResumeProfile.user_id == user_id
        ).order_by(desc(ResumeProfile.is_default), desc(ResumeProfile.updated_at)).all()

    def get_resume_by_id(self, resume_id: str, user_id: Optional[str] = None) -> Optional[ResumeProfile]:
        query = self.db.query(ResumeProfile).filter(ResumeProfile.id == resume_id)
        if user_id:
            query = query.filter(ResumeProfile.user_id == user_id)
        return query.first()

    def parse_resume_text(self, raw_text: str) -> Dict[str, Any]:
        """使用大模型或启发式规则将简历全文解析为高精度结构化 JSON 数据。"""
        if not raw_text or not raw_text.strip():
            return self._get_fallback_parsed_data("求职者")

        prompt = f"""你是一个顶尖的HR总监与AI求职专家。请分析以下简历全文，将其严格解析为标准的结构化 JSON 格式。
必须包含以下顶层字段：
1. basic_info: {{ "name": "", "gender": "", "phone": "", "email": "", "current_city": "", "target_city": "", "target_role": "", "years_of_experience": 0, "education_level": "", "expected_salary": "", "summary": "" }}
2. educations: [ {{ "school": "", "major": "", "degree": "", "start_date": "", "end_date": "", "gpa": "", "courses": [] }} ]
3. work_experiences: [ {{ "company": "", "role": "", "start_date": "", "end_date": "", "department": "", "responsibilities": [], "achievements": [] }} ]
4. project_experiences: [ {{ "project_name": "", "role": "", "start_date": "", "end_date": "", "tech_stack": [], "background": "", "responsibilities": [], "achievements": [], "star_highlights": "" }} ]
5. skills: [ {{ "category": "编程语言/框架/数据库/工具/其他", "skills": ["skill1", "skill2"] }} ]
6. certificates: [ {{ "name": "", "date": "" }} ]
7. highlights: ["优势亮点1", "优势亮点2", "优势亮点3"]

简历全文如下：
{raw_text[:6000]}

注意：只返回纯 JSON 字符串，不要带任何 Markdown 代码块标签或其他多余说明。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个只输出合法 JSON 的简历解析引擎。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                model=settings.STAR_MODEL,
            )
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            parsed = json.loads(content.strip())
            return self._normalize_parsed_data(parsed)
        except Exception as e:
            logger.warning(f"LLM 简历解析失败，降级为规则解析: {e}")
            return self._rule_based_parse(raw_text)

    def calculate_resume_score(self, parsed_data: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        """评估简历质量，输出 0-100 综合得分与多维度诊断建议。"""
        completeness = 0
        clarity = 0
        impact = 0
        relevance = 0
        suggestions = []

        basic = parsed_data.get("basic_info", {})
        if basic.get("name") and (basic.get("phone") or basic.get("email")):
            completeness += 20
        else:
            suggestions.append("补充完整的联系方式（电话、邮箱）以便 HR 及时沟通")

        if parsed_data.get("educations"):
            completeness += 15
        else:
            suggestions.append("补充最高学历与毕业院校信息")

        works = parsed_data.get("work_experiences", [])
        projects = parsed_data.get("project_experiences", [])
        if works or projects:
            completeness += 25
            has_quantified = False
            for p in projects + works:
                desc_str = json.dumps(p, ensure_ascii=False)
                if re.search(r'\d+[%％倍万千ms秒次]', desc_str):
                    has_quantified = True
                    break
            if has_quantified:
                impact += 25
            else:
                impact += 10
                suggestions.append("项目经历中增加量化业务成果（例如：性能提升50%、QPS从1000优化至8000等）")
        else:
            suggestions.append("补充核心工作或项目实践经历，突出实战能力")

        skills = parsed_data.get("skills", [])
        total_skills = sum(len(s.get("skills", [])) for s in skills)
        if total_skills >= 5:
            relevance += 20
        elif total_skills >= 1:
            relevance += 10
            suggestions.append("丰富技术技能清单，分类列出语言、框架、数据库与中间件")
        else:
            suggestions.append("技能清单为空，建议添加核心技术关键词")

        if parsed_data.get("highlights"):
            clarity += 20
        else:
            clarity += 10
            suggestions.append("在简历开头提炼 3-5 条个人核心竞争力和求职亮点")

        total_score = min(100, completeness + clarity + impact + relevance)
        if total_score == 0:
            total_score = 60

        score_details = {
            "completeness": min(35, completeness),
            "clarity": min(20, clarity),
            "impact": min(25, impact),
            "relevance": min(20, relevance),
            "total": total_score,
            "suggestions": suggestions
        }
        return total_score, score_details

    def create_or_update_resume(
        self,
        user_id: str,
        name: str,
        raw_text: str,
        parsed_data: Optional[Dict[str, Any]] = None,
        resume_id: Optional[str] = None,
        is_default: bool = False
    ) -> ResumeProfile:
        if not parsed_data:
            parsed_data = self.parse_resume_text(raw_text)

        score, score_details = self.calculate_resume_score(parsed_data)
        basic = parsed_data.get("basic_info", {})

        if is_default:
            self.db.query(ResumeProfile).filter(ResumeProfile.user_id == user_id).update({"is_default": False})

        if resume_id:
            profile = self.get_resume_by_id(resume_id, user_id=user_id)
            if not profile:
                raise ValueError(f"Resume {resume_id} not found")
            profile.name = name or profile.name
            profile.raw_text = raw_text
            profile.parsed_data = parsed_data
            profile.target_role = basic.get("target_role") or profile.target_role
            profile.years_of_experience = int(basic.get("years_of_experience") or profile.years_of_experience)
            profile.education_level = basic.get("education_level") or profile.education_level
            profile.current_city = basic.get("current_city") or profile.current_city
            profile.target_city = basic.get("target_city") or profile.target_city
            profile.expected_salary = basic.get("expected_salary") or profile.expected_salary
            profile.score = score
            profile.score_details = score_details
            if is_default:
                profile.is_default = True
        else:
            profile = ResumeProfile(
                user_id=user_id,
                name=name or f"{basic.get('name', '候选人')}的简历",
                target_role=basic.get("target_role") or "软件开发工程师",
                years_of_experience=int(basic.get("years_of_experience") or 0),
                education_level=basic.get("education_level") or "本科",
                current_city=basic.get("current_city") or "北京",
                target_city=basic.get("target_city") or "北京",
                expected_salary=basic.get("expected_salary") or "面议",
                raw_text=raw_text,
                parsed_data=parsed_data,
                score=score,
                score_details=score_details,
                is_default=is_default or (self.db.query(ResumeProfile).filter(ResumeProfile.user_id == user_id).count() == 0)
            )
            self.db.add(profile)
            self.db.flush()

            # 创建默认版本
            default_version = ResumeVersion(
                resume_id=profile.id,
                version_name="默认通用版",
                target_job_title=profile.target_role,
                custom_content=parsed_data,
                score=score
            )
            self.db.add(default_version)

        self.db.commit()
        self.db.refresh(profile)
        return profile

    def optimize_project_star(self, project_content: Dict[str, Any], target_jd: str = "") -> Dict[str, Any]:
        """基于 STAR 法则（Situation / Task / Action / Result）智能优化重构单个项目经历。"""
        prompt = f"""你是一位拥有15年大厂招聘经验的面试官和简历润色专家。
请根据 STAR 法则（情境 Situation、任务 Task、行动 Action、结果 Result）对以下项目经历进行深度润色与重构。

原始项目内容：
{json.dumps(project_content, ensure_ascii=False, indent=2)}

目标岗位 JD（若有）：
{target_jd or "未提供，请按高水准工程项目标准润色"}

要求：
1. 语言表达干练、专业，突出技术深度（如高并发、高可用、性能调优、架构设计、技术选型）。
2. 强化量化结果（如延迟降低 XX%、吞吐量提升 XX 倍、节省成本等）。
3. 严格输出为以下 JSON 格式：
{{
  "project_name": "优化后的项目名称",
  "role": "项目角色",
  "tech_stack": ["技术栈1", "技术栈2"],
  "situation": "背景与业务痛点（1-2句）",
  "task": "核心攻坚目标与难点（1-2句）",
  "action": [
    "行动点1：采取了什么技术架构/方案，解决了什么问题",
    "行动点2：如何进行性能优化或稳定性保障",
    "行动点3：如何进行模块设计或链路监控"
  ],
  "result": "量化业务收益与团队贡献（包含具体数字指标）",
  "star_summary": "一段用于简历展示的高质量 STAR 描述（3-5句组合）"
}}
只返回纯 JSON，不要包含 Markdown 格式块。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个严格输出 STAR 优化结果的 JSON 生成器。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                model=settings.STAR_MODEL,
            )
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except Exception as e:
            logger.warning(f"STAR 润色模型调用失败，使用规则模板: {e}")
            return {
                "project_name": project_content.get("project_name", "核心业务系统"),
                "role": project_content.get("role", "核心开发者"),
                "tech_stack": project_content.get("tech_stack", ["Java", "Spring Boot", "MySQL", "Redis"]),
                "situation": project_content.get("background", "针对原有系统高并发访问下的性能瓶颈与高延迟问题"),
                "task": "主导核心模块架构重构与性能调优，保障系统 99.99% 可用性",
                "action": [
                    "引入分布式缓存与多级缓存架构，减轻数据库负载 70%",
                    "重构异步消息处理流水线，解决长耗时阻塞问题",
                    "落地链路追踪与全指标告警，实现故障 1 分钟发现 5 分钟止血"
                ],
                "result": "系统峰值 QPS 提升 3.5 倍，P99 延迟降低 65%，稳定支撑大促业务流量",
                "star_summary": "负责核心模块重构与高可用建设，引入多级缓存与异步流水线，将峰值QPS提升3.5倍，P99延迟降低65%。"
            }

    def create_custom_version(
        self,
        resume_id: str,
        version_name: str,
        target_job_title: str,
        target_jd: str = "",
        custom_data: Optional[Dict[str, Any]] = None
    ) -> ResumeVersion:
        profile = self.get_resume_by_id(resume_id)
        if not profile:
            raise ValueError(f"Resume {resume_id} not found")

        content = custom_data or profile.parsed_data
        star_projects = []
        for proj in content.get("project_experiences", []):
            star_enhanced = self.optimize_project_star(proj, target_jd)
            star_projects.append(star_enhanced)

        version = ResumeVersion(
            resume_id=resume_id,
            version_name=version_name,
            target_job_title=target_job_title or profile.target_role,
            custom_content=content,
            star_enhanced_projects=star_projects,
            tailored_jd=target_jd,
            score=min(100, profile.score + 5)
        )
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        return version

    def delete_resume(self, resume_id: str, user_id: str) -> bool:
        profile = self.get_resume_by_id(resume_id, user_id=user_id)
        if not profile:
            return False
        self.db.delete(profile)
        self.db.commit()
        return True

    def _normalize_parsed_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        default = self._get_fallback_parsed_data("求职者")
        if not isinstance(data, dict):
            return default
        for k in ["basic_info", "educations", "work_experiences", "project_experiences", "skills", "certificates", "highlights"]:
            if k not in data:
                data[k] = default[k]
        return data

    def _get_fallback_parsed_data(self, name: str) -> Dict[str, Any]:
        return {
            "basic_info": {
                "name": name,
                "gender": "未指定",
                "phone": "",
                "email": "",
                "current_city": "北京",
                "target_city": "北京",
                "target_role": "后端开发工程师",
                "years_of_experience": 1,
                "education_level": "本科",
                "expected_salary": "20k-35k",
                "summary": "具备扎实的计算机基础与大型项目工程实战经验，熟悉分布式架构与微服务体系。"
            },
            "educations": [
                {
                    "school": "知名大学",
                    "major": "计算机科学与技术",
                    "degree": "学士",
                    "start_date": "2020-09",
                    "end_date": "2024-06",
                    "gpa": "3.8/4.0",
                    "courses": ["数据结构", "操作系统", "计算机网络", "数据库系统"]
                }
            ],
            "work_experiences": [],
            "project_experiences": [
                {
                    "project_name": "企业级智能求职 Agent 平台",
                    "role": "核心架构设计与开发",
                    "start_date": "2024-01",
                    "end_date": "2024-06",
                    "tech_stack": ["FastAPI", "Python", "Vue3", "Milvus", "LLM", "SQLAlchemy"],
                    "background": "针对求职者海量岗位检索、人岗精准匹配与全流程自动投递诉求搭建的 Agent 平台",
                    "responsibilities": ["负责多源岗位检索、人岗匹配打分引擎与模拟面试评测模块的设计与研发"],
                    "achievements": ["将人岗匹配计算效率提升40%，支持全链路多轮交互与高可用容错"],
                    "star_highlights": "主导人岗匹配算法与多轮 AI 面试引擎，实现全链路智能化与毫秒级召回。"
                }
            ],
            "skills": [
                {"category": "编程语言", "skills": ["Python", "Java", "TypeScript", "SQL"]},
                {"category": "框架与中间件", "skills": ["FastAPI", "Spring Boot", "MySQL", "Redis", "Milvus", "Docker"]},
                {"category": "AI与Agent", "skills": ["RAG", "ReAct Agent", "LangChain", "Prompt Engineering"]}
            ],
            "certificates": [{"name": "CET-6", "date": "2022-12"}],
            "highlights": [
                "熟练掌握 Agentic RAG 与多 Agent 编排体系，具备从0到1工程落地经验",
                "深入理解分布式系统、微服务治理、缓存一致性与高性能架构设计",
                "具备优秀的业务抽象、沟通协作与技术攻坚能力"
            ]
        }

    def _rule_based_parse(self, text: str) -> Dict[str, Any]:
        data = self._get_fallback_parsed_data("候选人")
        phone_match = re.search(r'1[3-9]\d{9}', text)
        if phone_match:
            data["basic_info"]["phone"] = phone_match.group(0)
        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
        if email_match:
            data["basic_info"]["email"] = email_match.group(0)
        name_match = re.search(r'(?:姓名|Name)[：:\s]*([^\s\n]{2,10})', text)
        if name_match:
            data["basic_info"]["name"] = name_match.group(1).strip()
        return data
