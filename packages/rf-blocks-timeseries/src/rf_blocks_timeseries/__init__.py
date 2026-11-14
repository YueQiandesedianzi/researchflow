"""ResearchFlow 时间序列积木包。

Core 的 Block Registry 经 entry points group ``researchflow.blocks``
发现本模块暴露的 BLOCKS_DIR。
"""

from pathlib import Path

BLOCKS_DIR = Path(__file__).parent / "blocks"
