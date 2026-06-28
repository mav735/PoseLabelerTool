from preflight import parse_used_ports


def test_parse_published_ports():
    sample = "0.0.0.0:7777->5432/tcp, [::]:7777->5432/tcp\n0.0.0.0:6666->5432/tcp\n\n80/tcp"
    assert parse_used_ports(sample) == {7777, 6666}


def test_parse_empty():
    assert parse_used_ports("") == set()
