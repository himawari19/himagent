"""Server-side validation for uploaded SUT screenshots."""
from io import BytesIO
from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SCREENSHOTS = 10
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def validate_screenshot_payload(files_payload: list[dict]) -> None:
    if not files_payload:
        raise ValueError("No valid screenshot files uploaded.")
    if len(files_payload) > MAX_SCREENSHOTS:
        raise ValueError(f"Upload at most {MAX_SCREENSHOTS} screenshots.")

    for index, file_item in enumerate(files_payload, 1):
        filename = file_item.get("filename") or f"screenshot {index}"
        content = file_item.get("bytes") or b""
        if not content:
            raise ValueError(f"{filename} is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(f"{filename} exceeds the 5 MB per-file limit.")

        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                if image.format not in ALLOWED_IMAGE_FORMATS:
                    raise ValueError(f"{filename} must be JPEG, PNG, or WEBP.")
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                    raise ValueError(f"{filename} has unsupported dimensions.")
        except UnidentifiedImageError as exc:
            raise ValueError(f"{filename} is not a valid image file.") from exc
