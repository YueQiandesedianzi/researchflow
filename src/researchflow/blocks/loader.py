"""积木三级发现与版本解析。

发现顺序（后者被前者覆盖）：Core 内置 < 已安装积木包(entry points) < 项目 blocks/。
版本引用支持：``id``（任意版本取最新）、``id@^0.1.0``、``id@>=0.1,<0.2``、``id@0.1.0``。
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

from researchflow.errors import ContractError

_PRECEDENCE = {"builtin": 1, "pack": 2, "project": 3}


def builtin_blocks_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "blocks_builtin"


def parse_version(s: str) -> tuple:
    parts = str(s).split("-")[0].split("+")[0].split(".")
    nums = [int(p) for p in parts if p.isdigit()]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def match_version(spec, version: tuple) -> bool:
    """spec 为 None/空 → 任意；^x.y.z → 兼容范围；逗号子句；否则精确匹配。"""
    if spec is None or str(spec).strip() in ("", "*"):
        return True
    spec = str(spec).strip()
    if spec.startswith(("^", "~")):
        base = parse_version(spec[1:])
        upper = (0, base[1] + 1, 0) if base[0] == 0 else (base[0] + 1, 0, 0)
        return base <= version < upper
    if any(op in spec for op in (">", "<", "=", "!")) and "," in spec or spec.startswith((">", "<", "=", "!")):
        for clause in spec.split(","):
            clause = clause.strip()
            for op in (">=", "<=", "==", "!=", ">", "<"):
                if clause.startswith(op):
                    target = parse_version(clause[len(op):])
                    ok = {
                        ">=": version >= target, "<=": version <= target,
                        ">": version > target, "<": version < target,
                        "==": version == target, "!=": version != target,
                    }[op]
                    if not ok:
                        return False
                    break
            else:
                raise ContractError(f"无法解析版本子句: {clause!r}")
        return True
    return version == parse_version(spec)


def _iter_block_dirs(container: Path):
    if (container / "block.yaml").is_file():
        yield container
        return
    if not container.is_dir():
        return
    for child in sorted(container.iterdir()):
        if child.is_dir() and (child / "block.yaml").is_file():
            yield child


class BlockIndex:
    def __init__(self):
        self.blocks: dict[str, list] = {}
        self.warnings: list[str] = []

    def add(self, block) -> None:
        entries = self.blocks.setdefault(block.id, [])
        for existing in entries:
            if existing.version == block.version and existing.precedence == block.precedence:
                self.warnings.append(f"积木重复（忽略后者）: {block.ref} @ {block.dir}")
                return
        entries.append(block)
        entries.sort(key=lambda b: (b.precedence, b.version), reverse=True)

    def resolve(self, ref: str):
        block_id, _, spec = ref.partition("@")
        block_id = block_id.strip()
        spec = spec.strip() or None
        candidates = self.blocks.get(block_id)
        if not candidates:
            raise ContractError(
                f"未找到积木 {block_id!r}（引用 {ref!r}）。"
                f"可用: {', '.join(sorted(self.blocks)) or '（无）'}"
            )
        for block in candidates:  # 已按优先级+版本降序
            if match_version(spec, block.version):
                return block
        raise ContractError(
            f"积木 {block_id!r} 没有满足版本范围 {spec!r} 的版本；"
            f"已发现: {', '.join(b.version_str for b in candidates)}"
        )

    def all_best(self):
        """每个 id 的最高优先级+版本积木（用于 blocks list）。"""
        return [entries[0] for _, entries in sorted(self.blocks.items())]


def _load_container(index: BlockIndex, container: Path, source: str, precedence: int) -> None:
    from researchflow.blocks.schema import load_block

    for block_dir in _iter_block_dirs(container):
        try:
            index.add(load_block(block_dir, source, precedence))
        except ContractError as exc:
            index.warnings.append(f"积木加载失败（跳过）: {block_dir}: {exc.message}")


def discover(project_root=None, load_entry_points: bool = True) -> BlockIndex:
    """三级发现积木。project_root 为 None 时跳过项目级。"""
    index = BlockIndex()
    _load_container(index, builtin_blocks_dir(), "builtin", _PRECEDENCE["builtin"])

    if load_entry_points:
        try:
            eps = metadata.entry_points(group="researchflow.blocks")
        except TypeError:  # 旧版 Python 兼容
            eps = metadata.entry_points().get("researchflow.blocks", [])
        for ep in eps:
            try:
                target = ep.load()
                paths = target() if callable(target) else target
                if isinstance(paths, (str, Path)):
                    paths = [paths]
                for p in paths:
                    _load_container(index, Path(p), f"pack:{ep.name}", _PRECEDENCE["pack"])
            except Exception as exc:  # 包异常不应拖垮整个发现
                index.warnings.append(f"entry point {ep.name!r} 加载失败（跳过）: {exc}")

    if project_root is not None:
        _load_container(index, Path(project_root) / "blocks", "project", _PRECEDENCE["project"])
    return index


def block_source_hash(block) -> str:
    """积木源码指纹：block.yaml + 目录内全部 .py（按名排序）。"""
    import hashlib

    h = hashlib.sha256()
    files = [block.dir / "block.yaml"] + sorted(block.dir.glob("*.py"))
    for f in files:
        if f.is_file():
            h.update(f.name.encode("utf-8"))
            h.update(f.read_bytes())
    return h.hexdigest()
