"""Tests for the /api/brand endpoint."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, BRAND_PATH

client = TestClient(app)

BRAND_FIXTURE = {
    "companyName": "Byoc FastAPI Alembic r5c",
    "tagline": "Byoc FastAPI Alembic r5c runs on Orkosi from its own code",
    "description": "Byoc FastAPI Alembic r5c is brought to Orkosi as its own code and run as it is: every part detected, placed and deployed without a remake.",
    "targetAudience": "saas",
    "industry": "technology",
    "logo": {"type": "text", "mark": "BFA"},
    "pricing": {
        "tiers": [
            {
                "name": "Free",
                "price": "$0",
                "period": "/month",
                "features": [
                    "Basic code detection",
                    "Standard deployment pipeline",
                    "Community support",
                ],
            },
            {
                "name": "Pro",
                "price": "$49",
                "period": "/month",
                "features": [
                    "Everything in Free",
                    "Priority deployment",
                    "Advanced detection rules",
                    "Dedicated support",
                ],
            },
        ]
    },
}


@pytest.fixture
def brand_file(tmp_path, monkeypatch):
    """Write a temporary brand.json and point BRAND_PATH at it."""
    brand_path = tmp_path / "brand.json"
    brand_path.write_text(json.dumps(BRAND_FIXTURE))
    monkeypatch.setattr("app.main.BRAND_PATH", brand_path)
    return brand_path


def test_get_brand_returns_brand_json(brand_file):
    """The endpoint returns the contents of brand.json."""
    response = client.get("/api/brand")
    assert response.status_code == 200
    data = response.json()
    assert data["companyName"] == "Byoc FastAPI Alembic r5c"
    assert "tagline" in data
    assert "pricing" in data


def test_get_brand_returns_fallback_when_no_file(monkeypatch, tmp_path):
    """When brand.json is missing, a minimal fallback is returned."""
    missing = tmp_path / "nonexistent.json"
    monkeypatch.setattr("app.main.BRAND_PATH", missing)
    response = client.get("/api/brand")
    assert response.status_code == 200
    data = response.json()
    assert data["companyName"] == "Byoc FastAPI Alembic r5c"


def test_get_brand_pricing_structure(brand_file):
    """The pricing block has the expected shape."""
    response = client.get("/api/brand")
    assert response.status_code == 200
    data = response.json()
    tiers = data["pricing"]["tiers"]
    assert len(tiers) == 2
    assert tiers[0]["name"] == "Free"
    assert tiers[0]["price"] == "$0"
    assert tiers[1]["name"] == "Pro"
    assert tiers[1]["price"] == "$49"