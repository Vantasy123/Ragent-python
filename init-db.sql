-- 初始化数据库脚本
-- 创建 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 设置时区
ALTER DATABASE ragent SET timezone TO 'Asia/Shanghai';

-- 显示完成信息
SELECT 'Database initialized successfully!' AS status;
