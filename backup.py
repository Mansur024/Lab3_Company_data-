"""ПР1. Резервное копирование с ротацией и проверкой целостности."""
import hashlib
import json
import shutil
import tarfile
import time
from datetime import datetime
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

SOURCE = Path("company_data")      # что копируем
BACKUP_DIR = Path("backups")       # куда складываем архивы
KEEP_LAST = 5                      # сколько последних копий хранить


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_manifest(folder):
    """Контрольная сумма каждого файла: {относительный_путь: sha256}."""
    return {str(p.relative_to(folder)): sha256(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def create_backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_DIR / f"backup_{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(SOURCE, arcname=SOURCE.name)
    manifest = {"created": stamp, "archive_sha256": sha256(archive),
                "files": make_manifest(SOURCE)}
    archive.with_suffix("").with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Создан {archive.name}, файлов: {len(manifest['files'])}, "
          f"размер: {archive.stat().st_size / 1024:.1f} КБ")
    return archive


def rotate():
    archives = sorted(BACKUP_DIR.glob("backup_*.tar.gz"))
    for old in archives[:-KEEP_LAST]:
        old.unlink()
        old.with_suffix("").with_suffix(".json").unlink(missing_ok=True)
        print(f"[ROTATE] Удалена старая копия {old.name}")


def verify_restore(archive):
    """Восстанавливает архив во временную папку и сравнивает контрольные суммы."""
    manifest = json.loads(archive.with_suffix(
        "").with_suffix(".json").read_text(encoding="utf-8"))
    if sha256(archive) != manifest["archive_sha256"]:
        print("[FAIL] Архив повреждён: контрольная сумма не совпадает")
        return False
    tmp = Path("restore_test")
    shutil.rmtree(tmp, ignore_errors=True)
    with tarfile.open(archive) as tar:
        tar.extractall(tmp, filter="data")
    restored = make_manifest(tmp / SOURCE.name)
    shutil.rmtree(tmp)

    if restored == manifest["files"]:
        print(
            f"[OK] Восстановление проверено: {len(restored)} файлов совпадают")
        return True

    orig_files = set(manifest["files"].keys())
    rest_files = set(restored.keys())

    missing = orig_files - rest_files       # отсутствуют файлы
    extra = rest_files - orig_files            # лишние файлы
    common = orig_files & rest_files           # общие файлы
    modified = [f for f in common if restored[f]
                != manifest["files"][f]]  # измененные хеши

    print("[FAIL] Восстановленные данные не совпадают с оригиналом:")
    if missing:
        print(f"  - Отсутствуют файлы ({len(missing)}): {list(missing)}")
    if extra:
        print(f"  - Лишние файлы ({len(extra)}): {list(extra)}")
    if modified:
        print(f"  - Изменены файлы ({len(modified)}): {modified}")

    return False


def restore(archive):
    """Восстанавливает данные из архива после инцидента, замеряя время."""
    start_time = time.perf_counter()

    if SOURCE.exists():
        shutil.rmtree(SOURCE)
        print(f"[CLEAN] Поврежденная папка {SOURCE} удалена")

    # Распаковываем архив
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall()

    elapsed_time = time.perf_counter() - start_time
    print(f"[OK] Данные успешно восстановлены из {archive.name}")
    print(f"[TIME] Время восстановления: {elapsed_time:.4f} секунд")


if __name__ == "__main__":

    latest_archive = sorted(BACKUP_DIR.glob("backup_*.tar.gz"))[-1]

    restore(latest_archive)
