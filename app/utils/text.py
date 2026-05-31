import re
import html
import uuid
import os
from flask import current_app


def render_body(text: str) -> str:
    safe = html.escape(text)
    safe = safe.replace("\r\n", "\n").replace("\r", "\n")
    safe = re.sub(r"\[b\](.*?)\[/b\]",    r"<strong>\1</strong>", safe, flags=re.DOTALL)
    safe = re.sub(r"\[i\](.*?)\[/i\]",    r"<em>\1</em>",         safe, flags=re.DOTALL)
    safe = re.sub(r"\[u\](.*?)\[/u\]",    r"<u>\1</u>",           safe, flags=re.DOTALL)
    safe = re.sub(r"\[s\](.*?)\[/s\]",    r"<s>\1</s>",           safe, flags=re.DOTALL)
    safe = re.sub(r"\[code\](.*?)\[/code\]", r"<code>\1</code>",   safe, flags=re.DOTALL)
    safe = re.sub(r'\[url=(https?://[^\]]{1,500})\](.*?)\[/url\]',
                  r'<a href="\1" target="_blank" rel="noopener noreferrer">\2</a>', safe, flags=re.DOTALL)
    safe = re.sub(r'\[url\](https?://[^\[]{1,500})\[/url\]',
                  r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', safe)
    safe = re.sub(r'\[img\](https?://[^\[]{1,500})\[/img\]',
                  r'<img src="\1" class="post-img" alt="" loading="lazy" style="max-width:100%">', safe)
    paragraphs = re.split(r"\n{2,}", safe)
    return "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)


ALLOWED_EXTENSIONS = {
    "pdf", "txt", "md", "csv", "zip", "tar", "gz",
    "png", "jpg", "jpeg", "gif", "webp",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "mp3", "ogg", "mp4", "webm",
}

MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB default


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage) -> tuple[str, str, int]:
    """
    Save an uploaded file to UPLOAD_FOLDER.
    Returns (original_filename, stored_name, file_size_bytes)
    """
    original = file_storage.filename
    ext = original.rsplit(".", 1)[1].lower() if "." in original else "bin"
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored)
    file_storage.save(path)
    size = os.path.getsize(path)
    return original, stored, size


def delete_upload(stored_name: str):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
    if os.path.exists(path):
        os.remove(path)
