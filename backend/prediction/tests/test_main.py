import logging

from prediction.main import main


def test_main_runs_without_error(caplog):
    """Scaffold du worker : ne fait que logger, ne doit pas lever."""
    with caplog.at_level(logging.INFO):
        main()
    assert caplog.records
