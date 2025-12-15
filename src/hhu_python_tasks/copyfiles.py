#! /usr/bin/env python3

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
import shutil
import sys
import threading


@dataclass
class CopyResult:
    file: Path
    error: None | Exception = None


class FileCopy(threading.Thread):
    def __init__(self,
            work_queue: Queue,
            source: Path,
            destination: Path,
            *,
            name: str,
            ):
        super().__init__(name=name)
        self.queue = work_queue
        self.source = source
        self.destination = destination

    def run(self) -> None:
        result = CopyResult(file=self.source)
        try:
            shutil.copy2(self.source, self.destination)
        except IOError as e:
            result.error = e
        self.queue.put(result)


def copy_files(
        destination: Path,
        files: list[Path],
        clean: bool = False,
        ) -> list[CopyResult]:
    """Copies a number of files to a destination directory in separate threads."""
    if clean:
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    
    copy_results: list[CopyResult] = []
    work_queue: Queue[CopyResult] = Queue()
    thlist: list[FileCopy] = []
    for src in files:
        th = FileCopy(work_queue, src, destination, name=src.name)
        th.start()
        thlist.append(th)
    
    for th in thlist:
        th.join()
    
    while True:
        try:
            result = work_queue.get(block=False)
        except Empty:
            break
        copy_results.append(result)
    
    return copy_results


def _test() -> None:
    results = copy_files(
            Path(sys.argv[1]),
            [Path(arg) for arg in sys.argv[2:]],
            )
    for result in results:
        if result.error is None:
            print(f"copied {result.file}")
        else:
            print(f"file {result.file}: error {result.error}")


if __name__ == "__main__":
    _test()
