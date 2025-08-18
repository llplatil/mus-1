from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
import subprocess
import sys
import shlex
import threading
import time

from pathlib import Path

from .metadata import WorkerEntry
from .logging_bus import LoggingEventBus


@dataclass
class JobResult:
    """Result of a remote job execution."""
    return_code: int
    stdout: str
    stderr: str


class SshJobProvider:
    """Minimal SSH job provider.

    Executes commands on a remote host referenced by an SSH config alias.
    """

    def __init__(self, connect_timeout_seconds: int = 10, batch_mode: bool = True) -> None:
        self.connect_timeout_seconds = connect_timeout_seconds
        self.batch_mode = batch_mode

    def run(
        self,
        ssh_alias: str,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        allocate_tty: bool = False,
        stream_output: bool = False,
        log_prefix: Optional[str] = None,
    ) -> JobResult:
        """Run a command over SSH using the provided alias.

        Args:
            ssh_alias: Host alias configured in ~/.ssh/config
            command: Command vector to execute remotely

        Returns:
            JobResult with exit code and captured output
        """
        ssh_cmd: List[str] = [
            "ssh",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
        ]
        if self.batch_mode:
            ssh_cmd += ["-o", "BatchMode=yes"]
        if allocate_tty:
            ssh_cmd += ["-tt"]
        # Build remote shell command string with optional cwd/env, run under bash -lc
        env_prefix = ""
        if env:
            pairs = [f"{k}={shlex.quote(v)}" for k, v in env.items()]
            env_prefix = " ".join(pairs) + " "
        cmd_quoted = " ".join(shlex.quote(part) for part in command)
        if cwd:
            remote_sh = f"cd {shlex.quote(str(cwd))} && {env_prefix}{cmd_quoted}"
        else:
            remote_sh = f"{env_prefix}{cmd_quoted}"
        remote_cmd = ["bash", "-lc", remote_sh]

        full_cmd = ssh_cmd + [ssh_alias] + remote_cmd

        if not stream_output:
            proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return JobResult(proc.returncode, proc.stdout or "", proc.stderr or "")

        # Streaming mode
        bus = LoggingEventBus.get_instance()
        proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

        collected_stdout: List[str] = []
        collected_stderr: List[str] = []

        def _pump(stream, is_err: bool):
            for line in iter(stream.readline, ''):
                if is_err:
                    collected_stderr.append(line)
                    sys.stderr.write(line)
                    bus.log(line.rstrip('\n'), "error", log_prefix or "JobProvider")
                else:
                    collected_stdout.append(line)
                    sys.stdout.write(line)
                    bus.log(line.rstrip('\n'), "info", log_prefix or "JobProvider")
            stream.close()

        threads = []
        if proc.stdout:
            t_out = threading.Thread(target=_pump, args=(proc.stdout, False), daemon=True)
            threads.append(t_out)
            t_out.start()
        if proc.stderr:
            t_err = threading.Thread(target=_pump, args=(proc.stderr, True), daemon=True)
            threads.append(t_err)
            t_err.start()

        start_time = time.monotonic()
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                proc.kill()
                ret = proc.wait()
                collected_stderr.append("Process killed due to timeout\n")
                sys.stderr.write("Process killed due to timeout\n")
                bus.log("Process killed due to timeout", "error", log_prefix or "JobProvider")
                break
            time.sleep(0.05)

        for t in threads:
            t.join(timeout=1)

        return JobResult(ret or 0, "".join(collected_stdout), "".join(collected_stderr))


class WslJobProvider:
    """Minimal WSL job provider (local Windows).

    Executes commands inside the default WSL distribution using bash -lc.
    """

    def run(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        stream_output: bool = False,
        log_prefix: Optional[str] = None,
    ) -> JobResult:
        if sys.platform != "win32":
            raise ValueError("WSL provider is only available on Windows hosts")

        env_prefix = ""
        if env:
            pairs = [f"{k}={shlex.quote(v)}" for k, v in env.items()]
            env_prefix = " ".join(pairs) + " "
        cmd_quoted = " ".join(shlex.quote(part) for part in command)
        if cwd:
            shell_cmd = f"cd {shlex.quote(str(cwd))} && {env_prefix}{cmd_quoted}"
        else:
            shell_cmd = f"{env_prefix}{cmd_quoted}"

        full_cmd = ["wsl.exe", "-e", "bash", "-lc", shell_cmd]

        if not stream_output:
            proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return JobResult(proc.returncode, proc.stdout or "", proc.stderr or "")

        bus = LoggingEventBus.get_instance()
        proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

        collected_stdout: List[str] = []
        collected_stderr: List[str] = []

        def _pump(stream, is_err: bool):
            for line in iter(stream.readline, ''):
                if is_err:
                    collected_stderr.append(line)
                    sys.stderr.write(line)
                    bus.log(line.rstrip('\n'), "error", log_prefix or "JobProvider")
                else:
                    collected_stdout.append(line)
                    sys.stdout.write(line)
                    bus.log(line.rstrip('\n'), "info", log_prefix or "JobProvider")
            stream.close()

        threads = []
        if proc.stdout:
            t_out = threading.Thread(target=_pump, args=(proc.stdout, False), daemon=True)
            threads.append(t_out)
            t_out.start()
        if proc.stderr:
            t_err = threading.Thread(target=_pump, args=(proc.stderr, True), daemon=True)
            threads.append(t_err)
            t_err.start()

        start_time = time.monotonic()
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            if timeout is not None and (time.monotonic() - start_time) > timeout:
                proc.kill()
                ret = proc.wait()
                collected_stderr.append("Process killed due to timeout\n")
                sys.stderr.write("Process killed due to timeout\n")
                bus.log("Process killed due to timeout", "error", log_prefix or "JobProvider")
                break
            time.sleep(0.05)

        for t in threads:
            t.join(timeout=1)

        return JobResult(ret or 0, "".join(collected_stdout), "".join(collected_stderr))


class LocalJobProvider:
    """Run a command locally on the current host (POSIX shells)."""

    def run(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        stream_output: bool = False,
        log_prefix: Optional[str] = None,
    ) -> JobResult:
        full_env = None
        if env:
            full_env = {**dict(**{}), **env}
        if not stream_output:
            proc = subprocess.run(command, cwd=str(cwd) if cwd else None, env=full_env, capture_output=True, text=True, timeout=timeout)
            return JobResult(proc.returncode, proc.stdout or "", proc.stderr or "")
        bus = LoggingEventBus.get_instance()
        proc = subprocess.Popen(command, cwd=str(cwd) if cwd else None, env=full_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        collected_stdout: List[str] = []
        collected_stderr: List[str] = []
        def _pump(stream, is_err: bool):
            for line in iter(stream.readline, ''):
                if is_err:
                    collected_stderr.append(line)
                    sys.stderr.write(line)
                    bus.log(line.rstrip('\n'), "error", log_prefix or "JobProvider")
                else:
                    collected_stdout.append(line)
                    sys.stdout.write(line)
                    bus.log(line.rstrip('\n'), "info", log_prefix or "JobProvider")
            stream.close()
        threads = []
        if proc.stdout:
            t_out = threading.Thread(target=_pump, args=(proc.stdout, False), daemon=True)
            threads.append(t_out)
            t_out.start()
        if proc.stderr:
            t_err = threading.Thread(target=_pump, args=(proc.stderr, True), daemon=True)
            threads.append(t_err)
            t_err.start()
        ret = proc.wait(timeout=timeout)
        for t in threads:
            t.join(timeout=1)
        return JobResult(ret or 0, "".join(collected_stdout), "".join(collected_stderr))


class SshWslJobProvider:
    """Run a command on a Windows host's default WSL via SSH.

    This composes ssh alias with a remote invocation of wsl.exe -e bash -lc "cd ... && env ... command".
    """

    def __init__(self, connect_timeout_seconds: int = 10, batch_mode: bool = True) -> None:
        self.connect_timeout_seconds = connect_timeout_seconds
        self.batch_mode = batch_mode

    def run(
        self,
        ssh_alias: str,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        stream_output: bool = False,
        log_prefix: Optional[str] = None,
    ) -> JobResult:
        ssh_cmd: List[str] = [
            "ssh",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
        ]
        if self.batch_mode:
            ssh_cmd += ["-o", "BatchMode=yes"]

        env_prefix = ""
        if env:
            pairs = [f"{k}={shlex.quote(v)}" for k, v in env.items()]
            env_prefix = " ".join(pairs) + " "
        cmd_quoted = " ".join(shlex.quote(part) for part in command)
        if cwd:
            shell_cmd = f"cd {shlex.quote(str(cwd))} && {env_prefix}{cmd_quoted}"
        else:
            shell_cmd = f"{env_prefix}{cmd_quoted}"

        remote_cmd = ["wsl.exe", "-e", "bash", "-lc", shell_cmd]
        full_cmd = ssh_cmd + [ssh_alias] + remote_cmd

        if not stream_output:
            proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return JobResult(proc.returncode, proc.stdout or "", proc.stderr or "")

        bus = LoggingEventBus.get_instance()
        proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        collected_stdout: List[str] = []
        collected_stderr: List[str] = []
        def _pump(stream, is_err: bool):
            for line in iter(stream.readline, ''):
                if is_err:
                    collected_stderr.append(line)
                    sys.stderr.write(line)
                    bus.log(line.rstrip('\n'), "error", log_prefix or "JobProvider")
                else:
                    collected_stdout.append(line)
                    sys.stdout.write(line)
                    bus.log(line.rstrip('\n'), "info", log_prefix or "JobProvider")
            stream.close()
        threads = []
        if proc.stdout:
            t_out = threading.Thread(target=_pump, args=(proc.stdout, False), daemon=True)
            threads.append(t_out)
            t_out.start()
        if proc.stderr:
            t_err = threading.Thread(target=_pump, args=(proc.stderr, True), daemon=True)
            threads.append(t_err)
            t_err.start()
        ret = proc.wait(timeout=timeout)
        for t in threads:
            t.join(timeout=1)
        return JobResult(ret or 0, "".join(collected_stdout), "".join(collected_stderr))


def run_on_worker(
    worker: WorkerEntry,
    command: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    allocate_tty: bool = False,
    stream_output: bool = True,
    log_prefix: Optional[str] = None,
) -> JobResult:
    """Execute a command on the given worker using its provider (ssh|wsl|local|ssh-wsl)."""
    if worker.provider == "ssh":
        provider = SshJobProvider()
        return provider.run(
            worker.ssh_alias,
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            allocate_tty=allocate_tty,
            stream_output=stream_output,
            log_prefix=log_prefix,
        )
    if worker.provider == "wsl":  # local WSL on Windows host
        provider_wsl = WslJobProvider()
        return provider_wsl.run(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            stream_output=stream_output,
            log_prefix=log_prefix,
        )
    if worker.provider == "local":
        provider_local = LocalJobProvider()
        return provider_local.run(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            stream_output=stream_output,
            log_prefix=log_prefix,
        )
    if worker.provider == "ssh-wsl":
        provider_sws = SshWslJobProvider()
        return provider_sws.run(
            worker.ssh_alias,
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
            stream_output=stream_output,
            log_prefix=log_prefix,
        )
    raise ValueError(f"Unsupported provider '{worker.provider}'. Supported: ssh, wsl")


