"""布局序列化器 — Stub"""


class LayoutSerializer:
    def to_json(self, scene) -> str:
        raise NotImplementedError

    def collision_to_highlights(self, collisions: list) -> list:
        raise NotImplementedError

    def zones_to_overlays(self, zones: list) -> list:
        raise NotImplementedError
