"""Temporal Worker — Stub"""


class WorkflowWorker:
    def __init__(self, task_queue: str = ""):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError
