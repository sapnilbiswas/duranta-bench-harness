"""
Unit and integration tests for 3GPP control-plane procedure latency extractor.
"""

from pathlib import Path
import shutil
import pytest

from scripts.control_plane_latency import (
    aggregate_procedure_stats,
    get_procedure_name,
    parse_control_plane_flows,
    run_tshark_extraction,
)


def test_procedure_name_resolution():
    """Verify that 3GPP procedure codes map accurately to official names."""
    # F1AP
    assert get_procedure_name("F1AP", 1) == "F1Setup"
    assert get_procedure_name("F1AP", 4) == "gNBCUConfigurationUpdate"
    assert get_procedure_name("F1AP", 5) == "UEContextSetup"

    # NGAP
    assert get_procedure_name("NGAP", 14) == "InitialContextSetup"
    assert get_procedure_name("NGAP", 21) == "NGSetup"
    assert get_procedure_name("NGAP", 29) == "PDUSessionResourceSetup"

    # E1AP
    assert get_procedure_name("E1AP", 3) == "gNB-CU-UP-E1Setup"
    assert get_procedure_name("E1AP", 8) == "bearerContextSetup"

    # Fallback for unknown codes
    assert get_procedure_name("F1AP", 999) == "F1AP_Procedure_999"


def test_parse_control_plane_flows_synthetic():
    """Verify request/response matching, latency calculation, and timeout detection."""
    synthetic_rows = [
        # F1Setup Request (frame 1, t = 100.000s)
        {
            "frame.number": "1",
            "frame.time_epoch": "100.000000",
            "ip.src": "10.0.0.1",
            "ip.dst": "10.0.0.2",
            "f1ap.procedureCode": "1",
            "f1ap.F1AP_PDU": "0",  # initiatingMessage
            "f1ap.TransactionID": "10",
        },
        # F1Setup Response (frame 2, t = 100.004200s -> delta = 4.2 ms)
        {
            "frame.number": "2",
            "frame.time_epoch": "100.004200",
            "ip.src": "10.0.0.2",
            "ip.dst": "10.0.0.1",
            "f1ap.procedureCode": "1",
            "f1ap.F1AP_PDU": "1",  # successfulOutcome
            "f1ap.TransactionID": "10",
        },
        # NGSetup Request (frame 3, t = 101.000000s)
        {
            "frame.number": "3",
            "frame.time_epoch": "101.000000",
            "ip.src": "10.0.0.1",
            "ip.dst": "10.0.0.3",
            "ngap.procedureCode": "21",
            "ngap.NGAP_PDU": "0",  # initiatingMessage
            "ngap.AMF_UE_NGAP_ID": "",
            "ngap.RAN_UE_NGAP_ID": "",
        },
        # NGSetup Failure / Reject (frame 4, t = 101.006500s -> delta = 6.5 ms, failure)
        {
            "frame.number": "4",
            "frame.time_epoch": "101.006500",
            "ip.src": "10.0.0.3",
            "ip.dst": "10.0.0.1",
            "ngap.procedureCode": "21",
            "ngap.NGAP_PDU": "2",  # unsuccessfulOutcome
            "ngap.AMF_UE_NGAP_ID": "",
            "ngap.RAN_UE_NGAP_ID": "",
        },
        # Unmatched request (frame 5, t = 102.000000s, never answered)
        {
            "frame.number": "5",
            "frame.time_epoch": "102.000000",
            "ip.src": "10.0.0.1",
            "ip.dst": "10.0.0.2",
            "f1ap.procedureCode": "5",  # UEContextSetup
            "f1ap.F1AP_PDU": "0",
            "f1ap.TransactionID": "",
            "f1ap.gNB_CU_UE_F1AP_ID": "42",
        },
    ]

    completed, unmatched = parse_control_plane_flows(synthetic_rows)

    assert len(completed) == 2
    assert len(unmatched) == 1

    # Verify F1Setup record
    f1 = completed[0]
    assert f1.protocol == "F1AP"
    assert f1.procedure_name == "F1Setup"
    assert f1.req_frame == 1
    assert f1.resp_frame == 2
    assert f1.latency_ms == pytest.approx(4.2, rel=1e-3)
    assert f1.outcome == "SUCCESS"

    # Verify NGSetup record (unsuccessful outcome)
    ng = completed[1]
    assert ng.protocol == "NGAP"
    assert ng.procedure_name == "NGSetup"
    assert ng.req_frame == 3
    assert ng.resp_frame == 4
    assert ng.latency_ms == pytest.approx(6.5, rel=1e-3)
    assert ng.outcome == "FAILURE"

    # Verify unmatched request
    un = unmatched[0]
    assert un.protocol == "F1AP"
    assert un.procedure_name == "UEContextSetup"
    assert un.frame == 5
    assert un.correlation_id == "42"


def test_aggregate_procedure_stats():
    """Verify calculation of statistical metrics."""
    synthetic_rows = [
        {"frame.number": "1", "frame.time_epoch": "0.000", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "0"},
        {"frame.number": "2", "frame.time_epoch": "0.002", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "1"},
        {"frame.number": "3", "frame.time_epoch": "0.010", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "0"},
        {"frame.number": "4", "frame.time_epoch": "0.014", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "1"},
        {"frame.number": "5", "frame.time_epoch": "0.020", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "0"},
        {"frame.number": "6", "frame.time_epoch": "0.026", "f1ap.procedureCode": "1", "f1ap.F1AP_PDU": "1"},
    ]
    completed, _ = parse_control_plane_flows(synthetic_rows)
    stats = aggregate_procedure_stats(completed)

    key = "F1AP::F1Setup"
    assert key in stats
    s = stats[key]
    assert s["count"] == 3
    assert s["min_ms"] == pytest.approx(2.0, rel=1e-3)
    assert s["median_ms"] == pytest.approx(4.0, rel=1e-3)
    assert s["mean_ms"] == pytest.approx(4.0, rel=1e-3)
    assert s["max_ms"] == pytest.approx(6.0, rel=1e-3)
    assert s["success_rate_pct"] == 100.0


def test_end_to_end_pcapng_parsing():
    """Integration test using tshark on sample_f1ap.pcapng fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_f1ap.pcapng"
    if not fixture_path.exists():
        pytest.skip("sample_f1ap.pcapng fixture not present")

    if not shutil.which("tshark"):
        pytest.skip("tshark not installed on PATH")

    raw_records = run_tshark_extraction(fixture_path)
    completed, unmatched = parse_control_plane_flows(raw_records)

    assert len(completed) == 2
    assert len(unmatched) == 1

    # Procedure 1: F1Setup -> 3.500 ms
    p1 = completed[0]
    assert p1.procedure_name == "F1Setup"
    assert p1.latency_ms == pytest.approx(3.5, rel=1e-3)
    assert p1.outcome == "SUCCESS"

    # Procedure 2: gNBCUConfigurationUpdate -> 2.250 ms
    p2 = completed[1]
    assert p2.procedure_name == "gNBCUConfigurationUpdate"
    assert p2.latency_ms == pytest.approx(2.25, rel=1e-3)
    assert p2.outcome == "SUCCESS"

    # Unmatched request
    assert unmatched[0].procedure_name == "F1Setup"
    assert unmatched[0].frame == 5
