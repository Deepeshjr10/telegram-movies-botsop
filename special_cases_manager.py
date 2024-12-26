import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import os

@dataclass
class MovieLink:
    url: str
    language: str = ""

@dataclass
class SpecialCase:
    variants: List[str]
    links: List[MovieLink]

class SpecialCasesManager:
    def __init__(self, file_path: str = "special_cases.json"):
        self.file_path = file_path
        self.special_cases: Dict[str, SpecialCase] = {}
        self.load_cases()

    def load_cases(self) -> None:
        """Load special cases from JSON file"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    self.special_cases = {
                        movie: SpecialCase(
                            variants=case['variants'],
                            links=[MovieLink(**link) for link in case['links']]
                        )
                        for movie, case in data.items()
                    }
                print(f"Loaded {len(self.special_cases)} special cases")
            except Exception as e:
                print(f"Error loading special cases: {e}")
                self.special_cases = {}

    def save_cases(self) -> None:
        """Save special cases to JSON file"""
        try:
            data = {
                movie: {
                    'variants': case.variants,
                    'links': [{'url': link.url, 'language': link.language} for link in case.links]
                }
                for movie, case in self.special_cases.items()
            }
            with open(self.file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print("Special cases saved successfully")
        except Exception as e:
            print(f"Error saving special cases: {e}")

    def add_case(self, movie: str, variants: List[str], links: List[Dict[str, str]]) -> None:
        """Add a new special case or update existing one"""
        movie_links = [MovieLink(**link) for link in links]
        self.special_cases[movie] = SpecialCase(variants=variants, links=movie_links)
        self.save_cases()

    def remove_case(self, movie: str) -> bool:
        """Remove a special case"""
        if movie in self.special_cases:
            del self.special_cases[movie]
            self.save_cases()
            return True
        return False

    def get_case(self, movie: str) -> Optional[SpecialCase]:
        """Get a special case by movie name"""
        return self.special_cases.get(movie)

    def is_special_case(self, query: str) -> tuple[bool, List[Dict[str, str]]]:
        """Check if a query matches any special case"""
        query_lower = query.lower().strip()
        for movie, case in self.special_cases.items():
            if query_lower == movie.lower() or query_lower in [v.lower() for v in case.variants]:
                return True, [{'url': link.url, 'language': link.language} for link in case.links]
        return False, []

    def list_all_cases(self) -> Dict[str, Dict]:
        """List all special cases"""
        return {
            movie: {
                'variants': case.variants,
                'links': [{'url': link.url, 'language': link.language} for link in case.links]
            }
            for movie, case in self.special_cases.items()
        }

# Example usage and testing
if __name__ == "__main__":
    # Create an instance of the manager for testing
    test_manager = SpecialCasesManager()

    # Add some test cases
    test_manager.add_case(
        "Gladiator II",
        ["Gladiator II", ],
        [
            {"url": "https://adrinolinks.com/2HlN", "language": "Hindi 480p"},
            {"url": "https://adrinolinks.com/hzbXu", "language": "hindi 720p"},
            {"url": "https://adrinolinks.com/z65e9T", "language": "hindi 1080p"}
        ]
    )

    test_manager.add_case(
        "venom",
        ["venom", "venom1", "venom2"],
        [
            {"url": "https://www.udlinks.com/3I1l", "language": "hindi"}
        ]
    )

    test_manager.add_case(
        "mufasa",
        ["mufasa1", "mufasa2", "mufasa3"],
        [
            {"url": "https://ola4e356.com", "language": "hindi"}
        ]
    )

    # Test queries
    test_queries = ["pushpa 2", "PUSHPA2", "venom", "Venom2"]
    for query in test_queries:
        is_special, links = test_manager.is_special_case(query)
        if is_special:
            print(f"\nQuery: {query}")
            print("Links found:")
            for link in links:
                print(f"- {link['url']} ({link['language']})")
        else:
            print(f"\nQuery: {query}")
            print("No special case found")

    # List all cases
    print("\nAll special cases:")
    print(json.dumps(test_manager.list_all_cases(), indent=2))