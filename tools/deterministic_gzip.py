#!/usr/bin/env python3
"""Gzip writers whose output bytes depend only on their content.

`gzip.open` stamps the file's creation time into the gzip header and stores the output filename. Two runs
over identical input therefore produce different bytes, which breaks any published sha256 of a gzipped
artifact and makes "reproducible" mean "reproducible content, non-reproducible file". Every gzipped artifact
this project ships is written through `gzip_text_writer` so a reader can hash it and get the same value on
their own machine after their own re-run.
"""
from __future__ import annotations

import contextlib
import gzip
import io


@contextlib.contextmanager
def gzip_text_writer(path, compresslevel: int = 9):
    raw = open(path, "wb")
    stream = None
    try:
        handle = gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=compresslevel, mtime=0)
        stream = io.TextIOWrapper(handle, encoding="utf-8", newline="")
        yield stream
    finally:
        if stream is not None:
            stream.close()  # closes the GzipFile and writes its trailer
        raw.close()
