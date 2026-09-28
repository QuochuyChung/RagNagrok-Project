import io
import zipfile
from pathlib import Path

MAX_BATCH_FILES = 200
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024  # 200MB


def extract_zip_safely(content: bytes) -> list[tuple[str, bytes]]:
    items, total_size = [], 0
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_BATCH_FILES:
            raise ValueError(f"Zip vượt quá {MAX_BATCH_FILES} file")

        for info in infos:
            p = Path(info.filename)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"Đường dẫn không an toàn trong zip: {info.filename}")
            if "__MACOSX" in p.parts or p.name.startswith("."):
                continue  # bỏ junk file hệ thống (macOS, .DS_Store...)

            total_size += info.file_size
            if total_size > MAX_TOTAL_UNCOMPRESSED:
                raise ValueError("Zip giải nén vượt giới hạn dung lượng")

            # Giữ nguyên relative path làm doc_name -> không flatten về basename,
            # tránh 2 file trùng tên ở 2 subfolder bị hiểu nhầm là version của nhau
            items.append((p.as_posix(), zf.read(info)))

    return items