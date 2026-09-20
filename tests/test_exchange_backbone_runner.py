from pathlib import Path

from marketdata.runners.acquire_exchange_backbone import _seed_tree


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "marketdata/runners/acquire_exchange_backbone.py"


def test_seed_helper_is_defined_before_script_entrypoint() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert source.index("def _seed_tree") < source.index('if __name__ == "__main__"')


def test_seed_helper_copies_an_immutable_evidence_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    (source / "nested").mkdir(parents=True)
    (source / "nested/evidence.bin").write_bytes(b"accepted evidence")
    _seed_tree(source, destination)
    assert (destination / "nested/evidence.bin").read_bytes() == b"accepted evidence"
