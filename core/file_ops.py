"""Safe file operations for generated Himagent artifacts."""
import os
from pathlib import Path
from werkzeug.utils import secure_filename


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = ROOT_DIR / "outputs"


def outputs_dir() -> str:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return str(OUTPUTS_DIR)


def safe_filename(filename: str) -> str:
    return secure_filename(filename or "")


def find_file_in_outputs(filename: str) -> str | None:
    """Find a generated file by basename under outputs/, including module folders."""
    safe_name = safe_filename(filename)
    if not safe_name or safe_name != (filename or ""):
        return None

    root = Path(outputs_dir()).resolve()
    for path in root.rglob(safe_name):
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return str(resolved)
    return None


def list_generated_tree() -> dict:
    """Return generated files grouped by module and artifact kind."""
    root = Path(outputs_dir()).resolve()
    tree: dict[str, dict[str, list[dict]]] = {}

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".xlsx", ".py"}:
            continue
        rel_path = path.relative_to(root).as_posix()
        parts = rel_path.split("/")
        if len(parts) >= 3:
            module_name = parts[0]
            folder_type = parts[1]
        elif len(parts) == 2:
            module_name = parts[0]
            folder_type = "excel" if path.suffix.lower() == ".xlsx" else "scripts"
        else:
            module_name = "other"
            folder_type = "excel" if path.suffix.lower() == ".xlsx" else "scripts"

        tree.setdefault(module_name, {"excel": [], "scripts": []})
        tree[module_name].setdefault(folder_type, [])
        stat = path.stat()
        tree[module_name][folder_type].append({
            "name": path.name,
            "rel_path": rel_path,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "type": "excel" if path.suffix.lower() == ".xlsx" else "python",
        })

    for module in tree.values():
        for files in module.values():
            files.sort(key=lambda item: item["modified"], reverse=True)
    return tree


def delete_generated_file(filename: str) -> bool:
    file_path = find_file_in_outputs(filename)
    if not file_path:
        return False
    os.remove(file_path)
    return True

