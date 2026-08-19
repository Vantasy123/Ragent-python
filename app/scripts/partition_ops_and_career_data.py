"""历史运维 Agent 数据与当前求职 Agent 数据分区分离脚本。"""

from __future__ import annotations

import logging
from sqlalchemy import text
from app.core.database import SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="[Data-Partition] %(asctime)s - %(message)s")
logger = logging.getLogger("data-partition")


def add_column_if_not_exists(table: str, col_def: str, col_name: str):
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
            logger.info(f"成功为 {table} 添加 {col_name} 字段")
    except Exception as e:
        logger.info(f"表 {table} 的 {col_name} 字段可能已存在: {e}")


def main():
    logger.info("1. 确保数据表分区字段已存在...")
    add_column_if_not_exists("knowledge_base", "category VARCHAR(64) NOT NULL DEFAULT 'career'", "category")
    add_column_if_not_exists("conversation", "domain VARCHAR(32) NOT NULL DEFAULT 'career'", "domain")
    add_column_if_not_exists("trace_run", "domain VARCHAR(32) NOT NULL DEFAULT 'career'", "domain")
    add_column_if_not_exists("evaluation_run", "domain VARCHAR(32) NOT NULL DEFAULT 'career'", "domain")
    add_column_if_not_exists("evaluation_dataset", "domain VARCHAR(32) NOT NULL DEFAULT 'career'", "domain")

    logger.info("2. 执行历史运维数据归档隔离...")
    with engine.begin() as conn:
        # 归档历史运维知识库
        r1 = conn.execute(text("""
            UPDATE knowledge_base 
            SET category = 'ops_archive' 
            WHERE name LIKE '%运维%' 
               OR name LIKE '%SRE%' 
               OR name LIKE '%监控%' 
               OR name LIKE '%Prometheus%' 
               OR name LIKE '%服务器%'
               OR description LIKE '%运维%'
        """))
        logger.info(f"已归档历史运维知识库: {r1.rowcount} 条")

        # 归档历史运维评测集
        r2 = conn.execute(text("""
            UPDATE evaluation_dataset 
            SET domain = 'ops_archive' 
            WHERE name LIKE '%运维%' 
               OR name LIKE '%SRE%' 
               OR name LIKE '%监控%' 
               OR name LIKE '%告警%' 
               OR description LIKE '%运维%'
        """))
        logger.info(f"已归档历史运维评测集: {r2.rowcount} 条")

        # 归档历史运维对话
        r3 = conn.execute(text("""
            UPDATE conversation 
            SET domain = 'ops_archive' 
            WHERE title LIKE '%服务器%' 
               OR title LIKE '%监控%' 
               OR title LIKE '%CPU%' 
               OR title LIKE '%内存%' 
               OR title LIKE '%Prometheus%' 
               OR title LIKE '%集群%' 
               OR title LIKE '%K8s%' 
               OR title LIKE '%运维%'
        """))
        logger.info(f"已归档历史运维对话: {r3.rowcount} 条")

        # 标记所有求职数据为 career 域
        conn.execute(text("UPDATE knowledge_base SET category = 'career' WHERE category IS NULL OR category = ''"))
        conn.execute(text("UPDATE evaluation_dataset SET domain = 'career' WHERE domain IS NULL OR domain = ''"))
        conn.execute(text("UPDATE conversation SET domain = 'career' WHERE domain IS NULL OR domain = ''"))
        conn.execute(text("UPDATE trace_run SET domain = 'career' WHERE domain IS NULL OR domain = ''"))
        conn.execute(text("UPDATE evaluation_run SET domain = 'career' WHERE domain IS NULL OR domain = ''"))

    logger.info("3. 历史运维数据与当前求职数据分区分离全部完成！")


if __name__ == "__main__":
    main()
