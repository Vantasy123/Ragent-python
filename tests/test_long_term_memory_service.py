from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services.long_term_memory_service import LongTermMemoryService


class LongTermMemoryServiceTest(unittest.TestCase):
    """验证长期记忆抽取、去重和检索。"""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.sessions = []

    def tearDown(self) -> None:
        for session in self.sessions:
            session.close()
        self.engine.dispose()

    def _db(self):
        """创建测试数据库会话，并保证 tearDown 先关闭会话再释放 engine。"""

        session = self.Session()
        self.sessions.append(session)
        return session

    def test_remember_from_user_message_extracts_preference(self) -> None:
        db = self._db()

        service = LongTermMemoryService(db)
        rows = service.remember_from_user_message(
            user_id="u1",
            conversation_id="c1",
            message_id="m1",
            content="我喜欢回答时先给结论，再给代码路径",
        )

        self.assertEqual(len(rows), 1)
        self.assertIn("用户偏好", rows[0].content)
        self.assertIn("先给结论", rows[0].content)

    def test_memory_retrieve_and_prompt_block(self) -> None:
        db = self._db()

        service = LongTermMemoryService(db)
        service.remember_from_user_message("u1", "c1", "m1", "请记住：我希望所有回答都使用中文")
        service.remember_from_user_message("u1", "c1", "m2", "我喜欢先解释真实调用链")

        rows = service.retrieve("u1", "这次也请按真实调用链解释", limit=2)
        block = service.build_prompt_block("u1", "中文回答并解释调用链")

        self.assertTrue(rows)
        self.assertIn("用户", block)
        self.assertIn("调用链", block)

    def test_duplicate_memory_is_not_reinserted(self) -> None:
        db = self._db()

        service = LongTermMemoryService(db)
        first = service.remember_from_user_message("u1", "c1", "m1", "我喜欢简洁回答")
        second = service.remember_from_user_message("u1", "c1", "m2", "我喜欢简洁回答")

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
