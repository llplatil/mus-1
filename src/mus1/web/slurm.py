from __future__ import annotations

from typing import Dict, List

import streamlit as st

from .utils import run_cmd


@st.cache_data(show_spinner=False, ttl=20)
def squeue(user: str) -> List[Dict[str, str]]:
    """
    Return a table of active jobs for the given user.
    """
    # Use a parsable format to avoid brittle whitespace parsing.
    fmt = "%i|%P|%j|%u|%T|%M|%D|%R"
    code, out, err = run_cmd(["squeue", "-u", str(user), "-h", "-o", fmt])
    if code != 0:
        return [
            {
                "jobid": "",
                "partition": "",
                "name": "",
                "user": str(user),
                "state": "ERROR",
                "time": "",
                "nodes": "",
                "reason": err or out,
            }
        ]
    rows = []
    for line in (out.splitlines() if out else []):
        parts = line.split("|")
        if len(parts) != 8:
            continue
        rows.append(
            {
                "jobid": parts[0],
                "partition": parts[1],
                "name": parts[2],
                "user": parts[3],
                "state": parts[4],
                "time": parts[5],
                "nodes": parts[6],
                "nodelist_reason": parts[7],
            }
        )
    return rows


@st.cache_data(show_spinner=False, ttl=60)
def sacct(jobid: str) -> str:
    code, out, err = run_cmd(
        [
            "sacct",
            "-j",
            str(jobid),
            "--format=JobID,JobName%25,Partition,State,Elapsed,Timelimit,AllocCPUS,NodeList%25,ExitCode,MaxRSS",
            "-n",
        ]
    )
    if code != 0:
        return err or out
    return out


@st.cache_data(show_spinner=False, ttl=20)
def sstat(jobid: str) -> str:
    # Often only meaningful while running.
    code, out, err = run_cmd(
        [
            "sstat",
            "-j",
            f"{jobid}.batch",
            "--format=JobID,AveCPU,MaxRSS,AveRSS,MaxVMSize",
            "-n",
        ]
    )
    if code != 0:
        return err or out
    return out


@st.cache_data(show_spinner=False, ttl=60)
def scontrol_node(node: str) -> str:
    code, out, err = run_cmd(["scontrol", "show", "node", "-o", str(node)])
    if code != 0:
        return err or out
    return out

