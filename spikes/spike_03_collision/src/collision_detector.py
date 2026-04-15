"""碰撞检测器 — Stub"""


class CollisionDetector:
    def detect_all(self, assets: list) -> list:
        raise NotImplementedError("CollisionDetector.detect_all 尚未实现")

    def build_index(self, assets: list):
        raise NotImplementedError

    def detect_incremental(self, moved_asset: dict) -> list:
        raise NotImplementedError
