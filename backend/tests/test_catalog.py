import pytest
from app.catalog import (Catalog, DatasetEntry, CatalogError,
                         load_catalog, load_catalog_safe, add_dataset)


def test_load_missing_file_gives_empty_catalog(tmp_path):
    cat = load_catalog(tmp_path / "nope.yaml")
    assert cat.datasets == []
    assert cat.models == []


def test_load_parses_datasets_and_models(tmp_path):
    p = tmp_path / "datasets.yaml"
    p.write_text(
        "datasets:\n"
        "  - name: people-v3\n"
        "    repo: mav735/pose-people\n"
        "    revision: main\n"
        "  - name: local-only\n"
        "models:\n"
        "  - name: yolo11n-pose\n"
        "    repo: mav735/pose-models\n"
        "    file: yolo11n-pose.pt\n"
    )
    cat = load_catalog(p)
    assert [d.name for d in cat.datasets] == ["people-v3", "local-only"]
    assert cat.datasets[0].repo == "mav735/pose-people"
    assert cat.datasets[1].repo is None
    assert cat.datasets[1].revision == "main"
    assert cat.models[0].file == "yolo11n-pose.pt"


def test_malformed_yaml_raises(tmp_path):
    p = tmp_path / "datasets.yaml"
    p.write_text("datasets: [oops\n")
    with pytest.raises(CatalogError):
        load_catalog(p)


def test_load_safe_swallows_malformed_yaml(tmp_path):
    p = tmp_path / "datasets.yaml"
    p.write_text("datasets: [oops\n")
    cat, err = load_catalog_safe(p)
    assert cat == Catalog()
    assert err is not None


def test_add_dataset_appends_and_persists(tmp_path):
    p = tmp_path / "datasets.yaml"
    add_dataset(p, DatasetEntry(name="people-v3", repo="mav735/pose-people"))
    add_dataset(p, DatasetEntry(name="hands-v1"))
    cat = load_catalog(p)
    assert [d.name for d in cat.datasets] == ["people-v3", "hands-v1"]


def test_add_dataset_rejects_duplicate_name(tmp_path):
    p = tmp_path / "datasets.yaml"
    add_dataset(p, DatasetEntry(name="people-v3"))
    with pytest.raises(CatalogError):
        add_dataset(p, DatasetEntry(name="people-v3"))
