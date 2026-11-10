#!/usr/bin/env python3
"""
control_plane_latency.py
========================
Extracts and computes 3GPP control-plane elementary procedure latency from
packet capture (.pcap / .pcapng) files using tshark.

Supported Protocols:
- F1AP (3GPP TS 38.473): CU-DU interface
- NGAP (3GPP TS 38.413): gNB-AMF interface
- E1AP (3GPP TS 38.463): CU-CP to CU-UP interface

Methodology:
1. Invokes tshark to parse control-plane protocol headers into structured fields.
2. Identifies initiatingMessage (PDU index 0) requests and correlates them with
   matching successfulOutcome (PDU index 1) or unsuccessfulOutcome (PDU index 2)
   responses using protocol transaction IDs and UE IDs.
3. Calculates procedure round-trip latency:
       Δt = t_response - t_request
4. Generates individual procedure records and aggregated statistical summaries
   (min, median, mean, p95/p99, max, IQR).
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


# Standard 3GPP Elementary Procedure Codes
F1AP_PROCEDURES: Dict[int, str] = {
    0: "Reset",
    1: "F1Setup",
    2: "ErrorIndication",
    3: "gNBDUConfigurationUpdate",
    4: "gNBCUConfigurationUpdate",
    5: "UEContextSetup",
    6: "UEContextRelease",
    7: "UEContextModification",
    8: "UEContextModificationRequired",
    9: "UEMobilityCommand",
    10: "UEContextReleaseRequest",
    11: "InitialULRRCMessageTransfer",
    12: "DLRRCMessageTransfer",
    13: "ULRRCMessageTransfer",
    14: "privateMessage",
    15: "UEInactivityNotification",
    16: "GNBDUResourceCoordination",
    17: "SystemInformationDeliveryCommand",
    18: "Paging",
    19: "Notify",
    20: "WriteReplaceWarning",
    21: "PWSCancel",
    22: "PWSRestartIndication",
    23: "PWSFailureIndication",
}

NGAP_PROCEDURES: Dict[int, str] = {
    0: "AMFConfigurationUpdate",
    1: "AMFStatusIndication",
    2: "CellTrafficTrace",
    3: "DeactivateTrace",
    4: "DownlinkNASTransport",
    5: "DownlinkNonUEAssociatedNRPPaTransport",
    6: "DownlinkRANConfigurationTransfer",
    7: "DownlinkRANStatusTransfer",
    8: "DownlinkUEAssociatedNRPPaTransport",
    9: "ErrorIndication",
    10: "HandoverCancel",
    11: "HandoverNotification",
    12: "HandoverPreparation",
    13: "HandoverResourceAllocation",
    14: "InitialContextSetup",
    15: "InitialUEMessage",
    16: "LocationReportingControl",
    17: "LocationReportingFailureIndication",
    18: "LocationReport",
    19: "NASNonDeliveryIndication",
    20: "NGReset",
    21: "NGSetup",
    22: "OverloadStart",
    23: "OverloadStop",
    24: "Paging",
    25: "PathSwitchRequest",
    26: "PDUSessionResourceModify",
    27: "PDUSessionResourceModifyIndication",
    28: "PDUSessionResourceRelease",
    29: "PDUSessionResourceSetup",
    30: "PDUSessionResourceNotify",
    31: "PrivateMessage",
    36: "RerouteNASRequest",
    40: "UEContextModification",
    41: "UEContextRelease",
    42: "UEContextReleaseRequest",
    43: "UERadioCapabilityCheck",
    44: "UERadioCapabilityInfoIndication",
}

E1AP_PROCEDURES: Dict[int, str] = {
    0: "Reset",
    1: "ErrorIndication",
    2: "privateMessage",
    3: "gNB-CU-UP-E1Setup",
    4: "gNB-CU-CP-E1Setup",
    5: "gNB-CU-UP-ConfigurationUpdate",
    6: "gNB-CU-CP-ConfigurationUpdate",
    7: "e1Release",
    8: "bearerContextSetup",
    9: "bearerContextModification",
    10: "bearerContextModificationRequired",
    11: "bearerContextRelease",
    12: "bearerContextReleaseRequest",
    13: "bearerContextInactivityNotification",
    14: "dLDataNotification",
    15: "dataUsageReport",
}

# 3GPP Class-1 procedures (request-response elementary procedures)
CLASS1_PROCEDURES = {
    "F1AP": {0, 1, 3, 4, 5, 6, 7, 8, 16, 20, 21},
    "NGAP": {0, 10, 12, 13, 14, 20, 21, 25, 26, 27, 28, 29, 40, 41, 43},
    "E1AP": {0, 3, 4, 5, 6, 7, 8, 9, 10, 11},
}


@dataclass
class ProcedureRecord:
    protocol: str
    procedure_code: int
    procedure_name: str
    req_frame: int
    req_time_epoch: float
    resp_frame: int
    resp_time_epoch: float
    latency_ms: float
    latency_us: float
    outcome: str  # "SUCCESS" or "FAILURE"
    correlation_id: str
    src_ip: str
    dst_ip: str


@dataclass
class PendingRequest:
    protocol: str
    procedure_code: int
    procedure_name: str
    frame: int
    time_epoch: float
    correlation_id: str
    src_ip: str
    dst_ip: str


def get_procedure_name(protocol: str, code: int) -> str:
    """Returns human-readable 3GPP procedure name or fallback."""
    if protocol == "F1AP":
        return F1AP_PROCEDURES.get(code, f"F1AP_Procedure_{code}")
    if protocol == "NGAP":
        return NGAP_PROCEDURES.get(code, f"NGAP_Procedure_{code}")
    if protocol == "E1AP":
        return E1AP_PROCEDURES.get(code, f"E1AP_Procedure_{code}")
    return f"{protocol}_Procedure_{code}"


def check_tshark() -> str:
    """Verifies that tshark is available on PATH."""
    path = shutil.which("tshark")
    if not path:
        raise RuntimeError(
            "tshark binary not found on PATH. Install tshark (e.g. apt-get install tshark) "
            "or run inside the project container."
        )
    return path


def run_tshark_extraction(pcap_path: Path, tshark_bin: str = "tshark") -> List[Dict[str, str]]:
    """Runs tshark to extract control plane packet fields as a list of dicts."""
    cmd = [
        tshark_bin,
        "-r", str(pcap_path),
        "-T", "fields",
        "-e", "frame.number",
        "-e", "frame.time_epoch",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "sctp.srcport",
        "-e", "sctp.dstport",
        "-e", "f1ap.procedureCode",
        "-e", "f1ap.F1AP_PDU",
        "-e", "f1ap.TransactionID",
        "-e", "f1ap.gNB_CU_UE_F1AP_ID",
        "-e", "f1ap.gNB_DU_UE_F1AP_ID",
        "-e", "ngap.procedureCode",
        "-e", "ngap.NGAP_PDU",
        "-e", "ngap.AMF_UE_NGAP_ID",
        "-e", "ngap.RAN_UE_NGAP_ID",
        "-e", "e1ap.procedureCode",
        "-e", "e1ap.E1AP_PDU",
        "-e", "e1ap.TransactionID",
        "-e", "e1ap.gNB_CU_CP_UE_E1AP_ID",
        "-e", "e1ap.gNB_CU_UP_UE_E1AP_ID",
        "-E", "header=y",
        "-E", "separator=,",
        "-E", "quote=d",
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    lines = res.stdout.strip().splitlines()
    if not lines:
        return []

    reader = csv.DictReader(lines)
    return list(reader)


def parse_control_plane_flows(records: List[Dict[str, str]]) -> Tuple[List[ProcedureRecord], List[PendingRequest]]:
    """
    Correlates initiatingMessage requests with corresponding response outcomes.
    Returns:
        (completed_procedures, unmatched_pending_requests)
    """
    completed: List[ProcedureRecord] = []
    # Key: (protocol, procedure_code, correlation_id) -> list of PendingRequest (FIFO queue)
    pending: Dict[Tuple[str, int, str], List[PendingRequest]] = {}

    for row in records:
        try:
            frame_no = int(row.get("frame.number", "0") or "0")
            time_epoch = float(row.get("frame.time_epoch", "0.0") or "0.0")
        except ValueError:
            continue

        src_ip = row.get("ip.src", "")
        dst_ip = row.get("ip.dst", "")

        # Check F1AP
        f1_code = row.get("f1ap.procedureCode")
        f1_pdu = row.get("f1ap.F1AP_PDU")
        if f1_code and f1_pdu:
            _process_packet_event(
                protocol="F1AP",
                proc_code_raw=f1_code,
                pdu_type_raw=f1_pdu,
                corr_id_raw=row.get("f1ap.TransactionID") or row.get("f1ap.gNB_CU_UE_F1AP_ID") or row.get("f1ap.gNB_DU_UE_F1AP_ID") or "",
                frame_no=frame_no,
                time_epoch=time_epoch,
                src_ip=src_ip,
                dst_ip=dst_ip,
                pending=pending,
                completed=completed,
            )

        # Check NGAP
        ng_code = row.get("ngap.procedureCode")
        ng_pdu = row.get("ngap.NGAP_PDU")
        if ng_code and ng_pdu:
            _process_packet_event(
                protocol="NGAP",
                proc_code_raw=ng_code,
                pdu_type_raw=ng_pdu,
                corr_id_raw=row.get("ngap.AMF_UE_NGAP_ID") or row.get("ngap.RAN_UE_NGAP_ID") or "",
                frame_no=frame_no,
                time_epoch=time_epoch,
                src_ip=src_ip,
                dst_ip=dst_ip,
                pending=pending,
                completed=completed,
            )

        # Check E1AP
        e1_code = row.get("e1ap.procedureCode")
        e1_pdu = row.get("e1ap.E1AP_PDU")
        if e1_code and e1_pdu:
            _process_packet_event(
                protocol="E1AP",
                proc_code_raw=e1_code,
                pdu_type_raw=e1_pdu,
                corr_id_raw=row.get("e1ap.TransactionID") or row.get("e1ap.gNB_CU_CP_UE_E1AP_ID") or row.get("e1ap.gNB_CU_UP_UE_E1AP_ID") or "",
                frame_no=frame_no,
                time_epoch=time_epoch,
                src_ip=src_ip,
                dst_ip=dst_ip,
                pending=pending,
                completed=completed,
            )

    unmatched = [req for queue in pending.values() for req in queue]
    return completed, unmatched


def _process_packet_event(
    protocol: str,
    proc_code_raw: str,
    pdu_type_raw: str,
    corr_id_raw: str,
    frame_no: int,
    time_epoch: float,
    src_ip: str,
    dst_ip: str,
    pending: Dict[Tuple[str, int, str], List[PendingRequest]],
    completed: List[ProcedureRecord],
) -> None:
    """Helper to process individual protocol event and match requests/responses."""
    # Handle comma-separated values if multiple chunks are bundled
    code_str = proc_code_raw.split(",")[0].strip()
    pdu_str = pdu_type_raw.split(",")[0].strip()
    corr_id = corr_id_raw.split(",")[0].strip() if corr_id_raw else "default"

    try:
        proc_code = int(code_str)
        pdu_type = int(pdu_str)
    except ValueError:
        return

    # Check if this procedure is a Class-1 procedure
    class1_set = CLASS1_PROCEDURES.get(protocol, set())
    if proc_code not in class1_set:
        return

    proc_name = get_procedure_name(protocol, proc_code)
    key = (protocol, proc_code, corr_id)

    if pdu_type == 0:
        # initiatingMessage (Request)
        req = PendingRequest(
            protocol=protocol,
            procedure_code=proc_code,
            procedure_name=proc_name,
            frame=frame_no,
            time_epoch=time_epoch,
            correlation_id=corr_id,
            src_ip=src_ip,
            dst_ip=dst_ip,
        )
        pending.setdefault(key, []).append(req)

    elif pdu_type in (1, 2):
        # successfulOutcome (1) or unsuccessfulOutcome (2)
        queue = pending.get(key)
        matched_req: Optional[PendingRequest] = None

        if queue:
            matched_req = queue.pop(0)
            if not queue:
                del pending[key]
        else:
            # Fallback: check default key if corr_id wasn't identical
            default_key = (protocol, proc_code, "default")
            def_queue = pending.get(default_key)
            if def_queue:
                matched_req = def_queue.pop(0)
                if not def_queue:
                    del pending[default_key]
            else:
                # Fallback: check any pending request with matching protocol & procedure
                for candidate_key in list(pending.keys()):
                    if candidate_key[0] == protocol and candidate_key[1] == proc_code:
                        matched_req = pending[candidate_key].pop(0)
                        if not pending[candidate_key]:
                            del pending[candidate_key]
                        break

        if matched_req:
            delta_s = time_epoch - matched_req.time_epoch
            outcome = "SUCCESS" if pdu_type == 1 else "FAILURE"
            rec = ProcedureRecord(
                protocol=protocol,
                procedure_code=proc_code,
                procedure_name=proc_name,
                req_frame=matched_req.frame,
                req_time_epoch=matched_req.time_epoch,
                resp_frame=frame_no,
                resp_time_epoch=time_epoch,
                latency_ms=round(delta_s * 1000.0, 4),
                latency_us=round(delta_s * 1_000_000.0, 2),
                outcome=outcome,
                correlation_id=corr_id,
                src_ip=src_ip,
                dst_ip=dst_ip,
            )
            completed.append(rec)


def aggregate_procedure_stats(completed: List[ProcedureRecord]) -> Dict[str, Any]:
    """Computes summary statistics per procedure type."""
    groups: Dict[str, List[ProcedureRecord]] = {}
    for rec in completed:
        key = f"{rec.protocol}::{rec.procedure_name}"
        groups.setdefault(key, []).append(rec)

    stats = {}
    for key, items in sorted(groups.items()):
        latencies = [r.latency_ms for r in items]
        latencies.sort()
        n = len(latencies)

        q1 = latencies[n // 4] if n >= 4 else latencies[0]
        q3 = latencies[(3 * n) // 4] if n >= 4 else latencies[-1]
        iqr = round(q3 - q1, 4)

        success_count = sum(1 for r in items if r.outcome == "SUCCESS")
        stats[key] = {
            "count": n,
            "success_count": success_count,
            "failure_count": n - success_count,
            "success_rate_pct": round((success_count / n) * 100.0, 1),
            "min_ms": round(min(latencies), 4),
            "median_ms": round(statistics.median(latencies), 4),
            "mean_ms": round(statistics.mean(latencies), 4),
            "max_ms": round(max(latencies), 4),
            "iqr_ms": iqr,
        }
    return stats


def format_text_report(
    completed: List[ProcedureRecord],
    unmatched: List[PendingRequest],
    stats: Dict[str, Any],
) -> str:
    """Formats human-readable markdown/text summary report."""
    lines = [
        "# Control-Plane Procedure Latency Report",
        "",
        "## Summary Statistics by Procedure",
        "",
        "| Procedure | Count | Success Rate | Min (ms) | Median (ms) | Mean (ms) | Max (ms) | IQR (ms) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for proc, s in stats.items():
        lines.append(
            f"| `{proc}` | {s['count']} | {s['success_rate_pct']}% | "
            f"{s['min_ms']:.3f} | {s['median_ms']:.3f} | {s['mean_ms']:.3f} | "
            f"{s['max_ms']:.3f} | {s['iqr_ms']:.3f} |"
        )

    lines.extend([
        "",
        "## Individual Transactions",
        "",
        "| Protocol | Procedure | Req Frame | Resp Frame | Outcome | Latency (ms) | Latency (µs) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for r in completed:
        lines.append(
            f"| {r.protocol} | {r.procedure_name} | #{r.req_frame} | #{r.resp_frame} | "
            f"{r.outcome} | {r.latency_ms:.3f} ms | {r.latency_us:.1f} µs |"
        )

    if unmatched:
        lines.extend([
            "",
            "## Unmatched / Timed-out Requests",
            "",
            "| Protocol | Procedure | Frame | Timestamp | Correlation ID |",
            "| :--- | :--- | :---: | :---: | :--- |",
        ])
        for u in unmatched:
            lines.append(
                f"| {u.protocol} | {u.procedure_name} | #{u.frame} | {u.time_epoch:.6f} | `{u.correlation_id}` |"
            )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute 3GPP control-plane elementary procedure latency from pcaps using tshark."
    )
    parser.add_argument("pcap", type=Path, help="Path to input .pcap or .pcapng capture file")
    parser.add_argument("--json", action="store_true", help="Output full report as JSON to stdout")
    parser.add_argument("--output", type=Path, help="Save JSON report to file")
    parser.add_argument("--csv", type=Path, help="Save individual procedure records to CSV file")
    parser.add_argument("--tshark-bin", default="tshark", help="Path to tshark binary")

    args = parser.parse_args()

    if not args.pcap.exists():
        sys.exit(f"Error: pcap file not found: {args.pcap}")

    try:
        check_tshark()
    except RuntimeError as err:
        sys.exit(f"Error: {err}")

    raw_records = run_tshark_extraction(args.pcap, tshark_bin=args.tshark_bin)
    completed, unmatched = parse_control_plane_flows(raw_records)
    stats = aggregate_procedure_stats(completed)

    report_data = {
        "pcap_file": str(args.pcap.resolve()),
        "total_packets_parsed": len(raw_records),
        "total_procedures_completed": len(completed),
        "total_unmatched_requests": len(unmatched),
        "summary_statistics": stats,
        "completed_procedures": [asdict(r) for r in completed],
        "unmatched_requests": [asdict(u) for u in unmatched],
    }

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "protocol", "procedure_code", "procedure_name", "req_frame", "req_time_epoch",
                    "resp_frame", "resp_time_epoch", "latency_ms", "latency_us", "outcome", "correlation_id"
                ]
            )
            writer.writeheader()
            for r in completed:
                d = asdict(r)
                d.pop("src_ip", None)
                d.pop("dst_ip", None)
                writer.writerow(d)
        print(f"Saved CSV records to {args.csv}", file=sys.stderr)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report_data, f, indent=2)
        print(f"Saved JSON report to {args.output}", file=sys.stderr)

    if args.json:
        print(json.dumps(report_data, indent=2))
    elif not args.output and not args.csv:
        print(format_text_report(completed, unmatched, stats))


if __name__ == "__main__":
    main()
