"""智能求职 Agent AI 模拟面试服务：支持多角色面试官设定、动态出题、多轮交互评估与综合复盘报告。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.domain.models import (
    JobOpportunity,
    MockInterviewRecord,
    MockInterviewSession,
    ResumeProfile
)
from app.infrastructure.model_router import ModelRouter

logger = logging.getLogger(__name__)


class MockInterviewService:
    def __init__(self, db: Session, model_router: Optional[ModelRouter] = None):
        self.db = db
        self.model_router = model_router or ModelRouter()

    def get_sessions_by_user(self, user_id: str) -> List[MockInterviewSession]:
        return self.db.query(MockInterviewSession).filter(
            MockInterviewSession.user_id == user_id
        ).order_by(desc(MockInterviewSession.created_at)).all()

    def get_session_by_id(self, session_id: str, user_id: Optional[str] = None) -> Optional[MockInterviewSession]:
        query = self.db.query(MockInterviewSession).filter(MockInterviewSession.id == session_id)
        if user_id:
            query = query.filter(MockInterviewSession.user_id == user_id)
        return query.first()

    def create_interview_session(
        self,
        user_id: str,
        target_role: str = "后端开发工程师",
        role_type: str = "tech_expert",
        difficulty: str = "intermediate",
        resume_id: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> MockInterviewSession:
        if resume_id:
            resume = self.db.query(ResumeProfile).filter(
                ResumeProfile.id == resume_id,
                ResumeProfile.user_id == user_id,
            ).first()
            if not resume:
                raise ValueError("简历不存在或无权访问")
        if job_id:
            job = self.db.query(JobOpportunity).filter(JobOpportunity.id == job_id).first()
            if not job or job.status != "active":
                raise ValueError("目标岗位不存在或已关闭")

        session = MockInterviewSession(
            user_id=user_id,
            resume_id=resume_id,
            job_id=job_id,
            target_role=target_role,
            role_type=role_type,
            difficulty=difficulty,
            status="in_progress",
            detailed_dimensions={
                "technical_depth": 0,
                "logic_structure": 0,
                "communication": 0,
                "star_framework": 0,
                "culture_fit": 0
            }
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        # 立即生成第一道面试题
        first_q = self.generate_next_question(session.id, round_number=1)
        return session

    def generate_next_question(
        self,
        session_id: str,
        round_number: Optional[int] = None,
        question_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> MockInterviewRecord:
        """根据当前面试会话进度、目标岗位和简历生成下一轮面试题。"""
        session = self.get_session_by_id(session_id, user_id=user_id)
        if not session:
            raise ValueError("面试会话不存在或无权访问")
        if session.status != "in_progress":
            raise ValueError("当前面试会话已结束，不能继续出题")
        if round_number is not None and round_number < 1:
            raise ValueError("轮次必须从 1 开始")

        current_records = self.db.query(MockInterviewRecord).filter(
            MockInterviewRecord.session_id == session_id
        ).order_by(MockInterviewRecord.round_number).all()

        if round_number is None:
            round_number = len(current_records) + 1
        if any(record.round_number == round_number for record in current_records):
            raise ValueError(f"第 {round_number} 轮问题已存在")

        resume = self.db.query(ResumeProfile).filter(ResumeProfile.id == session.resume_id).first() if session.resume_id else None
        job = self.db.query(JobOpportunity).filter(JobOpportunity.id == session.job_id).first() if session.job_id else None

        role_desc = {
            "tech_expert": "大厂资深技术专家，重点考察底层原理、高并发、性能调优和代码设计",
            "hr": "资深 HRBP，重点考察沟通表达、职业规划、团队协作与文化契合度（BQ）",
            "tech_director": "技术总监/架构师，重点考察系统架构设计、技术选型决策与复杂业务攻坚",
            "peer": "业务核心研发同事，考察实际工程细节、协作与解决问题的敏捷度"
        }.get(session.role_type, "资深技术面试官")

        history_summary = []
        for r in current_records:
            history_summary.append(f"第{r.round_number}轮 [{r.question_type}]: 提问={r.question} | 用户回答得分={r.score}")

        q_types_sequence = ["technical", "project_deep_dive", "system_design", "behavioral", "hr"]
        inferred_type = question_type or q_types_sequence[(round_number - 1) % len(q_types_sequence)]

        prompt = f"""你现在扮演一位【{role_desc}】。
正在对候选人进行针对【{session.target_role}】职位的第 {round_number} 轮深度模拟面试。
难度级别：{session.difficulty}。
本轮考察方向：{inferred_type}。

【候选人简历信息】：
{json.dumps(resume.parsed_data, ensure_ascii=False)[:2000] if resume else "候选人具备中高级工程实战经验"}

【目标岗位 JD 信息】：
{job.jd_text[:1500] if job else "要求扎实的计算机功底与大型系统设计经验"}

【往轮面试记录】：
{chr(10).join(history_summary) if history_summary else "这是第一轮提问"}

请生成一道高质量、具有大厂深度与区分度的面试问题，并给出该题期望的得分要点。
请严格以 JSON 格式输出：
{{
  "question_type": "{inferred_type}",
  "question": "面试官提问内容（语气专业、沉浸感强，可结合候选人简历项目或目标JD展开追问）",
  "expected_key_points": [
    "采分要点1",
    "采分要点2",
    "采分要点3"
  ],
  "model_answer": "大厂标准满分示范回答（包含核心原理、逻辑结构与实战案例）"
}}
只返回纯 JSON。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个沉浸式大厂面试官出题器，严格输出合法 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                model=settings.INTERVIEW_MODEL,
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
            logger.warning(f"面试出题失败，使用内置高频真题: {e}")
            res = self._fallback_question(round_number, inferred_type, session.target_role)

        record = MockInterviewRecord(
            session_id=session_id,
            round_number=round_number,
            question_type=res.get("question_type", inferred_type),
            question=res.get("question", "请结合你做过的最复杂的一个项目，谈谈你遇到了哪些技术难点以及如何解决的？"),
            expected_key_points=res.get("expected_key_points", ["项目背景与业务挑战", "技术选型与难点攻坚", "量化成果与复盘"]),
            model_answer=res.get("model_answer", "回答需符合 STAR 法则，突出问题定位方法与底层技术原理。")
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def evaluate_answer(
        self,
        record_id: str,
        user_answer: str,
        user_id: Optional[str] = None,
    ) -> MockInterviewRecord:
        """评估候选人的单轮面试回答，给出 0-100 打分、采分点覆盖分析与优化建议。"""
        if not user_answer or not user_answer.strip():
            raise ValueError("回答内容不能为空")
        record = self.db.query(MockInterviewRecord).filter(MockInterviewRecord.id == record_id).first()
        if not record:
            raise ValueError("面试题不存在或无权访问")
        session = self.get_session_by_id(record.session_id, user_id=user_id)
        if not session:
            raise ValueError("面试题不存在或无权访问")
        if session.status != "in_progress":
            raise ValueError("当前面试会话已结束，不能提交回答")

        prompt = f"""你是一位极具权威的大厂面试官。请对候选人针对以下面试题的回答进行严格而专业的评估打分。

【面试题目】：{record.question}
【题目类型】：{record.question_type}
【期望得分关键要点】：{json.dumps(record.expected_key_points, ensure_ascii=False)}
【参考满分示范】：{record.model_answer}

【候选人现场回答】：
{user_answer}

请严格按以下 JSON 格式输出评估结果：
{{
  "score": 85, // 0-100 打分
  "feedback": "整体评价（针对候选人回答的完整度、逻辑性、技术深度的综合点评，2-3句）",
  "improvement_tips": [
    "提升建议1：指出缺少了哪一部分关键原理解析",
    "提升建议2：建议按照 STAR 或 总-分-总 结构展开"
  ],
  "model_answer": "{record.model_answer or '标准参考回答'}"
}}
只返回纯 JSON。"""

        try:
            response = self.model_router.chat(
                messages=[
                    {"role": "system", "content": "你是一个严格、客观的面试评测与打分引擎，只输出 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                model=settings.INTERVIEW_MODEL,
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
            logger.warning(f"回答评估模型失败，降级为规则打分: {e}")
            length = len(user_answer.strip())
            score = min(90, max(50, 60 + length // 20))
            res = {
                "score": score,
                "feedback": "回答基本切中主题，逻辑较清晰，但在底层深度和量化指标上仍有提升空间。",
                "improvement_tips": ["可进一步阐述底层实现机制与设计权衡", "结合具体的生产环境故障或性能瓶颈举例"],
                "model_answer": record.model_answer
            }

        raw_score = res.get("score")
        try:
            val = int(raw_score) if raw_score is not None else 0
        except Exception:
            val = 0
        if val <= 0 and user_answer.strip():
            val = min(90, max(60, 65 + len(user_answer.strip()) // 10))
        record.score = val
        record.feedback = res.get("feedback", "回答良好。")
        record.improvement_tips = res.get("improvement_tips", ["建议加强底层原理解析", "结合量化收益说明"])
        if res.get("model_answer"):
            record.model_answer = res.get("model_answer")

        self.db.commit()
        self.db.refresh(record)
        return record

    def finish_session_and_generate_report(self, session_id: str, user_id: Optional[str] = None) -> MockInterviewSession:
        """结束面试会话，汇总全轮问答并生成五维能力雷达图与综合复盘报告。"""
        session = self.get_session_by_id(session_id, user_id=user_id)
        if not session:
            raise ValueError("面试会话不存在或无权访问")
        if session.status == "completed":
            return session

        records = self.db.query(MockInterviewRecord).filter(
            MockInterviewRecord.session_id == session_id
        ).order_by(MockInterviewRecord.round_number).all()

        if not records:
            session.status = "completed"
            session.overall_score = 0
            session.feedback_summary = "本次面试未记录到有效问答。"
            self.db.commit()
            return session

        avg_score = int(sum(r.score for r in records) / len(records)) if records else 0

        # 计算五维能力
        tech_scores = [r.score for r in records if r.question_type in ["technical", "system_design"]]
        project_scores = [r.score for r in records if r.question_type == "project_deep_dive"]
        bq_scores = [r.score for r in records if r.question_type in ["behavioral", "hr"]]

        technical_depth = int(sum(tech_scores) / len(tech_scores)) if tech_scores else avg_score
        star_framework = int(sum(project_scores) / len(project_scores)) if project_scores else avg_score
        communication = int(sum(bq_scores) / len(bq_scores)) if bq_scores else avg_score
        logic_structure = min(100, int((technical_depth + communication) / 2 + 5))
        culture_fit = min(100, int((communication + star_framework) / 2))

        session.detailed_dimensions = {
            "technical_depth": technical_depth,
            "logic_structure": logic_structure,
            "communication": communication,
            "star_framework": star_framework,
            "culture_fit": culture_fit
        }
        session.overall_score = avg_score
        session.status = "completed"

        session.feedback_summary = f"本次模拟面试共完成 {len(records)} 轮专业考核，综合评估得分 {avg_score} 分。候选人在技术深度（{technical_depth}分）与逻辑结构（{logic_structure}分）表现稳健，建议在针对高并发边界条件与具体量化成果的展开上进一步强化。"

        self.db.commit()
        self.db.refresh(session)
        return session

    def _fallback_question(self, round_num: int, q_type: str, target_role: str) -> Dict[str, Any]:
        questions_pool = {
            "technical": {
                "question": f"在【{target_role}】日常研发中，请深入谈谈 MySQL InnoDB 引擎的索引底层结构（B+树与B树区别）、聚簇索引与二级索引回表，以及在高并发场景下如何做慢 SQL 优化？",
                "expected_key_points": ["B+树叶子节点链表与层高优势", "回表与覆盖索引优化", "Explain 执行计划关键指标", "索引下推与最左匹配原则"],
                "model_answer": "InnoDB 使用 B+树作为索引结构，非叶子节点仅存键值，叶子节点双向链表相连支持高效范围查询。慢 SQL 优化通常基于 Explain 分析 type 与 Extra，通过覆盖索引、组合索引最左前缀或拆分查询解决。"
            },
            "project_deep_dive": {
                "question": "请选择你简历中最具技术挑战的一个项目，用 STAR 法则展开说明：你遇到了什么技术瓶颈？采取了哪些架构演进方案？最终达成了怎样的量化业务收益？",
                "expected_key_points": ["清晰的情境与技术指标挑战", "多方案权衡对比与选型依据", "具体的攻坚步骤与落地细节", "量化的业务收益（如 QPS/延时/故障率）"],
                "model_answer": "采用 STAR 框架结构化表达，突出在分布式高并发、缓存穿透/雪崩预防、异步解耦中的技术选型与压测对比，最终将 QPS 提升 3 倍并降低 60% P99 延时。"
            },
            "system_design": {
                "question": "如果要你设计一个支持每秒 10 万级并发的秒杀系统，你会从网络接入、缓存架构、数据库削峰、超卖控制和一致性保障等几个层面如何整体设计？",
                "expected_key_points": ["CDN与限流网关层拦截", "Redis 分布式预扣库存与 Lua 脚本原子性", "MQ 异步落库削峰", "数据库乐观锁与防超卖兜底"],
                "model_answer": "分层过滤架构：动静分离+CDN分发；网关令牌桶限流；Redis+Lua 原子扣减与排队；RocketMQ/Kafka 异步落库；数据库乐观锁防超卖与对账兜底。"
            },
            "behavioral": {
                "question": "在过去的项目交付中，当遇到产品需求紧急变更且上线时间不可延期，同时技术方案存在较大风险时，你是如何沟通协调并最终推进落地的？",
                "expected_key_points": ["敏锐的风险识别与量化沟通", "MVP 核心链路快速交付策略", "跨部门协同与向上管理能力"],
                "model_answer": "及时拉齐各方利益相关人，量化技术风险与潜在资损；提议分阶段上线并砍掉非核心功能，优先保障主链路高可用，上线后安排灰度放量与完备监控。"
            },
            "hr": {
                "question": "请谈谈你未来 3-5 年的职业发展规划？你为什么选择我们公司，以及你认为自己最大的竞争优势是什么？",
                "expected_key_points": ["清晰扎实的技术深耕路径", "对目标公司业务方向的认同与调研", "独特的项目经验与自驱力展示"],
                "model_answer": "明确走技术专家路线，持续精进分布式与 AI Agent 架构；对贵司业务场景有深度认同，能够快速将前沿技术落地并沉淀为业务生产力。"
            }
        }
        return questions_pool.get(q_type, questions_pool["technical"])
