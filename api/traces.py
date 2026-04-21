"""
追踪查看器 API
提供追踪查询和可视化数据
"""
import logging
from fastapi import APIRouter, HTTPException
from typing import Optional

from trace.trace_collector import TraceCollector

logger = logging.getLogger(__name__)

# 全局追踪收集器实例
trace_collector = TraceCollector(max_traces=1000)

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("", response_model=dict)
def list_traces(limit: int = 50):
    """列出最近的追踪"""
    try:
        traces = trace_collector.list_traces(limit=limit)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "traces": traces,
                "summary": trace_collector.get_trace_summary()
            }
        }
    except Exception as e:
        logger.error(f"Failed to list traces: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trace_id}", response_model=dict)
def get_trace(trace_id: str):
    """获取详细追踪信息"""
    trace = trace_collector.get_trace(trace_id)
    
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")
    
    return {
        "code": 200,
        "message": "success",
        "data": trace.to_dict()
    }


@router.get("/summary", response_model=dict)
def get_trace_summary():
    """获取追踪统计摘要"""
    summary = trace_collector.get_trace_summary()
    
    return {
        "code": 200,
        "message": "success",
        "data": summary
    }


@router.post("/clear", response_model=dict)
def clear_old_traces(older_than_seconds: int = 3600):
    """清理旧追踪"""
    try:
        trace_collector.clear_old_traces(older_than_seconds)
        
        return {
            "code": 200,
            "message": "success"
        }
    except Exception as e:
        logger.error(f"Failed to clear traces: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
