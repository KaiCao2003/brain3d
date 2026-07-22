"""Integrity boundaries for pinned population-density acquisition and caching."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.vasculature import reference_store
from mouse_brain_planner.vasculature.reference_store import (
    PINNED_DENSITY_MEMBER_SHA256,
    PINNED_REFERENCE_DOWNLOAD_URL,
    PINNED_TEMPLATE_MEMBER_SHA256,
    PinnedArchiveMember,
    ReferenceDensityCacheError,
    _download_verified_archive,
    _hash_array_c_order,
    _source_manifest,
    _stream_archive_member,
    _validate_supported_atlas,
    _verify_regular_file,
)


def test_pinned_manifest_names_only_the_official_versioned_source_and_members() -> None:
    source = _source_manifest()

    assert source["doi"] == "10.17632/stxvn5sv44.1"
    assert source["downloadUrl"] == PINNED_REFERENCE_DOWNLOAD_URL
    assert source["archiveSizeBytes"] == 311_493_514
    assert source["archiveSha256"] == (
        "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
    )
    density = source["densityMember"]
    template = source["templateMember"]
    assert isinstance(density, dict)
    assert isinstance(template, dict)
    assert density["sha256"] == PINNED_DENSITY_MEMBER_SHA256
    assert template["sha256"] == PINNED_TEMPLATE_MEMBER_SHA256


def test_regular_file_boundary_rejects_wrong_hash_and_symlink(tmp_path: Path) -> None:
    payload = b"verified bytes"
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    _verify_regular_file(
        source,
        expected_size=len(payload),
        expected_sha256=digest,
        label="test source",
    )
    with pytest.raises(ReferenceDensityCacheError, match="SHA-256"):
        _verify_regular_file(
            source,
            expected_size=len(payload),
            expected_sha256="0" * 64,
            label="test source",
        )
    link = tmp_path / "link.bin"
    link.symlink_to(source)
    with pytest.raises(ReferenceDensityCacheError, match="not a symlink"):
        _verify_regular_file(
            link,
            expected_size=len(payload),
            expected_sha256=digest,
            label="test source",
        )


def test_controlled_extractor_streams_only_requested_member_and_checks_identity(
    tmp_path: Path,
) -> None:
    payload = b"one pinned member"
    executable = tmp_path / "fake-bsdtar"
    executable.write_text(
        "#!/bin/sh\nprintf 'one pinned member'\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    archive = tmp_path / "archive.7z"
    archive.write_bytes(b"test-only archive placeholder")
    member = PinnedArchiveMember(
        member_path="only/this/member.nii",
        cached_filename="member.nii",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        kind="density",
    )
    destination = tmp_path / "member.nii"

    _stream_archive_member(
        bsdtar_path=executable,
        archive=archive,
        member=member,
        destination=destination,
    )

    assert destination.read_bytes() == payload


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return PINNED_REFERENCE_DOWNLOAD_URL

    def read(self, size: int) -> bytes:
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_download_uses_only_pinned_url_and_installs_only_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"small exact archive test double"
    synthetic_source = replace(
        reference_store.STXVN5SV44_V1_SOURCE,
        archive_size_bytes=len(payload),
        archive_sha256=hashlib.sha256(payload).hexdigest(),
    )
    requested_urls: list[str] = []

    def fake_urlopen(request: Any, *, timeout: float) -> _Response:
        requested_urls.append(str(request.full_url))
        assert timeout == reference_store.DOWNLOAD_TIMEOUT_SECONDS
        return _Response(payload)

    monkeypatch.setattr(reference_store, "STXVN5SV44_V1_SOURCE", synthetic_source)
    monkeypatch.setattr(reference_store.urllib.request, "urlopen", fake_urlopen)
    destination = tmp_path / "cache" / "source.7z"

    _download_verified_archive(destination)

    assert requested_urls == [PINNED_REFERENCE_DOWNLOAD_URL]
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob(".vascular-download.*"))


def test_atlas_reference_digest_binds_dtype_shape_and_values() -> None:
    first = np.arange(24, dtype=np.uint16).reshape(2, 3, 4)
    same = first.copy()
    changed = first.copy()
    changed[0, 0, 0] = 99

    assert _hash_array_c_order(first) == _hash_array_c_order(same)
    assert _hash_array_c_order(first) != _hash_array_c_order(changed)
    assert _hash_array_c_order(first) != _hash_array_c_order(first.astype(np.uint32))


def test_store_accepts_only_exact_25um_atlas_contract() -> None:
    metadata = make_allen_metadata_test_double(25)
    reference = np.broadcast_to(
        np.zeros((1, 1, 1), dtype=np.uint16),
        metadata.shape_voxels,
    )

    _validate_supported_atlas(metadata, reference)

    with pytest.raises(ReferenceDensityCacheError, match="exact allen_mouse_25um"):
        _validate_supported_atlas(
            make_allen_metadata_test_double(10),
            np.zeros((1, 1, 1), dtype=np.uint16),
        )
