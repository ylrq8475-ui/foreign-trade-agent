from __future__ import annotations

import unittest

from config.settings import Settings
from database.models import Lead
from maps.google_places import GooglePlacesClient


class FakeGooglePlacesClient(GooglePlacesClient):
    def __init__(self, places: list[dict]) -> None:
        super().__init__(Settings(google_maps_api_key="test-key"))
        self._places = places
        self.detail_calls: list[str] = []
        self.last_candidate_count = 0
        self.last_text_query = ""

    def _search_text_places(self, text_query: str, candidate_count: int) -> list[dict]:
        self.last_text_query = text_query
        self.last_candidate_count = candidate_count
        return self._places[:candidate_count]

    def _place_details(self, place_id: str) -> dict:
        self.detail_calls.append(place_id)
        return {
            "formattedAddress": f"{place_id} Address",
            "websiteUri": f"https://{place_id}.example.com",
            "internationalPhoneNumber": "+49-000-0000",
            "primaryType": "manufacturer",
        }


class GooglePlacesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GooglePlacesClient(Settings())

    def test_balanced_mode_backfills_b2b_queries_when_qualified_results_are_sparse(self) -> None:
        leads = [
            Lead(
                place_id="alpha",
                company_name="Alpha Private Label Kitchen Tools Distributor",
                country="Germany",
                industry="manufacturer",
            ),
            Lead(
                place_id="beta",
                company_name="Beta Supplier Group",
                country="Germany",
                industry="consultant",
            ),
            Lead(
                place_id="gamma",
                company_name="Gamma Procurement Hub",
                country="Germany",
                industry="service",
            ),
            Lead(
                place_id="delta",
                company_name="Delta Kitchen Shop",
                country="Germany",
                industry="store",
            ),
        ]

        ranked = self.client._rank_b2b_leads(
            leads,
            query="private label distributor",
            search_mode="balanced",
            limit=3,
        )

        self.assertEqual(3, len(ranked))
        self.assertEqual("alpha", ranked[0].place_id)
        self.assertEqual({"alpha", "beta", "gamma"}, {lead.place_id for lead in ranked})

    def test_search_with_api_expands_candidate_pool_but_only_enriches_selected_results(self) -> None:
        places = [
            {
                "id": f"lead-{index}",
                "displayName": {"text": f"Lead {index} Distributor"},
                "formattedAddress": f"Street {index}, Germany",
                "primaryType": "manufacturer",
            }
            for index in range(25)
        ]
        client = FakeGooglePlacesClient(places)

        leads = client._search_with_api(
            query="kitchen distributor",
            country="Germany",
            limit=5,
            search_mode="balanced",
        )

        self.assertEqual(20, client.last_candidate_count)
        self.assertEqual("kitchen distributor Germany", client.last_text_query)
        self.assertEqual(5, len(leads))
        self.assertEqual(5, len(client.detail_calls))
        self.assertTrue(all(lead.website.endswith(".example.com") for lead in leads))


if __name__ == "__main__":
    unittest.main()
