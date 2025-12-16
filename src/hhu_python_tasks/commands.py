from contextlib import chdir
import msgspec
import paramiko
from pathlib import Path
import shutil
import subprocess


class CommandResult(msgspec.Struct):
    ok: bool
    stdout: str
    stderr: str


class SshRunner:
    def __init__(self,
            hostname: str,
            remote_user: str | None = None,
            dry_run: bool = False,
            verbose: bool = False,
            ):
        if remote_user is None:
            if "@" in hostname:
                remote_user, hostname = hostname.split("@", 1)
        self.hostname = hostname
        self.remote_user = remote_user
        self.dry_run = dry_run
        self.verbose = verbose
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()
        client.connect(hostname, username=remote_user)
        self.client = client
    
    def run(self,
            args: list[str | Path],
            dry_run: bool = False,
            ) -> CommandResult:
        """Executes a command via SSH."""
        command = " ".join(str(a) for a in args)
        
        if self.dry_run or dry_run:
            if self.remote_user:
                remote = f"{self.remote_user}@{self.hostname}"
            else:
                remote = self.hostname
            print(f"would execute on {remote}: {command}")
            return CommandResult(ok=True, stdout="", stderr="")
        
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            ok = True
            if self.verbose:
                print(f"remote cmd OK: {command}")
        except paramiko.SSHException:
            ok = False
            if self.verbose:
                print(f"remote cmd failed: {command}")
        result = CommandResult(
                ok = ok,
                stdout = stdout.read().decode(),
                stderr = stderr.read().decode(),
                )
        return result
    
    def close(self) -> None:
        """Closes client connection; always call when finished."""
        self.client.close()
    
    def put(self,
            src: Path,
            dst: Path,
            dry_run: bool = False,
            ) -> None:
        """Copies a local file to a remote destination."""
        if dry_run or self.dry_run:
            print(f"would copy local file {src} to remote {dst}")
            return
        sftp = self.client.open_sftp()
        sftp.put(str(src), str(dst))
        if self.verbose:
            print(f"copied local file {src} to remote {dst}")
        sftp.close()
    
    def get(self,
            src: Path,
            dst: Path,
            dry_run: bool = False,
            ) -> None:
        """Copies a remote file to a local path."""
        if dry_run or self.dry_run:
            print(f"would copy remote file {src} to local {dst}")
            return
        sftp = self.client.open_sftp()
        sftp.get(str(src), str(dst), max_concurrent_prefetch_requests=64)
        if self.verbose:
            print(f"copied remote file {src} to local {dst}")
        sftp.close()
    
    def put_dir(self,
            src: Path,
            dst: Path,
            ref: Path | None,
            dry_run: bool = False,
            ) -> CommandResult:
        """Copies directory content to a remote destination."""
        args = ["rsync"]
        if self.verbose:
            args.append("-avxc")
        else:
            args.append("-axc")
#        if dry_run or self.dry_run:
#            args.append("--dry-run")
        args.append(f"{src}/")
        args.append(f"{self.remote_user}@{self.hostname}:{dst}/")
        if dry_run or self.dry_run:
            print(f"would execute locally: {' '.join(args)}")
            return CommandResult(ok=True, stdout="", stderr="")
        if ref is not None:
            args.append(f"--copy-dest={ref}/")
        r = subprocess.run(args, capture_output=True, encoding="utf-8")
        result = CommandResult(
                ok = r.returncode == 0,
                stdout = r.stdout,
                stderr = r.stderr,
                )
        if self.verbose:
            print(f"cmd result {r.returncode} from {' '.join(args)}")
        if not result.ok:
            print(f"cmd error: {result.stderr}")
            # XXX better error reporting needed
        return result


class LocalRunner:
    def __init__(self,
            directory: Path | None = None,
            dry_run: bool = False,
            verbose: bool = False,
            ) -> None:
        self.directory = directory or Path.cwd()
        self.dry_run = dry_run
        self.verbose = verbose
        self.closed = False
    
    def run(self,
            args: list[str | Path],
            dry_run: bool = False,
            ) -> CommandResult:
        """Executes a command locally."""
        if self.closed:
            raise ValueError("trying to use LocalRunner after close()")
        str_args = [str(a) for a in args]
        if self.dry_run or dry_run:
            command = " ".join(str_args)
            print(f"would execute locally: {command}")
            return CommandResult(ok=True, stdout="", stderr="")
        
        with chdir(self.directory):
            r = subprocess.run(str_args, capture_output=True, encoding="utf-8")
        result = CommandResult(
                ok = r.returncode == 0,
                stdout = r.stdout,
                stderr = r.stderr,
                )
        if self.verbose:
            print(f"cmd result {r.returncode} from {' '.join(str_args)}")
        if not result.ok:
            print(f"cmd error: {result.stderr}")
            # XXX better error reporting needed
        return result
    
    def close(self) -> None:
        """Closes command client; currently a nop."""
        self.closed = True
    
    def put(self,
            src: Path,
            dst: Path,
            dry_run: bool = False,
            ) -> None:
        """Copies a file to a destination relative to self.directory."""
        if dst.is_absolute():
            real_dst = dst
        else:
            real_dst = self.directory / dst
        if dry_run or self.dry_run:
            print(f"would copy {src} to {real_dst}")
            return
        shutil.copy2(src, real_dst)
        if self.verbose:
            print(f"copied {src} to {real_dst}")
    
    def get(self,
            src: Path,
            dst: Path,
            dry_run: bool = False,
            ) -> None:
        """Copies a file from a location relative to self.directory."""
        if src.is_absolute():
            real_src = src
        else:
            real_src = self.directory / src
        if dry_run or self.dry_run:
            print(f"would copy {real_src} to {dst}")
            return
        shutil.copy2(real_src, dst)
        if self.verbose:
            print(f"copied {real_src} to {dst}")
    
    def put_dir(self,
            src: Path,
            dst: Path,
            ref: Path | None,
            dry_run: bool = False,
            ) -> CommandResult:
        """Copies directory content to a remote destination."""
        args = ["cp", "-R"]
        if self.verbose:
            args.append("-v")
        args.append(f"{src}/")
        args.append(f"{dst.parent}/")
        if dry_run or self.dry_run:
            print(f"would run {' '.join(args)}")
            return CommandResult(ok=True, stdout="", stderr="")
        r = subprocess.run(args, capture_output=True, encoding="utf-8")
        result = CommandResult(
                ok = r.returncode == 0,
                stdout = r.stdout,
                stderr = r.stderr,
                )
        if self.verbose:
            print(f"cmd result {r.returncode} from {' '.join(args)}")
        if not result.ok:
            print(f"cmd error: {result.stderr}")
            # XXX better error reporting needed
        return result


def get_command_runner(
        hostname: str | None,
        remote_user: str | None,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> LocalRunner | SshRunner:
    if not hostname:
        return LocalRunner(dry_run=dry_run, verbose=verbose)
    return SshRunner(hostname=hostname, remote_user=remote_user,
            dry_run=dry_run, verbose=verbose)
