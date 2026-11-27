from unittest.mock import Mock

from runtime.charge.runtime.support import output_is_known, output_is_on, phase_log


def test_shared_output_state_normalization():
    assert output_is_known(None) is False
    assert output_is_known("UNKNOWN") is False
    assert output_is_known("unavailable") is False
    assert output_is_known("off") is True
    assert output_is_on(True) is True
    assert output_is_on("on") is True
    assert output_is_on("off") is False


def test_shared_phase_log_uses_injected_stage_logger():
    logger = Mock()
    phase_log(logger, "MAIN", 14.7, 1.2, 25.0)
    logger.info.assert_called_once()
    args = logger.info.call_args.args
    assert args[0] == "%s | %-12s | %5.2fВ | %5.2fА | %5.1f°C"
    assert isinstance(args[1], str)
    assert args[2:] == ("MAIN", 14.7, 1.2, 25.0)


def test_all_stage_scaffolds_import_the_same_shared_helpers():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "runtime/charge/runtime/main_scaffold.py",
        "runtime/charge/runtime/mix_scaffold.py",
        "runtime/charge/runtime/recovery_scaffold.py",
        "runtime/charge/runtime/residual_scaffold.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "output_is_known as _output_is_known" in source
        assert "output_is_on as _output_is_on" in source
        assert "phase_log as _phase_log" in source
        assert "def _output_is_known(" not in source
        assert "def _output_is_on(" not in source
        assert "def _phase_log(" not in source
