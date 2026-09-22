from app.models import PendingChange


def test_a_pending_change_round_trips(db_session):
    c = PendingChange(dataset="ds", path="labels/003/1.txt", op="add")
    db_session.add(c); db_session.commit()
    got = db_session.query(PendingChange).one()
    assert (got.dataset, got.path, got.op) == ("ds", "labels/003/1.txt", "add")
    assert got.created_at is not None


def test_many_changes_for_one_path_are_allowed(db_session):
    """No unique constraint: coalescing happens at flush, by id order.

    A unique key on (dataset, path) would force an upsert on every keystroke
    and lose the ordering that decides whether an add or a delete wins.
    """
    for _ in range(3):
        db_session.add(PendingChange(dataset="ds", path="labels/1.txt", op="add"))
    db_session.commit()
    assert db_session.query(PendingChange).count() == 3
