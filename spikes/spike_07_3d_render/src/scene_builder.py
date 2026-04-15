"""3D 场景构建器 — Stub"""
from dataclasses import dataclass, field


@dataclass
class CameraConfig:
    type: str = ""
    position: list = field(default_factory=list)
    fov: float | None = None


@dataclass
class Scene:
    meshes: list = field(default_factory=list)
    floor: dict | None = None
    camera_config: CameraConfig | None = None
    use_instanced_mesh: bool = False


class SceneBuilder:
    def build(self, asset_count: int, factory_size: tuple = (100_000, 60_000)) -> Scene:
        raise NotImplementedError

    def get_camera_config(self, mode: str, factory_size: tuple) -> CameraConfig:
        raise NotImplementedError
