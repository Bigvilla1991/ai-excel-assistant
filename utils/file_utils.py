"""文件工具：类型/大小校验与 CSV 编码检测。

安全约定（见方案 §13.2）：
- 上传时校验扩展名、大小、解压体积和解析结果；
- 编码检测结果展示给用户，允许手动覆盖。
"""

from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from utils.errors import FileValidationError

# 产品边界（见方案 §5.4）
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".csv"})
MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 压缩包/原始字节上限 20 MB
MAX_UNCOMPRESSED_SIZE: int = 500 * 1024 * 1024  # xlsx 解压后体积上限（zip 炸弹防护）
MAX_ROWS: int = 100_000  # 建议行数上限（仅提示）
MAX_COLUMNS: int = 500  # 硬性列数上限（宽表防护）

# CSV 编码选项（页面选择器与检测共用，避免双份列表漂移）。
# utf-16 系列仅供用户手动选择（BOM 直判场景），不参与自动"试解码"
# ——双字节序列几乎总能解码成功，对中文 CSV 误判率高。
ENCODING_OPTIONS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "utf-16",
    "utf-16-be",
    "gbk",
    "gb18030",
    "big5",
    "latin-1",
)

# 自动检测的候选编码（排除 utf-16 系列，防误判；UTF-16 由 BOM/NUL 启发式直判）
_DETECT_CANDIDATES: tuple[str, ...] = tuple(
    enc for enc in ENCODING_OPTIONS if not enc.startswith("utf-16")
)


def validate_file(filename: str, data: bytes) -> str:
    """校验文件名与内容，返回小写扩展名。

    抛 FileValidationError：扩展名不支持、内容为空、超过大小上限。
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        supported = "、".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(f"不支持的文件类型「{suffix}」，仅支持 {supported}。")

    if not data:
        raise FileValidationError("文件内容为空，请检查文件是否损坏。")

    if len(data) > MAX_FILE_SIZE:
        size_mb = len(data) / (1024 * 1024)
        raise FileValidationError(f"文件大小为 {size_mb:.1f} MB，超过 20MB 上限，请拆分后重试。")

    return suffix


def _probe_utf16(sample: bytes) -> str | None:
    """NUL 字节启发式：GBK/UTF-8 中文文本几乎不含 0x00，UTF-16 则大量出现。

    采样前 4KB，按奇偶位分布判断 LE/BE（ASCII 在 UTF-16 中表现为 ``XX 00``）。
    返回编码名或 None（无法判定）。
    """
    head = sample[:4096]
    if not head or b"\x00" not in head:
        return None
    odd_nulls = sum(1 for b in head[1::2] if b == 0)
    even_nulls = sum(1 for b in head[0::2] if b == 0)
    if odd_nulls > 0 and odd_nulls > even_nulls * 3:
        return "utf-16-le"
    if even_nulls > 0 and even_nulls > odd_nulls * 3:
        return "utf-16-be"
    return None


def detect_encoding(data: bytes, sample_limit: int = 1_000_000) -> str:
    """检测 CSV 文本编码，返回可读编码名。

    策略：BOM 直判 → NUL 启发式（无 BOM UTF-16）→ 按常见度对候选编码
    "试解码"，第一个完整解码成功者胜出 → 兜底 latin-1（不丢字节）。
    charset-normalizer 仅补充罕见编码（如 Shift-JIS）到候选末尾。
    """
    sample = data[:sample_limit]

    # BOM 直判，避免大文件 charset 检测耗时
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith(b"\xff\xfe"):
        return "utf-16"
    if sample.startswith(b"\xfe\xff"):
        return "utf-16-be"

    probe = _probe_utf16(sample)
    if probe is not None:
        return probe

    candidates: list[str] = list(_DETECT_CANDIDATES)
    best = from_bytes(sample).best()
    if best is not None and best.encoding and best.chaos <= 0.5 and best.encoding not in candidates:
        candidates.append(best.encoding)

    for enc in candidates:
        try:
            sample.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    # latin-1 在候选列表中，永不抛错，理论上不可达；保留兜底以防候选被篡改
    return "latin-1"


def check_column_limit(column_count: int) -> None:
    """列数硬性上限检查（宽表/恶意文件防护）。"""
    if column_count > MAX_COLUMNS:
        raise FileValidationError(
            f"文件列数为 {column_count}，超过 {MAX_COLUMNS} 列上限，无法处理。"
        )
