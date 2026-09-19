import io

from pypdf import PdfReader


def extract_text(file_bytes: bytes, content_type: str, filename: str) -> str:
    """PDF나 텍스트 파일에서 내용을 문자열로 뽑아냄."""
    name_lower = (filename or "").lower()

    if content_type == "application/pdf" or name_lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("PDF에서 글자를 못 읽었어요 (스캔 이미지형 PDF일 수 있어요).")
        return text

    # 그 외에는 일반 텍스트 파일로 시도 (txt, md, csv 등)
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return file_bytes.decode("cp949")  # 한글 윈도우 인코딩 대비
        except UnicodeDecodeError:
            raise ValueError("이 파일 형식은 아직 못 읽어요 (PDF나 텍스트 파일만 가능해요).")
