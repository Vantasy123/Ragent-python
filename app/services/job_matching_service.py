"""智能求职 Agent 人岗匹配与岗位检索服务：负责岗位库管理、JD 结构化解析、深度匹配打分与打招呼话术生成。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.domain.models import JobOpportunity, JobMatchAnalysis, ResumeProfile
from app.infrastructure.model_router import ModelRouter

logger = logging.getLogger(__name__)


class JobMatchingService:
    def __init__(self, db: Session, model_router: Optional[ModelRouter] = None):
        self.db = db
        self.model_router = model_router or ModelRouter()

    def get_job_postings(
        self,
        keyword: Optional[str] = None,
        city: Optional[str] = None,
        job_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[JobOpportunity], int]:
        query = self.db.query(JobOpportunity).filter(JobOpportunity.status == "active")
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    JobOpportunity.title.like(pattern),
                    JobOpportunity.company.like(pattern),
                    JobOpportunity.jd_text.like(pattern)
                )
            )
        if city and city != "全部" and city != "全国":
            query = query.filter(JobOpportunity.city.like(f"%{city}%"))
        if job_type and job_type != "all":
            query = query.filter(JobOpportunity.job_type == job_type)
        if source_platform and source_platform != "all":
            query = query.filter(JobOpportunity.source_platform == source_platform)

        total = query.count()
        jobs = query.order_by(desc(JobOpportunity.created_at)).offset(offset).limit(limit).all()
        return jobs, total

    def get_job_by_id(self, job_id: str) -> Optional[JobOpportunity]:
        return self.db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()

    def create_or_import_job(
        self,
        title: str,
        company: str,
        jd_text: str,
        city: str = "北京",
        salary_min: int = 15,
        salary_max: int = 30,
        education_req: str = "本科及以上",
        experience_req: str = "1-3年",
        job_type: str = "social",
        source_platform: str = "nowcoder",
        source_url: str = "",
        company_tags: Optional[List[str]] = None
    ) -> JobOpportunity:
        parsed_jd = self.parse_jd_text(jd_text, title=title)
        job = JobOpportunity(
            title=title or parsed_jd.get("title", "后端工程师"),
            company=company or parsed_jd.get("company", "知名互联网企业"),
            city=city or parsed_jd.get("city", "北京"),
            salary_min=salary_min or parsed_jd.get("salary_min", 15),
            salary_max=salary_max or parsed_jd.get("salary_max", 30),
            education_req=education_req or parsed_jd.get("education_req", "本科及以上"),
            experience_req=experience_req or parsed_jd.get("experience_req", "不限"),
            job_type=job_type,
            source_platform=source_platform,
            source_url=source_url,
            company_tags=company_tags or parsed_jd.get("company_tags", ["互联网", "一线大厂", "双休"]),
            jd_text=jd_text,
            required_skills=parsed_jd.get("required_skills", []),
            preferred_skills=parsed_jd.get("preferred_skills", []),
            responsibilities=parsed_jd.get("responsibilities", []),
            benefits=parsed_jd.get("benefits", [])
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def parse_jd_text(self, jd_text: str, title: str = "") -> Dict[str, Any]:
        """提取岗位 JD 的核心结构（职责、必备技能、加分技能、经验要求、薪资福利）。"""
        if not jd_text or not jd_text.strip():
            return {
                "title": title or "开发工程师",
                "company": "科技公司",
                "city": "全国",
                "salary_min": 15,
                "salary_max": 30,
                "education_req": "本科及以上",
                "experience_req": "1-3年",
                "required_skills": ["Java/Python", "MySQL", "Redis", "微服务架构"],
                "preferred_skills": ["高并发架构经验", "Kubernetes", "大模型落地经验"],
                "responsibilities": ["负责核心业务模块的设计与研发", "保障系统高可用与高性能架构演进"],
                "benefits": ["五险一金", "年终奖", "弹性工作", "免费健身房"],
                "company_tags": ["高成长", "技术氛围浓厚"]
            }

        prompt = f"""你是一个资深技术猎头与招聘专家。请分析以下岗位招聘 JD，提取结构化数据：
JD 文本如下：
{jd_text[:4000]}

请严格以 JSON 格式输出：
{{
  "title": "岗位名称",
  "company": "公司名称（如JD中出现）",
  "city": "工作城市",
  "salary_min": 15,
  "salary_max": 30,
  "education_req": "本科/硕士/大专/不限",
  "experience_req": "应届生/1-3年/3-5年/5年以上/不限",
  "required_skills": ["必备技术栈1", "必备技术栈2"],
  "preferred_skills": ["加分技术项1", "加分技术项2"],
  "responsibilities": ["岗位职责1", "岗位职责2"],
  "benefits": ["福利亮点1", "福利亮点2"],
  "company_tags": ["标签1", "标签2"]
}}
只返回纯 JSON。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个严格输出合法 JSON 的 JD 结构化分析器。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
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
            logger.warning(f"JD 解析模型调用失败，使用默认提取: {e}")
            skills = []
            for kw in ["Java", "Python", "Go", "C++", "Vue", "React", "MySQL", "Redis", "Kafka", "Docker", "K8s", "Spring Boot", "FastAPI", "Milvus", "RAG", "LLM"]:
                if re.search(rf"\b{kw}\b", jd_text, re.IGNORECASE):
                    skills.append(kw)
            return {
                "title": title or "开发工程师",
                "company": "科技公司",
                "city": "北京",
                "salary_min": 15,
                "salary_max": 30,
                "education_req": "本科及以上",
                "experience_req": "1-3年",
                "required_skills": skills[:6] or ["Python/Java", "MySQL", "Redis"],
                "preferred_skills": skills[6:] or ["分布式架构", "高并发实战"],
                "responsibilities": ["参与系统核心业务功能研发与性能调优"],
                "benefits": ["定期体检", "弹性打卡", "节日福利"],
                "company_tags": ["技术驱动", "前沿业务"]
            }

    def analyze_job_match(
        self,
        user_id: str,
        resume_id: str,
        job_id: str
    ) -> JobMatchAnalysis:
        """执行候选人简历与目标岗位 JD 的深度全维度人岗匹配计算。"""
        resume = self.db.query(ResumeProfile).filter(ResumeProfile.id == resume_id).first()
        job = self.db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
        if not resume or not job:
            raise ValueError("Resume or Job Opportunity not found")

        resume_json = json.dumps(resume.parsed_data, ensure_ascii=False, indent=2)
        job_json = json.dumps({
            "title": job.title,
            "company": job.company,
            "city": job.city,
            "education_req": job.education_req,
            "experience_req": job.experience_req,
            "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills,
            "responsibilities": job.responsibilities,
            "jd_text": job.jd_text
        }, ensure_ascii=False, indent=2)

        prompt = f"""你是一个具有大厂招聘委员会水准的 AI 人岗匹配评审专家。
请对候选人简历与目标岗位 JD 进行深度匹配度打分与详细优劣势剖析。

【候选人简历】：
{resume_json[:3500]}

【目标岗位 JD】：
{job_json[:2500]}

请按以下要求进行全维度评估，并严格以 JSON 格式输出：
{{
  "overall_score": 88, // 综合匹配得分 (0-100)
  "skill_match_score": 90, // 技能重合与熟练度得分 (0-100)
  "experience_match_score": 85, // 项目与工作经验匹配得分 (0-100)
  "education_match_score": 90, // 学历与院校背景契合得分 (0-100)
  "match_level": "high", // high / medium / low
  "matched_skills": ["已完全匹配技能1", "已匹配技能2"],
  "missing_skills": ["岗位要求但简历未明确提及的技能1", "缺失技能2"],
  "strong_points": [
    "优势亮点1：具备岗位所需的核心实战经验",
    "优势亮点2：技术栈高度契合"
  ],
  "weak_points": [
    "薄弱环节1：缺少某些特定中间件的深度调优案例",
    "薄弱环节2：项目规模量化描述可进一步增强"
  ],
  "star_project_suggestions": [
    "项目优化建议1：在 XX 项目中突出高并发场景处理",
    "项目优化建议2：补充具体达成的业务量化指标"
  ],
  "customized_greeting": "针对该HR/招聘者的个性化破冰打招呼文案（100字左右，礼貌、专业、突出与本JD核心要求的契合点）",
  "customized_cover_letter": "针对该岗位的定制化求职信（250-400字，结构包含自我介绍、核心优势、与岗位高度契合的事实依据、诚恳的求职态度）"
}}
只返回纯 JSON，不要附加任何 Markdown 格式或额外文本。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个严格输出人岗匹配 JSON 报告的评估引擎。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            res = json.loads(content.strip())
        except Exception as e:
            logger.warning(f"人岗匹配大模型打分失败，执行启发式计算: {e}")
            res = self._heuristic_match(resume, job)

        # 检查或更新数据库中的匹配记录
        analysis = self.db.query(JobMatchAnalysis).filter(
            JobMatchAnalysis.user_id == user_id,
            JobMatchAnalysis.resume_id == resume_id,
            JobMatchAnalysis.job_id == job_id
        ).first()

        if not analysis:
            analysis = JobMatchAnalysis(
                user_id=user_id,
                resume_id=resume_id,
                job_id=job_id
            )
            self.db.add(analysis)

        analysis.overall_score = res.get("overall_score", 80)
        analysis.skill_match_score = res.get("skill_match_score", 80)
        analysis.experience_match_score = res.get("experience_match_score", 80)
        analysis.education_match_score = res.get("education_match_score", 85)
        analysis.match_level = res.get("match_level", "high" if analysis.overall_score >= 80 else ("medium" if analysis.overall_score >= 60 else "low"))
        analysis.matched_skills = res.get("matched_skills", [])
        analysis.missing_skills = res.get("missing_skills", [])
        analysis.strong_points = res.get("strong_points", [])
        analysis.weak_points = res.get("weak_points", [])
        analysis.star_project_suggestions = res.get("star_project_suggestions", [])
        analysis.customized_greeting = res.get("customized_greeting", "")
        analysis.customized_cover_letter = res.get("customized_cover_letter", "")

        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def generate_greeting(self, user_id: str, resume_id: str, job_id: str) -> str:
        """为目标岗位一键生成高回复率的 HR 打招呼破冰语。"""
        analysis = self.analyze_job_match(user_id, resume_id, job_id)
        if analysis.customized_greeting:
            return analysis.customized_greeting

        job = self.get_job_by_id(job_id)
        resume = self.db.query(ResumeProfile).filter(ResumeProfile.id == resume_id).first()
        basic = resume.parsed_data.get("basic_info", {}) if resume else {}
        name = basic.get("name", "求职者")
        title = job.title if job else "贵司岗位"
        company = job.company if job else "贵公司"

        return f"您好！我是{name}，非常关注{company}发布的【{title}】职位。我拥有相关领域的工程落地经验，技术栈与该职位高度契合，曾主导过高并发与性能优化项目。期待能与您进一步沟通，感谢阅读我的简历！"

    def _heuristic_match(self, resume: ResumeProfile, job: JobOpportunity) -> Dict[str, Any]:
        resume_skills = []
        for cat in resume.parsed_data.get("skills", []):
            resume_skills.extend(cat.get("skills", []))
        resume_skills_lower = {s.lower() for s in resume_skills}

        matched = []
        missing = []
        for req in (job.required_skills or []):
            if req.lower() in resume_skills_lower or any(req.lower() in s for s in resume_skills_lower):
                matched.append(req)
            else:
                missing.append(req)

        skill_score = int((len(matched) / max(1, len(matched) + len(missing))) * 100)
        overall = min(95, max(60, int(skill_score * 0.5 + 40)))

        return {
            "overall_score": overall,
            "skill_match_score": skill_score,
            "experience_match_score": 80,
            "education_match_score": 90,
            "match_level": "high" if overall >= 80 else ("medium" if overall >= 60 else "low"),
            "matched_skills": matched or ["核心编程语言", "数据库"],
            "missing_skills": missing or ["特定框架高级特性"],
            "strong_points": [
                f"核心技术栈（如 {', '.join(matched[:3]) if matched else '通用开发能力'}）与岗位要求重合度高",
                "具备扎实的计算机基础与大型项目工程实操背景"
            ],
            "weak_points": [
                f"建议在简历中补充关于 {missing[0] if missing else '特定高并发场景'} 的实战案例"
            ],
            "star_project_suggestions": [
                "针对该岗位要求的关键指标，进一步量化项目中的性能优化数据"
            ],
            "customized_greeting": f"您好！看到贵司正在招聘【{job.title}】，我的技术背景和项目经验与此岗位非常匹配，期待能与您交流！",
            "customized_cover_letter": f"尊敬的 HR / 面试官：您好！我对贵司的【{job.title}】职位非常向往。在过去的项目实战中，我深入掌握了相关技术栈，并有丰富的高质量工程实践经验，希望能为团队贡献力量。"
        }


def ensure_default_job_samples(db: Session) -> None:
    """初始化预置高频大厂校招与社招岗位机会数据。"""
    count = db.query(JobOpportunity).count()
    if count > 0:
        return

    sample_jobs = [
        {
            "title": "后端开发工程师（Go/Java/Python）",
            "company": "字节跳动",
            "city": "北京",
            "salary_min": 25,
            "salary_max": 45,
            "education_req": "本科及以上",
            "experience_req": "1-3年",
            "job_type": "social",
            "source_platform": "nowcoder",
            "source_url": "https://www.nowcoder.com/jobs",
            "company_tags": ["一线大厂", "高薪资", "核心业务", "租房补贴"],
            "jd_text": "【岗位职责】\n1. 负责字节跳动核心业务后台架构设计与研发，支持海量高并发业务场景；\n2. 深入理解业务，主导微服务治理、性能调优与稳定性建设；\n3. 参与 AI Agent 与大模型技术在业务链路中的探索与落地。\n\n【任职要求】\n1. 本科及以上学历，计算机或相关专业；\n2. 熟练掌握 Go/Java/Python/C++ 至少一种编程语言，深入理解数据结构、网络与操作系统；\n3. 熟练掌握 MySQL、Redis、Kafka 等主流中间件，具备高并发高可用系统实战经验；\n4. 具备良好的工程素养、Code Review 意识与排障能力。",
            "required_skills": ["Go/Java/Python", "MySQL", "Redis", "Kafka", "高并发架构", "微服务"],
            "preferred_skills": ["分布式事务", "Kubernetes", "大模型/Agent 实战"],
            "responsibilities": ["负责核心服务端业务架构与高并发研发", "推进微服务治理与性能调优", "保障线上服务 99.99% 高可用"],
            "benefits": ["免费三餐", "每月租房补贴", "全额六险一金", "年度体检", "无限零食饮料"]
        },
        {
            "title": "Java 核心研发工程师（校招/实习）",
            "company": "阿里巴巴",
            "city": "杭州",
            "salary_min": 20,
            "salary_max": 35,
            "education_req": "本科及以上",
            "experience_req": "应届生",
            "job_type": "campus",
            "source_platform": "nowcoder",
            "source_url": "https://www.nowcoder.com/jobs",
            "company_tags": ["电商中台", "技术底蕴", "导师带教", "大厂平台"],
            "jd_text": "【岗位职责】\n1. 参与阿里电商交易与履约中台核心研发；\n2. 负责分布式服务框架、高并发缓存体系与数据一致性设计；\n3. 编写高质量单元测试与自动化测试脚本。\n\n【任职要求】\n1. 2026/2027 届高校毕业生，计算机、软件或相关专业；\n2. 熟练掌握 Java 基础（JVM 内存模型、垃圾回收、多线程并发）；\n3. 熟练使用 Spring Boot / Spring Cloud 框架生态，掌握 MySQL 索引原理与调优；\n4. 积极自驱，具备良好的算法与逻辑思维。",
            "required_skills": ["Java", "JVM", "Spring Boot", "MySQL", "Redis", "并发编程"],
            "preferred_skills": ["Dubbo", "RocketMQ", "ACM/ICPC 竞赛获奖"],
            "responsibilities": ["参与电商交易中台分布式系统开发", "参与高可用与容灾方案设计"],
            "benefits": ["十三薪+年终奖", "交通补贴", "导师1对1指导", "免费健身房"]
        },
        {
            "title": "AI Agent / 算法应用工程师",
            "company": "腾讯科技",
            "city": "深圳",
            "salary_min": 28,
            "salary_max": 50,
            "education_req": "硕士及以上",
            "experience_req": "1-3年",
            "job_type": "social",
            "source_platform": "boss",
            "source_url": "https://www.zhipin.com",
            "company_tags": ["AI前沿", "大模型应用", "平台级流量", "股票期权"],
            "jd_text": "【岗位职责】\n1. 负责基于 LLM 的 Agent 协同系统、RAG 向量检索与智能工具编排；\n2. 优化模型 Prompt、知识库召回准确率与多轮对话链路；\n3. 落地企业级智能问答、运维与求职助理产品。\n\n【任职要求】\n1. 计算机或人工智能相关专业硕士及以上；\n2. 精通 Python，熟练掌握 FastAPI、LangChain、LlamaIndex 等 Agent 框架；\n3. 熟悉 Milvus/Chroma 向量检索与 ReAct / Plan-Execute 智能体架构；\n4. 有大模型应用落地经验或知名开源项目贡献者优先。",
            "required_skills": ["Python", "LLM", "RAG", "Agent 架构", "Milvus", "Prompt 工程"],
            "preferred_skills": ["LangGraph", "Fine-tuning", "大模型安全对齐"],
            "responsibilities": ["负责智能 Agent 编排系统研发与 RAG 链路调优", "构建大模型评估基准与自动化门禁"],
            "benefits": ["优质食堂", "企鹅安居计划", "全额公积金", "商业医疗险"]
        },
        {
            "title": "前端开发工程师（Vue3/React/TypeScript）",
            "company": "美团",
            "city": "北京",
            "salary_min": 18,
            "salary_max": 32,
            "education_req": "本科及以上",
            "experience_req": "1-3年",
            "job_type": "social",
            "source_platform": "liepin",
            "source_url": "https://www.liepin.com",
            "company_tags": ["业务稳健", "大前端", "工程化体系", "弹性工作"],
            "jd_text": "【岗位职责】\n1. 负责美团到店与外卖运营后台、移动端及协同系统前端开发；\n2. 打造高性能、组件化、响应式的 Web 用户界面；\n3. 参与前端工程化、构建优化与监控告警体系建设。\n\n【任职要求】\n1. 熟练掌握 Vue3 / React、TypeScript、Tailwind CSS 及现代前端工具链；\n2. 深入理解浏览器渲染机制、跨端通信与前端性能优化；\n3. 具备良好的交互设计敏锐度与组件抽象能力。",
            "required_skills": ["Vue3", "TypeScript", "Tailwind CSS", "Vite", "前端性能优化"],
            "preferred_skills": ["微前端", "Node.js", "可视化图表 (ECharts)"],
            "responsibilities": ["负责企业级后台与用户交互界面研发", "推进前端工程化与组件库建设"],
            "benefits": ["餐补", "年度体检", "打车报销", "带薪年假"]
        }
    ]

    for item in sample_jobs:
        job = JobOpportunity(
            title=item["title"],
            company=item["company"],
            city=item["city"],
            salary_min=item["salary_min"],
            salary_max=item["salary_max"],
            education_req=item["education_req"],
            experience_req=item["experience_req"],
            job_type=item["job_type"],
            source_platform=item["source_platform"],
            source_url=item["source_url"],
            company_tags=item["company_tags"],
            jd_text=item["jd_text"],
            required_skills=item["required_skills"],
            preferred_skills=item["preferred_skills"],
            responsibilities=item["responsibilities"],
            benefits=item["benefits"],
            status="active"
        )
        db.add(job)
    db.commit()
    logger.info("已成功初始化预置大厂求职岗位数据。")

