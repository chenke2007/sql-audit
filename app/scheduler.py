"""
SQL 采集调度器

支持定时自动采集慢SQL。
"""

import logging
from datetime import datetime
from typing import Callable, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.oracle.client import OracleClient
from app.oracle.collector import SQLCollector, SQLObject

logger = logging.getLogger(__name__)


class CollectionJob:
    """采集任务"""

    def __init__(
        self,
        name: str,
        collector: SQLCollector,
        callback: Optional[Callable[[List[SQLObject]], None]] = None
    ):
        self.name = name
        self.collector = collector
        self.callback = callback
        self.last_run: Optional[datetime] = None
        self.last_result_count: int = 0

    async def execute(self) -> List[SQLObject]:
        """执行采集任务"""
        logger.info(f"开始执行采集任务: {self.name}")
        self.last_run = datetime.now()

        try:
            # 采集慢SQL
            results = self.collector.collect_slow_sqls(
                top_n=settings.collector.top_n,
                cpu_threshold_ms=settings.collector.cpu_threshold_ms,
                elapsed_threshold_ms=settings.collector.elapsed_threshold_ms,
                buffer_gets_threshold=settings.collector.buffer_gets_threshold
            )

            self.last_result_count = len(results)
            logger.info(f"采集任务 {self.name} 完成，采集到 {len(results)} 条慢SQL")

            # 回调通知
            if self.callback:
                try:
                    self.callback(results)
                except Exception as e:
                    logger.error(f"采集任务回调失败: {e}")

            return results

        except Exception as e:
            logger.error(f"采集任务 {self.name} 失败: {e}")
            return []


class CollectionScheduler:
    """
    采集调度器

    管理定时采集任务的调度执行。
    """

    def __init__(self, oracle_client: OracleClient):
        self.client = oracle_client
        self.scheduler = AsyncIOScheduler()
        self.jobs: dict[str, CollectionJob] = {}
        self._running = False

    def start(self):
        """启动调度器"""
        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("采集调度器已启动")

    def shutdown(self):
        """关闭调度器"""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("采集调度器已关闭")

    def add_slow_sql_job(
        self,
        job_id: str = "slow_sql_collection",
        interval_minutes: int = 5,
        callback: Optional[Callable[[List[SQLObject]], None]] = None
    ) -> CollectionJob:
        """
        添加慢SQL自动采集任务

        Args:
            job_id: 任务ID
            interval_minutes: 执行间隔（分钟）
            callback: 采集完成后的回调函数

        Returns:
            采集任务对象
        """
        collector = SQLCollector(self.client)
        job = CollectionJob(job_id, collector, callback)
        self.jobs[job_id] = job

        # 添加定时任务
        self.scheduler.add_job(
            job.execute,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True,
            max_instances=1  # 防止任务重叠执行
        )

        logger.info(f"已添加慢SQL采集任务 {job_id}，间隔 {interval_minutes} 分钟")
        return job

    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self.jobs:
            self.scheduler.remove_job(job_id)
            del self.jobs[job_id]
            logger.info(f"已移除采集任务 {job_id}")

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """获取任务状态"""
        job = self.jobs.get(job_id)
        if not job:
            return None

        return {
            "job_id": job_id,
            "name": job.name,
            "last_run": job.last_run.isoformat() if job.last_run else None,
            "last_result_count": job.last_result_count
        }

    def get_all_status(self) -> List[dict]:
        """获取所有任务状态"""
        return [self.get_job_status(job_id) for job_id in self.jobs]


# 全局调度器实例
collection_scheduler = CollectionScheduler(oracle_client=None)  # 需要在初始化时设置 client
