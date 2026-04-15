"""Temporal Client — Stub"""


class WorkflowClient:
    def run_workflow(self, workflow_cls, args=None, task_queue="", activity_overrides=None):
        raise NotImplementedError

    def start_workflow_async(self, workflow_cls, args=None, task_queue="", activity_overrides=None):
        raise NotImplementedError

    def run_parallel_activities(self, activities=None, task_queue=""):
        raise NotImplementedError
