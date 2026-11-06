"""Seed script for demo workspace with realistic fictional customer."""
"""Seed the demo workspace with a realistic fictional customer profile and ICP.

All data is intentionally synthetic and labelled as such in the UI.
"""

import argparse
import uuid
from pathlib import Path
from datetime import datetime, timezone

from app.core.database import SessionLocal, Engine as engine, Base
from app.models import Workspace, ClientProfile, ICPProfile
import app.models  # noqa: F401  # register all models with Base.metadata
from app.config import settings
from app.schemas.workspace import WorkspaceCreate
from app.schemas.client_profile import ClientProfileCreate
from app.schemas.icp_profile import ICPProfileCreate


def ensure_db_dir():
    db_path = Path(settings().database_url.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)


def reset_db():
    ensure_db_dir()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_demo_workspace(db):
    workspace = Workspace(
        slug="demo",
        name="Demo Workspace",
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def create_demo_client_profile(db, workspace):
    profile = ClientProfile(
        workspace_id=workspace.id,
        name="Northbridge Growth Partners",
        website="https://www.northbridgegp.com",
        description=(
            "Northbridge Growth Partners is a B2B growth consultancy helping mid-market "
            "technology and professional services companies accelerate pipeline generation "
            "through data-driven outbound prospecting and personalized engagement."
        ),
        products_services=(
            "Data-driven outbound prospecting, ICP definition, account research, "
            "personalized cold outreach, email and LinkedIn engagement, appointment setting."
        ),
        value_proposition=(
            "Northbridge replaces generic lead lists with researched, relevant prospects and "
            "personalized outreach that starts real conversations with decision-makers."
        ),
        target_audience=(
            "B2B technology companies, professional services firms, and consultancies with "
            "50-500 employees seeking to expand their pipeline."
        ),
        problems_solved=(
            "Poor lead quality, generic outreach that gets ignored, lack of account research, "
            "difficulty identifying the right decision-makers, low engagement rates."
        ),
        usp=(
            "Northbridge combines AI-assisted research with human judgment to deliver prospects "
            "with a clear business problem and a specific reason to engage."
        ),
        is_active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def create_demo_icp(db, workspace, client_profile):
    icp = ICPProfile(
        workspace_id=workspace.id,
        client_profile_id=client_profile.id,
        name="Mid-Market Tech & Professional Services Decision-Makers",
        target_industries="Technology,Professional Services,Consulting,Software",
        sub_industries="SaaS,IT Services,Business Consulting,Management Consulting,Marketing Services",
        target_countries="United States,United Kingdom,Canada",
        target_regions="North America,Western Europe",
        company_size="Medium",
        employee_count_min=50,
        employee_count_max=500,
        revenue_min="$1M",
        revenue_max="$50M",
        preferred_company_types="Private,Bootstrapped,Series A-C",
        target_audience="B2B technology and professional services companies",
        decision_maker_roles="Founder,CEO,Owner,Managing Director,Head of Sales,VP Sales,Head of Business Development",
        additional_criteria="Active outbound sales motion, publicly visible leadership, relevant public digital footprint",
        max_prospects=20,
        is_active=True,
    )
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return icp


def seed():
    ensure_db_dir()
    db = SessionLocal()
    try:
        reset_db()
        workspace = create_demo_workspace(db)
        client_profile = create_demo_client_profile(db, workspace)
        icp = create_demo_icp(db, workspace, client_profile)
        print(f"Seeded workspace: {workspace.slug}")
        print(f"Client profile: {client_profile.name} ({client_profile.id})")
        print(f"ICP: {icp.name} ({icp.id})")
        print("Demo workspace ready.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset database before seeding")
    args = parser.parse_args()
    seed()
