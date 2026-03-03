import json
from pathlib import Path


class JsonStateStore:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._processed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._processed = set(raw.get("processed", []))

    def is_processed(self, key: str) -> bool:
        return key in self._processed

    def mark_processed(self, key: str) -> None:
        self._processed.add(key)
        self._save()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps({"processed": sorted(self._processed)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.state_path)
