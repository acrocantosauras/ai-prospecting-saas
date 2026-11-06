"""Demo provider - deterministic synthetic data for local demos.

All records are clearly labelled synthetic. This provider is always available
and is used when AI_PROVIDER=demo or when no real credentials are configured.

IMPORTANT: These must never be presented as real companies or real contacts.
"""

import hashlib
import random
import uuid
from typing import Any

from app.providers.base import (
    CompanyDiscoveryProvider,
    CompanyResearchProvider,
    DecisionMakerDiscoveryProvider,
    ContactEnrichmentProvider,
    EmailVerificationProvider,
    AIAnalysisProvider,
)


def _seed(icp: dict[str, Any], index: int) -> int:
    """Deterministic seed derived from ICP + index."""
    key = f"{icp.get('target_industries')}-{icp.get('target_countries')}-{index}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)


class DemoProvider(
    CompanyDiscoveryProvider,
    CompanyResearchProvider,
    DecisionMakerDiscoveryProvider,
    ContactEnrichmentProvider,
    EmailVerificationProvider,
    AIAnalysisProvider,
):
    """Deterministic demo provider returning clearly labelled synthetic records."""

    def discover(self, icp: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        """Discover synthetic companies matching the ICP."""
        limit = min(limit, 100)
        industries = self._parse_list(icp.get("target_industries") or "Technology,Professional Services,Healthcare")
        countries = self._parse_list(icp.get("target_countries") or "United States,United Kingdom,Canada")
        rng = random.Random(_seed(icp, 0))
        companies = []
        seen = set()
        for i in range(limit * 2):
            if len(companies) >= limit:
                break
            seed = _seed(icp, i)
            local_rng = random.Random(seed)
            industry = industries[i % len(industries)] if industries else "Technology"
            country = countries[i % len(countries)] if countries else "United States"
            name = self._synthetic_company_name(seed, industry, country)
            if name in seen:
                continue
            seen.add(name)
            company = {
                "name": name,
                "website": self._synthetic_website(name),
                "industry": industry,
                "location": self._synthetic_location(country, local_rng),
                "country": country,
                "city": self._synthetic_city(country, local_rng),
                "description": self._synthetic_company_description(name, industry, country, local_rng),
                "products_services": self._synthetic_products(industry, local_rng),
                "company_size": self._synthetic_size(local_rng),
                "employee_count": self._synthetic_employee_count(local_rng),
                "revenue": self._synthetic_revenue(local_rng),
                # No fabricated profile or source URLs: a synthetic company has
                # no real LinkedIn/Instagram page, so these stay empty.
                "linkedin_url": None,
                "instagram_url": None,
                "source_url": None,
                "source_name": "Synthetic Demo Provider",
                "synthetic": True,
            }
            companies.append(company)
        return companies

    def research(self, company: dict[str, Any]) -> dict[str, Any]:
        """Produce synthetic research grounded in the synthetic company record."""
        research = {
            "what_it_does": self._synthetic_what_it_does(company),
            "what_it_sells": company.get("products_services"),
            "who_it_serves": self._synthetic_who_it_serves(company),
            "positioning": self._synthetic_positioning(company),
            "public_developments": self._synthetic_public_developments(company),
            "observable_challenges": self._synthetic_challenges(company),
            "research_confidence": "low (synthetic demo)",
            # Synthetic research has no citable sources.
            "source_urls": [],
            "source_notes": "Synthetic demo records - do not treat as verified facts.",
            "synthetic": True,
        }
        return research

    def discover_decision_makers(self, company: dict[str, Any], icp: dict[str, Any]) -> list[dict[str, Any]]:
        """Return synthetic decision-makers for the synthetic company."""
        seed = _seed({**icp, "company": company.get("name")}, 0)
        rng = random.Random(seed)
        roles = self._parse_list(icp.get("decision_maker_roles") or "Founder,CEO,Owner,Managing Director,Head of Sales")
        names = self._synthetic_dm_names(seed, len(roles), rng)
        decision_makers = []
        for idx, role in enumerate(roles[:3]):
            dm_name = names[idx] if idx < len(names) else self._synthetic_dm_name(seed + idx, rng)
            first, last = self._split_dm_name(dm_name)
            dm = {
                "first_name": first,
                "last_name": last,
                "full_name": dm_name,
                "job_title": role,
                "company": company.get("name"),
                "professional_profile_url": None,
                "profile_source": "Synthetic Demo Provider",
                "public_contact_details": None,
                "synthetic": True,
            }
            decision_makers.append(dm)
        return decision_makers

    def enrich(self, prospect: dict[str, Any]) -> dict[str, Any]:
        """Return synthetic enrichment with honest missing/unavailable statuses."""
        email = prospect.get("email")
        if email:
            verification = self.verify(email)
            email_status = verification.get("status")
        else:
            email_status = "unavailable"
        enrichment = {
            "email": email,
            "email_status": email_status,
            "email_confidence": self._email_confidence(email_status),
            "linkedin_url": prospect.get("linkedin_url"),
            "instagram_url": prospect.get("instagram_url"),
            "other_profiles": None,
            "raw_response": "Synthetic demo enrichment - no external provider used.",
            "fetched_at": None,
            "synthetic": True,
        }
        return enrichment

    def verify(self, email: str) -> dict[str, Any]:
        """Deterministic synthetic email verification with realistic statuses."""
        if not email or "@" not in email:
            return {"status": "unavailable", "details": "No email provided", "synthetic": True}
        status = self._synthetic_verification_status(email)
        return {
            "status": status,
            "details": self._verification_details(status),
            "synthetic": True,
        }

    def analyze(self, prompt: str, schema: type, system: str | None = None) -> Any:
        """Return synthetic AI output that satisfies the schema without a real model.

        This is a fallback for when no AI provider is configured. It should be
        replaced by a real provider in production.
        """
        from pydantic import create_model, BaseModel

        if schema is str:
            return prompt[:200] + " [SYNTHETIC DEMO RESPONSE]"
        if issubclass(schema, BaseModel):
            instance = schema.model_construct(**self._synthetic_ai_fill(schema))
            return instance
        return {"synthetic": True, "note": "Demo provider returned synthetic analysis."}

    def _synthetic_ai_fill(self, schema: type) -> dict[str, Any]:
        """Fill a Pydantic schema with synthetic values for required fields."""
        from pydantic import BaseModel

        if not issubclass(schema, BaseModel):
            return {}
        fields: dict[str, Any] = {}
        for name, field_info in schema.model_fields.items():
            if name in fields:
                continue
            if field_info.annotation is str:
                fields[name] = f"[Synthetic demo] {name} placeholder"
            elif field_info.annotation is int:
                fields[name] = 0
            elif field_info.annotation is float:
                fields[name] = 0.0
            elif field_info.annotation is bool:
                fields[name] = False
            else:
                fields[name] = None
        return fields

    # ---- helpers ----

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]

    @staticmethod
    def _synthetic_company_name(seed: int, industry: str, country: str) -> str:
        rng = random.Random(seed)
        prefixes = ["North", "Blue", "Swift", "Bright", "Prime", "Green", "Apex", "Core", "Nova", "Clear"]
        middles = ["Bridge", "Stone", "Valley", "Peak", "Point", "Line", "Wave", "Grid", "Point", "Edge"]
        suffixes = ["Group", "Labs", "Partners", "Solutions", "Systems", "Corp", "Co", "Holdings", "Ventures", "Studio"]
        return f"{rng.choice(prefixes)} {rng.choice(middles)} {rng.choice(suffixes)}"

    @staticmethod
    def _synthetic_website(name: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return f"https://www.{slug}.com"

    @staticmethod
    def _synthetic_location(country: str, rng: random.Random) -> str:
        city = rng.choice(["New York", "London", "Toronto", "Sydney", "Berlin", "Austin", "Chicago", "San Francisco"])
        region_map = {
            "United States": "United States",
            "United Kingdom": "United Kingdom",
            "Canada": "Canada",
        }
        return f"{city}, {region_map.get(country, country)}"

    @staticmethod
    def _synthetic_city(country: str, rng: random.Random) -> str:
        cities = {
            "United States": ["New York", "Austin", "Chicago", "San Francisco", "Boston"],
            "United Kingdom": ["London", "Manchester", "Birmingham", "Edinburgh"],
            "Canada": ["Toronto", "Vancouver", "Montreal", "Calgary"],
        }
        return rng.choice(cities.get(country, ["City"]))

    @staticmethod
    def _synthetic_company_description(name: str, industry: str, country: str, rng: random.Random) -> str:
        return (
            f"{name} is a {industry.lower()} company based in {country} providing "
            f"{rng.choice(['specialised', 'innovative', 'trusted', 'established'])} solutions "
            f"to businesses in the sector."
        )

    @staticmethod
    def _synthetic_products(industry: str, rng: random.Random) -> str:
        product_sets = {
            "Technology": "SaaS platforms, cloud infrastructure, data analytics tools",
            "Professional Services": "Consulting, audit, tax advisory, business transformation",
            "Healthcare": "Medical devices, digital health platforms, clinical services",
            "Manufacturing": "Industrial equipment, components, supply chain services",
            "Retail": "E-commerce platforms, retail analytics, omnichannel solutions",
        }
        return product_sets.get(industry, "B2B services and products")

    @staticmethod
    def _synthetic_size(rng: random.Random) -> str:
        return rng.choice(["Small", "Medium", "Large", "Enterprise"])

    @staticmethod
    def _synthetic_employee_count(rng: random.Random) -> str:
        ranges = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]
        return rng.choice(ranges)

    @staticmethod
    def _synthetic_revenue(rng: random.Random) -> str:
        ranges = ["< $1M", "$1M-$10M", "$10M-$50M", "$50M-$200M", "$200M-$1B", ">$1B"]
        return rng.choice(ranges)

    @staticmethod
    def _synthetic_linkedin(name: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return f"https://www.linkedin.com/company/{slug}"

    @staticmethod
    def _synthetic_instagram(name: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "", name.lower()).strip()
        return f"https://www.instagram.com/{slug}"

    @staticmethod
    def _synthetic_what_it_does(company: dict[str, Any]) -> str:
        return f"{company.get('name')} operates in the {company.get('industry')} sector."

    @staticmethod
    def _synthetic_who_it_serves(company: dict[str, Any]) -> str:
        return "Other businesses in its sector and adjacent markets."

    @staticmethod
    def _synthetic_positioning(company: dict[str, Any]) -> str:
        return "Positions as a specialist provider within its niche."

    @staticmethod
    def _synthetic_public_developments(company: dict[str, Any]) -> str:
        return "No verified public developments available for this synthetic demo record."

    @staticmethod
    def _synthetic_challenges(company: dict[str, Any]) -> str:
        return "Synthetic demo - no verified operational challenges identified."

    def _synthetic_dm_names(self, seed: int, count: int, rng: random.Random) -> list[str]:
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Quinn", "Avery", "Pat"]
        last_names = ["Stone", "Reed", "Cole", "Brennan", "Hayes", "Park", "Shah", "Kim", "Olsen", "Diaz"]
        names: list[str] = []
        for i in range(count):
            name = f"{rng.choice(first_names)} {rng.choice(last_names)}"
            names.append(name)
        return names

    @staticmethod
    def _synthetic_dm_name(seed: int, rng: random.Random) -> str:
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam"]
        last_names = ["Stone", "Reed", "Cole", "Brennan", "Hayes"]
        return f"{rng.choice(first_names)} {rng.choice(last_names)}"

    @staticmethod
    def _split_dm_name(full_name: str):
        parts = full_name.strip().split()
        if len(parts) >= 2:
            return parts[0], " ".join(parts[1:])
        return parts[0], None

    @staticmethod
    def _email_confidence(status: str) -> float:
        conf_map = {
            "verified_deliverable": 0.9,
            "risky": 0.5,
            "invalid": 0.1,
            "unverified": 0.3,
            "unavailable": 0.0,
        }
        return conf_map.get(status, 0.0)

    @staticmethod
    def _synthetic_verification_status(email: str) -> str:
        seed = int(hashlib.md5(email.encode()).hexdigest(), 16) % 100
        if seed < 30:
            return "verified_deliverable"
        if seed < 50:
            return "risky"
        if seed < 70:
            return "unverified"
        if seed < 90:
            return "invalid"
        return "unavailable"

    @staticmethod
    def _verification_details(status: str) -> str:
        return {
            "verified_deliverable": "Synthetic demo - marked as deliverable.",
            "risky": "Synthetic demo - marked as risky.",
            "invalid": "Synthetic demo - marked as invalid.",
            "unverified": "Synthetic demo - not verified.",
            "unavailable": "Synthetic demo - unavailable.",
        }.get(status, "Synthetic demo.")
