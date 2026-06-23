"""
Documents endpoint tests.
"""
import io
import uuid
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.facility import Facility
from app.models.user import User


class TestDocumentsList:
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get("/api/v1/documents", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["documents"] == []

    async def test_list_filters_by_org(
        self, client: AsyncClient, auth_headers: dict,
        other_auth_headers: dict, facility: Facility,
    ):
        with (
            patch("aiofiles.open", MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(write=AsyncMock())), __aexit__=AsyncMock()))),
            patch("pathlib.Path.mkdir"),
        ):
            resp = await client.post(
                "/api/v1/documents",
                headers=auth_headers,
                data={"document_type": "permit", "facility_id": str(facility.id)},
                files={"file": ("test.pdf", io.BytesIO(b"pdf content"), "application/pdf")},
            )
        assert resp.status_code == 201

        resp2 = await client.get("/api/v1/documents", headers=other_auth_headers)
        assert resp2.json()["total"] == 0


class TestDocumentUpload:
    async def test_upload_success(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        with (
            patch("aiofiles.open", MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(write=AsyncMock())), __aexit__=AsyncMock()))),
            patch("pathlib.Path.mkdir"),
        ):
            resp = await client.post(
                "/api/v1/documents",
                headers=auth_headers,
                data={"document_type": "utility_bill", "name": "Jan 2026", "facility_id": str(facility.id)},
                files={"file": ("january.pdf", io.BytesIO(b"bill data"), "application/pdf")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["document_type"] == "utility_bill"
        assert data["name"] == "Jan 2026"
        assert data["content_type"] == "application/pdf"
        assert data["size_bytes"] == len(b"bill data")
        assert data["facility_id"] == str(facility.id)

    async def test_upload_invalid_type(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            "/api/v1/documents",
            headers=auth_headers,
            data={"document_type": "garbage_type"},
            files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
        )
        assert resp.status_code == 422

    async def test_upload_unknown_facility(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/documents",
            headers=auth_headers,
            data={"document_type": "permit", "facility_id": str(uuid.uuid4())},
            files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
        )
        assert resp.status_code == 404

    async def test_upload_unauthenticated(self, client: AsyncClient, facility: Facility):
        resp = await client.post(
            "/api/v1/documents",
            data={"document_type": "permit"},
            files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
        )
        assert resp.status_code == 401


class TestDocumentDelete:
    async def test_delete_success(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        with (
            patch("aiofiles.open", MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(write=AsyncMock())), __aexit__=AsyncMock()))),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            create_resp = await client.post(
                "/api/v1/documents",
                headers=auth_headers,
                data={"document_type": "permit", "facility_id": str(facility.id)},
                files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
            )
        doc_id = create_resp.json()["id"]

        with patch("pathlib.Path.exists", return_value=False):
            del_resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
        assert del_resp.status_code == 204

    async def test_delete_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete(f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_cross_org_blocked(
        self, client: AsyncClient, auth_headers: dict,
        other_auth_headers: dict, facility: Facility,
    ):
        with (
            patch("aiofiles.open", MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(write=AsyncMock())), __aexit__=AsyncMock()))),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            create_resp = await client.post(
                "/api/v1/documents",
                headers=auth_headers,
                data={"document_type": "permit", "facility_id": str(facility.id)},
                files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
            )
        doc_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=other_auth_headers)
        assert resp.status_code == 404
